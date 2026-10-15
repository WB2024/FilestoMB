"""Lidarr integration: register an album by its exact MusicBrainz release and
let Lidarr pick up the files Picard has already tagged and placed.

Lidarr is only told about the album and its folder. Nothing is moved, renamed
or deleted: the artist is added with its path set to the folder that already
holds the files, so a disk rescan maps them in place. Every step is verified
and any surprise is reported as a LidarrError instead of being worked around.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import httpx

MBID = re.compile(r"^[0-9a-fA-F-]{36}$")


class LidarrError(Exception):
    """Safe to show to the user."""


@dataclass
class Outcome:
    ok: bool
    summary: str
    steps: list[str] = field(default_factory=list)
    album_id: int | None = None
    url: str = ""


def to_lidarr_path(path: Path, music_root: Path, lidarr_library_path: str) -> str:
    """Translate a path under our music root into the same place as Lidarr sees it."""
    try:
        rel = Path(path).resolve().relative_to(music_root.resolve())
    except ValueError as error:
        raise LidarrError(f"{path} isn't inside the music library.") from error
    return str(PurePosixPath(lidarr_library_path) / PurePosixPath(rel.as_posix()))


class LidarrClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1",
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=30.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, **kwargs):
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise LidarrError(f"Couldn't reach Lidarr at {self.base_url}: {error or type(error).__name__}") from error
        if response.status_code in (401, 403):
            raise LidarrError("Lidarr rejected the API key.")
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                items = body if isinstance(body, list) else [body]
                detail = "; ".join(str(i.get("errorMessage") or i.get("message") or "") for i in items if isinstance(i, dict))
            except ValueError:
                pass
            raise LidarrError(f"Lidarr returned {response.status_code} for {method} {path}. {detail}".strip())
        return response.json() if response.content else None

    # -- read-only helpers -------------------------------------------------------

    async def status(self) -> dict:
        return await self._call("GET", "/system/status")

    async def root_folders(self) -> list[dict]:
        return await self._call("GET", "/rootfolder")

    async def find_album(self, release_group_mbid: str) -> dict | None:
        found = await self._call("GET", "/album", params={"foreignAlbumId": release_group_mbid})
        return found[0] if found else None

    async def lookup_album(self, release_group_mbid: str) -> dict | None:
        found = await self._call("GET", "/album/lookup", params={"term": f"lidarr:{release_group_mbid}"})
        return found[0] if found else None

    async def track_files(self, album_id: int) -> list[dict]:
        return await self._call("GET", "/trackfile", params={"albumId": album_id})

    # -- the import --------------------------------------------------------------

    async def _wait(self, command_id: int, timeout: float = 180.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            command = await self._call("GET", f"/command/{command_id}")
            if command.get("status") in ("completed", "failed", "aborted", "cancelled", "orphaned"):
                return command
            await asyncio.sleep(1.5)
        raise LidarrError("Lidarr took too long to rescan the folder. Check its Activity page.")

    async def send_album(
        self,
        *,
        release_mbid: str,
        release_group_mbid: str,
        album_folder_lidarr: str,
        root_folder: str,
        expected_tracks: int,
        dry_run: bool = False,
    ) -> Outcome:
        if not (MBID.match(release_mbid) and MBID.match(release_group_mbid)):
            raise LidarrError("Needs valid MusicBrainz release and release group IDs.")
        steps: list[str] = []
        album_folder = str(PurePosixPath(album_folder_lidarr))
        artist_folder = str(PurePosixPath(album_folder).parent)
        if not PurePosixPath(artist_folder).is_relative_to(PurePosixPath(root_folder)) or artist_folder == root_folder.rstrip("/"):
            raise LidarrError(
                f"Lidarr's root folder is {root_folder}, but the files are in {album_folder}. "
                "They need to be in an artist folder inside it."
            )

        album = await self.find_album(release_group_mbid)
        if album is None:
            lookup = await self.lookup_album(release_group_mbid)
            if lookup is None:
                raise LidarrError("Lidarr can't find that release group on its metadata server (it may not have synced from MusicBrainz yet).")
            roots = await self.root_folders()
            root = next((r for r in roots if r.get("path", "").rstrip("/") == root_folder.rstrip("/")), None)
            if root is None:
                raise LidarrError(f"{root_folder} isn't a root folder in Lidarr.")
            artist = lookup.get("artist") or {}
            existing = await self._call("GET", "/artist", params={"mbId": artist.get("foreignArtistId", "")})
            if existing:
                if existing[0].get("path", "").rstrip("/") != artist_folder:
                    raise LidarrError(
                        f"Lidarr already has this artist at {existing[0].get('path')}, but the files are in {artist_folder}. "
                        "Move one to match the other, then try again."
                    )
                artist = existing[0]
            else:
                artist = {
                    **artist,
                    "qualityProfileId": root["defaultQualityProfileId"],
                    "metadataProfileId": root["defaultMetadataProfileId"],
                    "rootFolderPath": root["path"],
                    "path": artist_folder,
                    "monitored": True,
                    "tags": root.get("defaultTags") or [],
                    "addOptions": {"monitor": "none", "monitored": True, "searchForMissingAlbums": False},
                }
            steps.append(f"Would add album to Lidarr (artist folder {artist_folder})" if dry_run else "Adding album to Lidarr")
            if dry_run:
                return Outcome(True, "Dry run: album isn't in Lidarr yet; nothing changed.", steps)
            body = {**lookup, "monitored": True, "artist": artist, "addOptions": {"addType": "automatic", "searchForNewAlbum": False}}
            album = await self._call("POST", "/album", json=body)
            steps.append(f"Added “{album.get('title')}” to Lidarr")
        else:
            artist_path = (album.get("artist") or {}).get("path", "").rstrip("/")
            if artist_path != artist_folder:
                raise LidarrError(
                    f"Lidarr has this album's artist at {artist_path}, but the files are in {artist_folder}. "
                    "Nothing was changed."
                )
            steps.append("Album already in Lidarr")

        album_id = album["id"]
        album = await self._call("GET", f"/album/{album_id}")
        releases = album.get("releases") or []
        chosen = [r for r in releases if r.get("foreignReleaseId", "").lower() == release_mbid.lower()]
        if not chosen:
            raise LidarrError("Lidarr's copy of this release group doesn't include that exact release yet. Refresh the artist in Lidarr and retry.")
        if dry_run:
            return Outcome(True, "Dry run OK: Lidarr knows this exact release.", steps + ["Release found in Lidarr"], album_id)
        if not chosen[0].get("monitored") or sum(1 for r in releases if r.get("monitored")) != 1:
            for r in releases:
                r["monitored"] = r in chosen
            album["releases"] = releases
            album["monitored"] = True
            album = await self._call("PUT", f"/album/{album_id}", json=album)
            steps.append("Pinned the exact MusicBrainz release")
        else:
            steps.append("Exact release already pinned")

        artist_id = album.get("artistId") or (album.get("artist") or {}).get("id")
        command = await self._call("POST", "/command", json={"name": "RescanArtist", "artistId": artist_id})
        result = await self._wait(command["id"])
        if result.get("status") != "completed":
            raise LidarrError(f"Lidarr's rescan {result.get('status')}: {result.get('message') or 'see its Activity page'}.")
        files = await self.track_files(album_id)
        in_folder = [f for f in files if str(PurePosixPath(f.get("path", "")).parent) == album_folder]
        steps.append(f"Lidarr mapped {len(in_folder)} of {expected_tracks} files")
        ok = len(in_folder) >= expected_tracks
        return Outcome(
            ok,
            "Imported into Lidarr, files left where they are." if ok else f"Lidarr only mapped {len(in_folder)} of {expected_tracks} files; check Unmapped Files in Lidarr.",
            steps,
            album_id,
            f"{self.base_url}/album/{album.get('foreignAlbumId', release_group_mbid)}",
        )

"""HTTP endpoints for the Lidarr integration. Logic lives in filestomb.lidarr."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import mutagen

from .. import integrations, lidarr
from ..tags import AUDIO_EXTENSIONS
from ..batch.runner import locate_moved
from ..config import Settings

DEFAULT_LIBRARY_PATH = "/data"


class SendIn(BaseModel):
    path: str  # the album folder Picard saved to, relative to the library
    release_mbid: str
    dry_run: bool = False


class LocateIn(BaseModel):
    release_mbid: str
    hours: float = 12


def configured() -> bool:
    return bool(integrations.get("lidarr_url") and integrations.get("lidarr_api_key") and integrations.get("lidarr_root_folder"))


def make_client() -> lidarr.LidarrClient:
    if not configured():
        raise HTTPException(422, "Set the Lidarr URL, API key and root folder in Settings first.")
    return lidarr.LidarrClient(integrations.get("lidarr_url"), integrations.get("lidarr_api_key"))


def count_release_files(folder: Path, release_mbid: str) -> int:
    """Audio files in the folder tagged with this release. An album folder can also hold
    other editions (e.g. an older FLAC copy beside the new MP3s), which don't count."""
    matching = 0
    for entry in sorted(folder.iterdir()):
        if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS:
            try:
                audio = mutagen.File(entry, easy=True)
            except Exception:  # noqa: BLE001 - unreadable files just don't count
                continue
            if audio and release_mbid.lower() in [v.lower() for v in audio.get("musicbrainz_albumid") or []]:
                matching += 1
    return matching


def make_sender(root: Path, mb_client) -> Callable[..., object]:
    """An async function (album folder, release mbid, dry_run) -> Outcome, shared
    by the HTTP endpoint and batch mode."""

    async def send(folder: Path, release_mbid: str, dry_run: bool = False) -> lidarr.Outcome:
        client = make_client()
        try:
            release = await mb_client.lookup_release(release_mbid)
            group = (release.get("release-group") or {}).get("id")
            if not group:
                raise lidarr.LidarrError("MusicBrainz didn't say which release group that release belongs to.")
            tracks = await asyncio.to_thread(count_release_files, folder, release_mbid)
            if not tracks:
                raise lidarr.LidarrError("None of the audio files in that folder are tagged with this release ID.")
            return await client.send_album(
                release_mbid=release_mbid,
                release_group_mbid=group,
                album_folder_lidarr=lidarr.to_lidarr_path(
                    folder, root, integrations.get("lidarr_library_path") or DEFAULT_LIBRARY_PATH
                ),
                root_folder=integrations.get("lidarr_root_folder"),
                expected_tracks=tracks,
                dry_run=dry_run,
            )
        finally:
            await client.aclose()

    return send


def register(app: FastAPI, settings: Settings, root: Path, resolve: Callable[[str], Path], mb_client) -> Callable[..., object]:
    send = make_sender(root, mb_client)

    @app.get("/api/lidarr/status")
    async def status() -> dict:
        return {"configured": configured(), "auto": integrations.get("lidarr_auto") == "1", "url": integrations.get("lidarr_url")}

    @app.post("/api/settings/test-lidarr")
    async def test() -> dict:
        client = make_client()
        try:
            info = await client.status()
            folders = await client.root_folders()
        except lidarr.LidarrError as error:
            raise HTTPException(502, str(error)) from error
        finally:
            await client.aclose()
        wanted = integrations.get("lidarr_root_folder").rstrip("/")
        return {
            "ok": True,
            "version": info.get("version"),
            "root_folder_found": any(f.get("path", "").rstrip("/") == wanted for f in folders),
            "root_folders": [f.get("path") for f in folders],
        }

    @app.post("/api/lidarr/locate")
    async def locate(body: LocateIn) -> dict:
        """Where did Picard just put this release? Needs PICARD_DEST_ROOT."""
        if not settings.picard_dest_root:
            raise HTTPException(422, "PICARD_DEST_ROOT isn't set, so FilesToMB can't search for the saved files.")
        dest = Path(settings.picard_dest_root)
        hits = await asyncio.to_thread(locate_moved, dest, time.time() - body.hours * 3600, body.release_mbid)
        folders = sorted({str(h.parent.resolve().relative_to(root)) for h in hits})
        return {"folders": folders}

    @app.post("/api/lidarr/send")
    async def send_endpoint(body: SendIn) -> dict:
        folder = resolve(body.path)
        if not folder.is_dir():
            raise HTTPException(404, "Not a directory.")
        try:
            outcome = await send(folder, body.release_mbid, body.dry_run)
        except lidarr.LidarrError as error:
            raise HTTPException(502, str(error)) from error
        return {"ok": outcome.ok, "summary": outcome.summary, "steps": outcome.steps, "url": outcome.url, "dry_run": body.dry_run}

    return send

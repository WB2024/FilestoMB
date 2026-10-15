"""FastAPI backend for the FilesToMB web UI.

A thin JSON layer over the same modules the TUI uses (tag reading, matching,
seeding, OAuth). The server is stateless between requests: the browser holds
the album being edited and sends it back when it needs matching or seeding.

Browsing is confined to `Settings.music_root`; the API only ever speaks in
paths *relative* to that root, so the filesystem layout outside it is never
exposed and `..` tricks are rejected.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import coverart, state, tags
from ..config import Settings, load_settings
from ..matching import match_album
from ..mb import seed
from ..mb.client import MusicBrainzClient
from ..mb.oauth import MusicBrainzOAuth, build_authorize_url
from ..models import Album, EntityType, Track

STATIC_DIR = Path(__file__).parent / "static"
USERSCRIPT_TEMPLATE = Path(__file__).parent / "userscript.js"
# Bump when userscript.js changes so installed copies auto-update.
USERSCRIPT_VERSION = "1.1.0"
COVER_MAX_BYTES = 20 * 1024 * 1024
PICKABLE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
CAPTURE_ENTITIES = {"artist", "label", "release-group", "release"}
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class TrackIn(BaseModel):
    filename: str = ""
    title: str = ""
    track_number: str | None = None
    disc_number: str | None = None
    length_ms: int | None = None


class AlbumIn(BaseModel):
    title: str
    artist: str
    date: str | None = None
    label: str | None = None
    catalog_number: str | None = None
    barcode: str | None = None
    tracks: list[TrackIn] = Field(default_factory=list)

    def to_album(self) -> Album:
        def clean(value: str | None) -> str | None:
            value = (value or "").strip()
            return value or None

        return Album(
            directory=Path("."),
            title=self.title.strip(),
            artist=self.artist.strip(),
            date=clean(self.date),
            label=clean(self.label),
            catalog_number=clean(self.catalog_number),
            barcode=clean(self.barcode),
            tracks=[
                Track(
                    path=Path(t.filename or t.title),
                    title=t.title.strip(),
                    artist="",
                    album="",
                    album_artist="",
                    track_number=clean(t.track_number),
                    disc_number=clean(t.disc_number),
                    length_ms=t.length_ms,
                )
                for t in self.tracks
            ],
        )


class PathIn(BaseModel):
    path: str = ""


class MatchIn(BaseModel):
    title: str
    artist: str
    label: str | None = None


class NameIn(BaseModel):
    name: str


class ReleaseGroupSeedIn(BaseModel):
    title: str
    artist: str
    disambiguation: str | None = None
    primary_type: str | None = None
    secondary_types: list[str] = Field(default_factory=list)
    edit_note: str | None = None


class ReleaseDetailsIn(BaseModel):
    status: str | None = None
    language: str | None = None
    script: str | None = None
    country: str | None = None
    packaging: str | None = None
    annotation: str | None = None
    disambiguation: str | None = None
    external_links: list[str] = Field(default_factory=list)
    edit_note: str | None = None


class ReleaseSeedIn(BaseModel):
    album: AlbumIn
    release_group_mbid: str | None = None
    artist_mbid: str | None = None
    label_mbid: str | None = None
    details: ReleaseDetailsIn = Field(default_factory=ReleaseDetailsIn)


class JobIn(BaseModel):
    """What the user is working on, shared with the userscript running on musicbrainz.org."""

    path: str
    title: str
    artist: str
    release_mbid: str | None = None
    has_cover: bool = False
    cover_filename: str | None = None
    # Entities the user is currently creating on musicbrainz.org, and the
    # names to expect, so the userscript can recognise the new page.
    awaiting: list[str] = Field(default_factory=list)
    names: dict[str, str] = Field(default_factory=dict)


class LookupIn(BaseModel):
    title: str
    artist_mbid: str | None = None
    release_group_mbid: str | None = None


class CaptureIn(BaseModel):
    entity: str
    mbid: str
    name: str | None = None


class UseImageIn(BaseModel):
    path: str
    image: str


class CodeIn(BaseModel):
    code: str


class CollectionAddIn(BaseModel):
    collection_id: str
    release_mbid: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _extract_mbid(value: str | None) -> str | None:
    """Accept a bare MBID or a full musicbrainz.org URL, return the UUID."""
    if not value:
        return None
    found = UUID_RE.search(value)
    return found.group(0).lower() if found else None


def _has_audio(directory: Path) -> bool:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file() and Path(entry.name).suffix.lower() in tags.AUDIO_EXTENSIONS:
                    return True
    except OSError:
        pass
    return False


def _resolve(root: Path, relative: str) -> Path:
    """Map a root-relative path to an absolute one, refusing to leave the root."""
    target = (root / relative.strip("/")).resolve()
    if target != root and not target.is_relative_to(root):
        raise HTTPException(400, "Path is outside the music library.")
    return target


def _relative(root: Path, absolute: Path) -> str:
    rel = absolute.relative_to(root).as_posix()
    return "" if rel == "." else rel


def _load_cover(directory: Path) -> tuple[bytes, str, str] | None:
    """Return (bytes, mime, filename) for the album's cover art, preferring a
    standalone cover file over art embedded in the tags."""
    cover_file = coverart.find_cover_file(directory)
    if cover_file is not None:
        mime = "image/png" if cover_file.suffix.lower() == ".png" else "image/jpeg"
        return cover_file.read_bytes(), mime, cover_file.name

    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in tags.AUDIO_EXTENSIONS:
            continue
        extracted = coverart.extract_embedded_cover(path)
        if extracted is None:
            continue
        try:
            data = extracted.read_bytes()
            mime = "image/png" if extracted.suffix == ".png" else "image/jpeg"
            return data, mime, f"cover{extracted.suffix}"
        finally:
            extracted.unlink(missing_ok=True)
    return None


def _sniff_image(data: bytes) -> tuple[str, str] | None:
    """(mime, extension) for the image types the Cover Art Archive accepts."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def _album_to_json(album: Album, root: Path, directory: Path) -> dict:
    first = album.tracks[0]
    return {
        "path": _relative(root, directory),
        "folder_name": directory.name or "library",
        "title": album.title,
        "artist": album.artist,
        "date": album.date or "",
        "label": album.label or "",
        "catalog_number": album.catalog_number or "",
        "barcode": album.barcode or "",
        "tagged_release_mbid": first.musicbrainz_release_id,
        "tracks": [
            {
                "filename": t.path.relative_to(directory).as_posix(),
                "title": t.title,
                "artist": t.artist,
                "track_number": t.track_number or "",
                "disc_number": t.disc_number or "",
                "length_ms": t.length_ms,
            }
            for t in album.tracks
        ],
    }


def _match_to_json(result) -> dict:
    return {
        "status": result.status.value,
        "query": result.query,
        "selected_mbid": result.selected_mbid,
        "candidates": [asdict(c) for c in result.candidates],
    }


def _app_version() -> str:
    try:
        return version("filestomb")
    except PackageNotFoundError:
        return "dev"


# --------------------------------------------------------------------------
# App factory
# --------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None,
    mb_client: MusicBrainzClient | None = None,
    oauth: MusicBrainzOAuth | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    root = settings.music_root.resolve()
    client = mb_client or MusicBrainzClient(settings.user_agent, settings.api_base_url)
    auth = oauth or MusicBrainzOAuth(settings.oauth_client_id, settings.oauth_client_secret)
    username_cache = {"value": ""}
    # Single-user, in-memory: the album being submitted, plus MBIDs the
    # userscript has captured from musicbrainz.org that the UI hasn't picked up yet.
    job: dict = {"active": False}
    captures: list[dict] = []
    # Covers the user supplied (uploaded, or picked from the album folder),
    # keyed by album path. They take precedence over auto-detected art and
    # live in memory: the music mount is read-only, and a restart just
    # falls back to auto-detection.
    covers: dict[str, tuple[bytes, str, str]] = {}

    async def cover_for(path: str, directory: Path):
        if path.strip("/") in covers:
            return covers[path.strip("/")]
        return await asyncio.to_thread(_load_cover, directory) if directory.is_dir() else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await client.aclose()
        await auth.aclose()

    app = FastAPI(title="FilesToMB", version=_app_version(), lifespan=lifespan)

    def mb_error(error: Exception) -> HTTPException:
        if isinstance(error, httpx.HTTPStatusError):
            return HTTPException(502, f"MusicBrainz returned {error.response.status_code}.")
        if isinstance(error, httpx.HTTPError):
            return HTTPException(502, f"Couldn't reach MusicBrainz: {error or type(error).__name__}")
        return HTTPException(500, str(error))

    # -- Config / meta -------------------------------------------------------

    @app.get("/api/config")
    async def get_config() -> dict:
        last = state.load_last_directory()
        last_rel = ""
        if last is not None:
            try:
                last_rel = _relative(root, last.resolve()) if last.resolve().is_relative_to(root) else ""
            except (OSError, ValueError):
                last_rel = ""
        return {
            "version": _app_version(),
            "userscript_version": USERSCRIPT_VERSION,
            "library_name": root.name or str(root),
            "library_exists": root.is_dir(),
            "last_path": last_rel,
            "has_contact": settings.has_contact,
            "oauth_configured": settings.has_oauth,
            "options": {
                "release_statuses": seed.RELEASE_STATUSES,
                "release_packagings": seed.RELEASE_PACKAGINGS,
                "rg_primary_types": list(seed.RELEASE_GROUP_PRIMARY_TYPES),
                "rg_secondary_types": list(seed.RELEASE_GROUP_SECONDARY_TYPES),
            },
        }

    # -- Browsing ------------------------------------------------------------

    @app.get("/api/browse")
    async def browse(path: str = Query("")) -> dict:
        directory = _resolve(root, path)
        if not directory.is_dir():
            raise HTTPException(404, "Not a directory.")

        def listing() -> dict:
            dirs = []
            audio_here = 0
            try:
                entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
            except PermissionError:
                raise HTTPException(403, "Permission denied.")
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    child = Path(entry.path)
                    dirs.append(
                        {
                            "name": entry.name,
                            "path": _relative(root, child.resolve()),
                            "has_audio": _has_audio(child),
                        }
                    )
                elif entry.is_file() and Path(entry.name).suffix.lower() in tags.AUDIO_EXTENSIONS:
                    audio_here += 1
            return {"dirs": dirs, "audio_files": audio_here}

        data = await asyncio.to_thread(listing)
        rel = _relative(root, directory)
        crumbs = [{"name": root.name or "library", "path": ""}]
        walked = ""
        for part in [p for p in rel.split("/") if p]:
            walked = f"{walked}/{part}".strip("/")
            crumbs.append({"name": part, "path": walked})
        return {"path": rel, "crumbs": crumbs, **data}

    @app.post("/api/scan")
    async def scan(body: PathIn) -> dict:
        directory = _resolve(root, body.path)
        if not directory.is_dir():
            raise HTTPException(404, "Not a directory.")
        album = await asyncio.to_thread(tags.scan_directory, directory, False)
        if album is None:
            raise HTTPException(404, "No readable audio files were found in that folder.")
        cover = await cover_for(body.path, directory)
        try:
            state.save_last_directory(directory)
        except OSError:
            pass
        data = _album_to_json(album, root, directory)
        data["cover"] = (
            {"filename": cover[2], "bytes": len(cover[0]), "custom": body.path.strip("/") in covers}
            if cover
            else None
        )
        return data

    @app.get("/api/cover")
    async def cover(path: str = Query(""), download: bool = False) -> Response:
        directory = _resolve(root, path)
        found = await cover_for(path, directory)
        if found is None:
            raise HTTPException(404, "No cover art found.")
        data, mime, filename = found
        disposition = "attachment" if download else "inline"
        return Response(
            data,
            media_type=mime,
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )

    def cover_json(found: tuple[bytes, str, str], path: str) -> dict:
        return {"filename": found[2], "bytes": len(found[0]), "custom": path.strip("/") in covers}

    @app.put("/api/cover")
    async def upload_cover(request: Request, path: str = Query(""), filename: str = Query("cover")) -> dict:
        """Client-side option: the browser sends the raw image bytes."""
        directory = _resolve(root, path)
        if not directory.is_dir():
            raise HTTPException(404, "Not a directory.")
        data = await request.body()
        if not data:
            raise HTTPException(422, "No image data received.")
        if len(data) > COVER_MAX_BYTES:
            raise HTTPException(413, "Image is larger than 20 MB.")
        kind = _sniff_image(data)
        if kind is None:
            raise HTTPException(415, "That isn't a JPEG, PNG, GIF or WebP image.")
        stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem)[:60] or "cover"
        covers[path.strip("/")] = (data, kind[0], f"{stem}{kind[1]}")
        return cover_json(covers[path.strip("/")], path)

    @app.delete("/api/cover")
    async def remove_cover(path: str = Query("")) -> dict:
        covers.pop(path.strip("/"), None)
        found = await cover_for(path, _resolve(root, path))
        return {"cover": cover_json(found, path) if found else None}

    @app.get("/api/images")
    async def list_images(path: str = Query("")) -> dict:
        """Server-side option: image files already inside the album folder."""
        directory = _resolve(root, path)
        if not directory.is_dir():
            raise HTTPException(404, "Not a directory.")

        def find() -> list[dict]:
            found = []
            for file in sorted(directory.rglob("*")):
                if len(found) >= 60:
                    break
                if file.is_file() and file.suffix.lower() in PICKABLE_IMAGE_EXTENSIONS:
                    try:
                        size = file.stat().st_size
                    except OSError:
                        continue
                    if size <= COVER_MAX_BYTES:
                        found.append({"name": file.relative_to(directory).as_posix(), "bytes": size})
            return found

        return {"images": await asyncio.to_thread(find)}

    def album_image(path: str, name: str) -> Path:
        directory = _resolve(root, path)
        file = (directory / name).resolve()
        if not file.is_relative_to(directory) or file.suffix.lower() not in PICKABLE_IMAGE_EXTENSIONS:
            raise HTTPException(400, "Not an image inside this album folder.")
        if not file.is_file():
            raise HTTPException(404, "No such image.")
        return file

    @app.get("/api/image")
    async def get_image(path: str = Query(""), name: str = Query(...)) -> Response:
        file = album_image(path, name)
        data = await asyncio.to_thread(file.read_bytes)
        kind = _sniff_image(data)
        if kind is None:
            raise HTTPException(415, "Unsupported image.")
        return Response(data, media_type=kind[0], headers={"Cache-Control": "max-age=300"})

    @app.post("/api/cover/use")
    async def use_image(body: UseImageIn) -> dict:
        file = album_image(body.path, body.image)
        data = await asyncio.to_thread(file.read_bytes)
        kind = _sniff_image(data)
        if kind is None:
            raise HTTPException(415, "That file isn't a valid image.")
        covers[body.path.strip("/")] = (data, kind[0], file.name)
        return cover_json(covers[body.path.strip("/")], body.path)

    # -- MusicBrainz matching ------------------------------------------------

    @app.post("/api/match")
    async def match(body: MatchIn) -> dict:
        album = Album(
            directory=Path("."),
            title=body.title.strip(),
            artist=body.artist.strip(),
            label=_blank_to_none(body.label),
        )
        if not album.title or not album.artist:
            raise HTTPException(422, "Title and artist are required to search MusicBrainz.")
        try:
            results = await match_album(client, album)
        except Exception as error:
            raise mb_error(error)
        return {entity.value: _match_to_json(result) for entity, result in results.items()}

    @app.post("/api/lookup")
    async def lookup(body: LookupIn) -> dict:
        """Find a just-created release group / release without waiting for
        MusicBrainz's search index: browse from the known parent entity."""

        def norm(text: str) -> str:
            return "".join(ch for ch in text.casefold() if ch.isalnum())

        wanted = norm(body.title)
        artist = _extract_mbid(body.artist_mbid)
        group = _extract_mbid(body.release_group_mbid)
        found: dict[str, list[dict]] = {"release-group": [], "release": []}
        try:
            if artist and not group:
                groups = [c for c in await client.browse_release_groups(artist) if norm(c.name) == wanted]
                found["release-group"] = [asdict(c) for c in groups]
                if len(groups) == 1:
                    group = groups[0].mbid
            if group:
                releases = [c for c in await client.browse_releases(group) if norm(c.name) == wanted]
                found["release"] = [asdict(c) for c in releases]
        except Exception as error:
            raise mb_error(error)
        return found

    @app.post("/api/resolve-mbid")
    async def resolve_mbid(body: NameIn) -> dict:
        found = _extract_mbid(body.name)
        if not found:
            raise HTTPException(422, "That doesn't look like a MusicBrainz ID or URL.")
        return {"mbid": found}

    # -- Seeded edit forms ---------------------------------------------------

    @app.post("/api/seed/artist")
    async def seed_artist(body: NameIn) -> dict:
        return {"url": seed.seed_artist_url(body.name.strip())}

    @app.post("/api/seed/label")
    async def seed_label(body: NameIn) -> dict:
        if not body.name.strip():
            raise HTTPException(422, "This album has no label to create.")
        return {"url": seed.seed_label_url(body.name.strip())}

    @app.post("/api/seed/release-group")
    async def seed_release_group(body: ReleaseGroupSeedIn) -> dict:
        url = seed.seed_release_group_url(
            body.title.strip(),
            body.artist.strip(),
            disambiguation=_blank_to_none(body.disambiguation),
            primary_type=_blank_to_none(body.primary_type),
            secondary_types=body.secondary_types,
            edit_note=_blank_to_none(body.edit_note),
        )
        return {"url": url}

    @app.post("/api/seed/release")
    async def seed_release(body: ReleaseSeedIn) -> dict:
        details = body.details
        fields = seed.build_release_seed_fields(
            body.album.to_album(),
            release_group_mbid=_extract_mbid(body.release_group_mbid),
            artist_mbid=_extract_mbid(body.artist_mbid),
            label_mbid=_extract_mbid(body.label_mbid),
            status=_blank_to_none(details.status),
            language=_blank_to_none(details.language),
            script=_blank_to_none(details.script),
            country=_blank_to_none(details.country),
            packaging=_blank_to_none(details.packaging),
            annotation=_blank_to_none(details.annotation),
            disambiguation=_blank_to_none(details.disambiguation),
            external_links=[u.strip() for u in details.external_links if u.strip()],
            edit_note=_blank_to_none(details.edit_note),
        )
        return {"action": f"{seed.BASE_URL}/release/add", "fields": fields}

    # -- OAuth login + collections ------------------------------------------

    @app.get("/api/auth/status")
    async def auth_status() -> dict:
        logged_in = auth.is_logged_in
        if logged_in and not username_cache["value"]:
            try:
                username_cache["value"] = await auth.fetch_username()
            except Exception:
                pass
        return {
            "configured": settings.has_oauth,
            "logged_in": logged_in,
            "username": username_cache["value"] if logged_in else "",
        }

    @app.post("/api/auth/start")
    async def auth_start() -> dict:
        if not settings.has_oauth:
            raise HTTPException(
                400, "Set MB_OAUTH_CLIENT_ID and MB_OAUTH_CLIENT_SECRET to enable login."
            )
        return {"url": build_authorize_url(settings.oauth_client_id)}

    @app.post("/api/auth/code")
    async def auth_code(body: CodeIn) -> dict:
        try:
            await auth.exchange_code(body.code.strip())
            username_cache["value"] = await auth.fetch_username()
        except httpx.HTTPStatusError:
            raise HTTPException(400, "MusicBrainz rejected that code. Codes are single-use; start again.")
        except Exception as error:
            raise mb_error(error)
        return {"logged_in": True, "username": username_cache["value"]}

    @app.post("/api/auth/logout")
    async def auth_logout() -> dict:
        auth.logout()
        username_cache["value"] = ""
        return {"logged_in": False}

    @app.get("/api/collections")
    async def collections() -> dict:
        if not auth.is_logged_in:
            raise HTTPException(401, "Log in to MusicBrainz first.")
        try:
            token = await auth.get_access_token()
            if not username_cache["value"]:
                username_cache["value"] = await auth.fetch_username()
            found = await client.list_collections(token, username=username_cache["value"] or None)
        except Exception as error:
            raise mb_error(error)
        return {
            "collections": [
                {"id": c["id"], "name": c.get("name", c["id"])}
                for c in found
                if c.get("entity-type") == "release"
            ]
        }

    @app.post("/api/collections/add")
    async def collections_add(body: CollectionAddIn) -> dict:
        if not auth.is_logged_in:
            raise HTTPException(401, "Log in to MusicBrainz first.")
        release = _extract_mbid(body.release_mbid)
        if not release:
            raise HTTPException(422, "Invalid release ID.")
        try:
            token = await auth.get_access_token()
            await client.add_release_to_collection(body.collection_id, release, token)
        except Exception as error:
            raise mb_error(error)
        return {"ok": True}

    # -- Userscript + job sharing -------------------------------------------

    def public_url(request: Request) -> str:
        configured = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
        return configured or str(request.base_url).rstrip("/")

    @app.get("/filestomb.user.js")
    async def userscript(request: Request) -> Response:
        base = public_url(request)
        host = httpx.URL(base).host
        text = (
            USERSCRIPT_TEMPLATE.read_text(encoding="utf-8")
            .replace("__BASE_URL__", base)
            .replace("__HOST__", host)
            .replace("__VERSION__", USERSCRIPT_VERSION)
        )
        return Response(
            text,
            media_type="text/javascript; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/userscript")
    async def userscript_info(request: Request) -> dict:
        return {"version": USERSCRIPT_VERSION, "url": f"{public_url(request)}/filestomb.user.js"}

    @app.put("/api/job")
    async def put_job(body: JobIn) -> dict:
        directory = _resolve(root, body.path)
        if not directory.is_dir():
            raise HTTPException(404, "Not a directory.")
        if job.get("path") != body.path:
            captures.clear()
        job.clear()
        job.update(
            active=True,
            path=body.path,
            title=body.title,
            artist=body.artist,
            release_mbid=_extract_mbid(body.release_mbid),
            has_cover=body.has_cover,
            cover_filename=body.cover_filename,
            awaiting=[e for e in body.awaiting if e in CAPTURE_ENTITIES],
            names=body.names,
        )
        return {"ok": True}

    @app.get("/api/job")
    async def get_job() -> dict:
        return dict(job)

    @app.post("/api/job/capture")
    async def capture(body: CaptureIn) -> dict:
        mbid = _extract_mbid(body.mbid)
        if body.entity not in CAPTURE_ENTITIES or not mbid:
            raise HTTPException(422, "Unsupported entity or invalid MBID.")
        captures.append({"entity": body.entity, "mbid": mbid, "name": body.name or ""})
        if body.entity == "release" and job.get("active"):
            job["release_mbid"] = mbid
        return {"ok": True}

    @app.get("/api/job/captures")
    async def take_captures() -> dict:
        taken = list(captures)
        captures.clear()
        return {"captures": taken}

    # -- Static frontend -----------------------------------------------------

    @app.middleware("http")
    async def revalidate_static(request: Request, call_next):
        # Without this, browsers heuristically cache app.js/app.css and keep
        # running stale code after the container is updated.
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> Response:
        # Version the asset URLs so every release is fetched fresh.
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__ASSET_VERSION__", _app_version())
        return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    return app


def run() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()

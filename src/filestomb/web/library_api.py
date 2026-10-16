"""HTTP endpoints for the Clean-library check. Logic lives in filestomb.library."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import integrations, library, tags
from ..config import Settings
from ..paths import config_dir

STALE_AFTER_SECONDS = 300  # kick off a background refresh when the index is older than this


class CheckIn(BaseModel):
    path: str  # the album being imported, relative to the music root
    release_mbid: str


class ReplaceIn(BaseModel):
    path: str
    release_mbid: str
    folder: str  # the existing copy, relative to the music root


def make(settings: Settings, music_root: Path) -> "LibraryService":
    return LibraryService(settings, music_root)


class LibraryService:
    def __init__(self, settings: Settings, music_root: Path) -> None:
        self.settings = settings
        self.music_root = Path(music_root).resolve()
        self.index = library.LibraryIndex(config_dir() / "library-index.db")
        self.audit_path = config_dir() / "library-audit.log"

    # -- configuration -----------------------------------------------------

    def clean_root(self) -> Path | None:
        value = integrations.get("clean_library") or self.settings.picard_dest_root
        if not value:
            return None
        path = Path(value).resolve()
        try:
            path.relative_to(self.music_root)
        except ValueError:
            return None
        return path if path.is_dir() else None

    def archive_root(self) -> Path | None:
        clean = self.clean_root()
        if clean is None:
            return None
        custom = integrations.get("replaced_folder")
        return Path(custom).resolve() if custom else clean.parent / "Replaced"

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.music_root).as_posix()

    # -- index -------------------------------------------------------------

    def refresh_blocking(self) -> None:
        clean = self.clean_root()
        if clean is not None:
            self.index.refresh(clean, skip=self.archive_root())

    def refresh_in_background(self) -> bool:
        if self.index.building or self.clean_root() is None:
            return False
        threading.Thread(target=self.refresh_blocking, daemon=True).start()
        return True

    def refresh_folder(self, folder: Path) -> None:
        clean = self.clean_root()
        if clean is not None:
            self.index.refresh_folder(clean, folder)

    def ensure_fresh_soon(self) -> None:
        if not self.index.building and time.time() - float(self.index.meta("last_built", "0") or 0) > STALE_AFTER_SECONDS:
            self.refresh_in_background()

    # -- lookups -----------------------------------------------------------

    def existing_copies(self, directory: Path, release_mbid: str) -> list[dict]:
        """Folders in the Clean library that already hold this release, with quality, excluding `directory` itself."""
        clean = self.clean_root()
        if clean is None:
            return []
        out = []
        for rel, _count, _audio in self.index.find_release(release_mbid):
            folder = clean / rel
            if folder.resolve() == directory.resolve() or not folder.is_dir():
                continue
            mine, everything = library.release_files(folder, release_mbid)
            if not mine:  # the index was stale; the files have moved or been retagged
                continue
            out.append({"folder": self.rel(folder), "files": mine, "other_files": len(everything) - len(mine)})
        return out

    def guard_message(self, directory: Path, release_mbid: str) -> str | None:
        """For batch mode: a reason not to import this album unattended, or None."""
        copies = self.existing_copies(directory, release_mbid)
        if not copies:
            return None
        return f"Already in your library at {copies[0]['folder']}. Open it from here to compare and choose; nothing was changed."

    def audit(self, line: str) -> None:
        try:
            with self.audit_path.open("a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except OSError:
            pass


def register(app: FastAPI, service: LibraryService, resolve: Callable[[str], Path], refuse_during_batch: Callable[[], None]) -> None:
    @app.get("/api/library/status")
    async def status() -> dict:
        clean, archive = service.clean_root(), service.archive_root()
        configured = clean is not None
        if configured and not service.index.stats()["last_built"] and not service.index.building:
            service.refresh_in_background()
        return {"configured": configured, "clean": str(clean) if clean else "", "archive": str(archive) if archive else "", **service.index.stats()}

    @app.post("/api/library/reindex")
    async def reindex() -> dict:
        if service.clean_root() is None:
            raise HTTPException(422, "Set the Clean library folder (inside the music library) in Settings first.")
        return {"started": service.refresh_in_background()}

    @app.post("/api/library/check")
    async def check(body: CheckIn) -> dict:
        directory = resolve(body.path)
        clean, archive = service.clean_root(), service.archive_root()
        if clean is None:
            return {"configured": False, "matches": []}
        if service.index.building or not service.index.stats()["last_built"]:
            service.refresh_in_background()
            return {"configured": True, "indexing": True, "progress": service.index.progress, "matches": []}
        service.ensure_fresh_soon()
        album = await asyncio.to_thread(tags.scan_directory, directory, False) if directory.is_dir() else None
        if album is None:
            raise HTTPException(404, "No readable audio files were found in that folder.")
        new_q = await asyncio.to_thread(library.summarize, [Path(t.path) for t in album.tracks])
        matches = []
        for copy in await asyncio.to_thread(service.existing_copies, directory, body.release_mbid):
            existing_q = await asyncio.to_thread(library.summarize, copy["files"])
            cmp = library.compare(existing_q, new_q)
            matches.append({"folder": copy["folder"], "other_files": copy["other_files"], "existing": library.describe(existing_q), "new": library.describe(new_q),
                            "verdict": cmp["verdict"], "reasons": cmp["reasons"]})
        return {"configured": True, "indexing": False, "archive": str(archive), "matches": matches}

    @app.post("/api/library/replace")
    async def replace(body: ReplaceIn) -> dict:
        """Move the existing copy into the replaced-albums folder. Nothing is deleted."""
        refuse_during_batch()
        directory = resolve(body.path)
        clean, archive = service.clean_root(), service.archive_root()
        if clean is None or archive is None:
            raise HTTPException(422, "Set the Clean library folder in Settings first.")
        folder = resolve(body.folder)
        # Only a folder the check itself would have offered, never an arbitrary path.
        offered = {c["folder"] for c in await asyncio.to_thread(service.existing_copies, directory, body.release_mbid)}
        if service.rel(folder) not in offered:
            raise HTTPException(422, "That isn't an existing copy of this release in the library. Check again.")
        try:
            result = await asyncio.to_thread(library.archive_existing, clean, archive, folder, body.release_mbid, time.strftime("%Y%m%d-%H%M%S"))
        except library.LibraryError as error:
            raise HTTPException(422, str(error)) from error
        service.audit(f"replaced release={body.release_mbid} from={service.rel(folder)} archived_to={result['archived_to']} files={result['files']} whole_folder={result['whole_folder']}")
        await asyncio.to_thread(service.refresh_folder, folder)  # drops the row if the whole folder moved
        return result

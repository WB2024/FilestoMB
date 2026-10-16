"""Background orchestration for batch mode: discover, match, and (gated) process.

Safety rules enforced here, not just in the UI:

* Discovery and matching never write to the library.
* Only albums triaged "ready" are ever processed, and each is re-verified
  immediately beforehand: unchanged on disk since it was matched, and the
  release re-fetched and re-judged confident.
* Albums are processed strictly one at a time, so Picard only ever holds one
  album and "Save matched" can't touch anything else.
* After saving, the source folder must be empty of audio and (if a destination
  is configured) the files must be found there carrying the right release ID.
* The first anomaly stops the whole batch. Nothing is ever deleted.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
import mutagen

from .. import picard, releasetags, tags
from ..releasetags import match_tracks, parse_release
from . import discovery, store
from .matcher import MBLike, evaluate_album, evaluate_candidate

AUDIO_EXTENSIONS = tags.AUDIO_EXTENSIONS
MAX_CONSECUTIVE_MB_ERRORS = 5
WARMUP_BASE_SECONDS = 8.0       # Picard needs a moment to fetch the release and match the files
WARMUP_PER_TRACK_SECONDS = 0.5
WARMUP_MAX_SECONDS = 30.0
SAVE_TIMEOUT_SECONDS = 150.0    # how long to wait for the source folder to empty
SAVE_RESEND_SECONDS = 20.0      # SAVE_MATCHED is idempotent, so re-sending is safe
POLL_SECONDS = 3.0
PAUSE_BETWEEN_ALBUMS = 2.0


class BatchAbort(Exception):
    """Stop the whole batch: something unexpected happened and a human should look."""


def locate_moved(dest_root: Path, since: float, release_mbid: str, max_depth: int = 7) -> list[Path]:
    """Find files Picard just saved: audio under `dest_root` whose inode changed
    since `since` and that carry `release_mbid`.

    Uses ctime, not mtime: Picard (with "preserve timestamps") keeps a file's old
    mtime, but moving or retagging a file always bumps its ctime, which can't be
    set by hand. Directory mtimes can't be used to prune the walk either, because
    adding a file to an existing album folder doesn't touch its ancestors. Only
    stat() is called per file, so walking a large library is quick."""
    hits: list[Path] = []
    threshold = since - 5

    def walk(directory: str, depth: int) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        walk(entry.path, depth + 1)
                elif Path(entry.name).suffix.lower() in AUDIO_EXTENSIONS and entry.stat().st_ctime >= threshold:
                    audio = mutagen.File(entry.path, easy=True)
                    if audio and release_mbid in (audio.get("musicbrainz_albumid") or []):
                        hits.append(Path(entry.path))
            except OSError:
                continue

    walk(str(dest_root), 0)
    return hits


def cleanup_empty_dirs(root: Path) -> list[Path]:
    """Remove folders that are completely empty (and folders that only held such
    folders). Uses rmdir, which refuses anything non-empty, and never removes `root`."""
    removed: list[Path] = []
    for current, _dirs, _files in os.walk(root, topdown=False, followlinks=False):
        path = Path(current)
        if path == root or path.is_symlink():
            continue
        try:
            os.rmdir(path)
            removed.append(path)
        except OSError:
            continue
    return removed


class BatchManager:
    def __init__(
        self,
        batch_store: store.BatchStore,
        client: MBLike,
        music_root: Path,
        audit_path: Path,
        picard_pipe_dir: str = "",
        picard_library_root: str = "/music",
        dest_root: Path | None = None,
        after_saved=None,
    ) -> None:
        self.store = batch_store
        self.client = client
        self.root = Path(music_root).resolve()
        self.audit_path = Path(audit_path)
        self.picard_pipe_dir = picard_pipe_dir
        self.picard_library_root = picard_library_root
        self.dest_root = Path(dest_root).resolve() if dest_root else None
        # Optional async hook(folder, release_mbid) -> str | None, run once an album's
        # files are confirmed at their destination (used for the Lidarr hand-off).
        # It returns a note to record, or None if it's switched off; raising stops the batch.
        self.after_saved = after_saved
        # Optional async hook(directory, release_mbid) -> str | None, run just before an album is
        # tagged: a returned message means "don't import this unattended" (e.g. it's already in the library).
        self.before_import = None

        self.phase = "idle"  # idle | discovering | matching | processing
        self.progress: dict[str, Any] = {}
        self.events: deque[dict] = deque(maxlen=300)
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.last_result: str = ""

    # -- bookkeeping --------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def request_stop(self) -> None:
        self._stop.set()

    def _event(self, message: str, level: str = "info", path: str = "") -> None:
        self.events.append({"t": time.time(), "level": level, "message": message, "path": path})

    def audit(self, event: str, **data) -> None:
        line = json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, **data}, ensure_ascii=False)
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def audit_tail(self, lines: int = 200) -> list[str]:
        try:
            return self.audit_path.read_text(encoding="utf-8").splitlines()[-lines:]
        except OSError:
            return []

    def status(self, root: str | None = None) -> dict:
        return {
            "phase": self.phase,
            "busy": self.busy,
            "progress": self.progress,
            "stop_requested": self._stop.is_set(),
            "last_result": self.last_result,
            "counts": self.store.counts(root) if root is not None else None,
            "events": list(self.events)[-60:],
            "dest_configured": self.dest_root is not None,
        }

    def _start(self, phase: str, make_coro) -> None:
        if self.busy:
            raise RuntimeError("Another batch job is already running.")
        self._stop.clear()
        self.phase = phase
        self.progress = {"done": 0, "total": 0, "current": ""}
        self.last_result = ""

        async def runner():
            try:
                await make_coro()
            except BatchAbort as abort:
                self.last_result = f"Stopped: {abort}"
                self._event(self.last_result, "error")
                self.audit("abort", reason=str(abort))
            except Exception as error:  # a bug or an unexpected failure: stop safely
                self.last_result = f"Stopped on an unexpected error: {error}"
                self._event(self.last_result, "error")
                self.audit("error", reason=repr(error))
            finally:
                # Only one job runs at a time, so any row still "processing" belongs to this
                # one and was cut short: flag it rather than leave a misleading state.
                self.store.recover_interrupted()
                self.phase = "idle"
                self.progress = {**self.progress, "current": ""}

        self._task = asyncio.create_task(runner())

    def _abs(self, rel: str) -> Path:
        target = (self.root / rel).resolve()
        if target != self.root and not target.is_relative_to(self.root):
            raise ValueError("path outside library")
        return target

    def _rel(self, absolute: Path) -> str:
        rel = absolute.resolve().relative_to(self.root).as_posix()
        return "" if rel == "." else rel

    # -- discovery ----------------------------------------------------------

    def start_discovery(self, root_rel: str) -> None:
        self._start("discovering", lambda: self._discover(root_rel))

    async def _discover(self, root_rel: str) -> None:
        directory = self._abs(root_rel)
        self._event(f"Scanning {root_rel or '/'} for album folders…")
        found = await asyncio.to_thread(discovery.find_album_dirs, directory, self._stop.is_set)
        if self._stop.is_set():
            self.last_result = "Discovery stopped."
            return
        rels = [self._rel(p) for p in found]
        new, known = self.store.add_found(root_rel, rels)
        removed = self.store.forget_missing(root_rel, set(rels))
        self.progress = {"done": len(rels), "total": len(rels), "current": ""}
        self.last_result = f"Found {len(rels)} album folders ({new} new, {known} already known, {removed} no longer present)."
        self._event(self.last_result)
        self.audit("discovered", root=root_rel, found=len(rels), new=new)

    # -- matching -----------------------------------------------------------

    def start_matching(self, root_rel: str, rematch: list[str] | None = None) -> None:
        self._start("matching", lambda: self._match(root_rel, rematch))

    async def _match(self, root_rel: str, rematch: list[str] | None) -> None:
        for path in rematch or []:
            self.store.update(path, status=store.PENDING, message=None)
        pending = self.store.paths_with_status(root_rel, store.PENDING)
        self.progress = {"done": 0, "total": len(pending), "current": ""}
        self._event(f"Matching {len(pending)} albums against MusicBrainz…")
        errors = 0
        for index, path in enumerate(pending):
            if self._stop.is_set():
                self.last_result = f"Stopped after {index} of {len(pending)} albums."
                return
            self.progress = {"done": index, "total": len(pending), "current": path}
            try:
                await self._match_one(path)
                errors = 0
            except (httpx.HTTPError, asyncio.TimeoutError) as error:
                errors += 1
                self.store.update(path, message=f"Will retry: MusicBrainz error ({error.__class__.__name__}).")
                self._event(f"MusicBrainz error on {path}: {error.__class__.__name__}", "warn", path)
                if errors >= MAX_CONSECUTIVE_MB_ERRORS:
                    raise BatchAbort("MusicBrainz keeps failing. Try again later; progress so far is saved.")
        self.progress = {"done": len(pending), "total": len(pending), "current": ""}
        self.last_result = f"Matched {len(pending)} albums."
        self._event(self.last_result)

    async def _match_one(self, rel: str) -> None:
        directory = self._abs(rel)
        if not directory.is_dir():
            self.store.update(rel, status=store.PROBLEM, message="Folder no longer exists.")
            return
        album = await asyncio.to_thread(tags.scan_directory, directory, False)
        if album is None:
            self.store.update(rel, status=store.PROBLEM, message="No readable audio files in this folder.")
            return
        fingerprint = await asyncio.to_thread(discovery.fingerprint, directory)
        verdict = await evaluate_album(self.client, album)
        self.store.update(
            rel,
            status={"ready": store.READY, "review": store.REVIEW, "missing": store.MISSING}[verdict.status],
            artist=album.artist,
            title=album.title,
            year=(album.date or "")[:4],
            tracks=len(album.tracks),
            duration_ms=sum(t.length_ms or 0 for t in album.tracks),
            fingerprint=fingerprint,
            release_mbid=verdict.release_mbid,
            confidence=verdict.confidence,
            verdict={"reasons": verdict.reasons, "candidates": verdict.candidates},
            message=verdict.reasons[0] if verdict.reasons else None,
        )

    # -- processing (the only part that writes) ------------------------------

    def start_processing(self, root_rel: str, limit: int, clear_picard: bool) -> None:
        if not picard.is_connected(self.picard_pipe_dir):
            raise RuntimeError("Picard isn't reachable.")
        if not clear_picard:
            raise RuntimeError("Confirm that Picard's file lists can be cleared before starting.")
        self._start("processing", lambda: self._process(root_rel, max(1, limit)))

    async def _process(self, root_rel: str, limit: int) -> None:
        queue = self.store.paths_with_status(root_rel, store.READY, limit=limit)
        self.progress = {"done": 0, "total": len(queue), "current": ""}
        self.audit("batch_start", root=root_rel, albums=len(queue))
        self._event(f"Processing {len(queue)} confident album(s), one at a time. Clearing Picard first.")
        await self._send(("REMOVE_ALL", ""))  # start from an empty Picard so "save matched" can only touch our album
        await asyncio.sleep(1.0)
        done = 0
        for index, path in enumerate(queue):
            if self._stop.is_set():
                self.last_result = f"Stopped before album {index + 1}. {done} processed."
                self.audit("batch_stop", done=done)
                return
            self.progress = {"done": index, "total": len(queue), "current": path}
            await self._process_one(path)
            done += 1
            await asyncio.sleep(PAUSE_BETWEEN_ALBUMS)
        self.progress = {"done": len(queue), "total": len(queue), "current": ""}
        self.last_result = f"Finished: {done} album(s) tagged and saved by Picard."
        self._event(self.last_result)
        self.audit("batch_done", done=done)

    async def _send(self, *commands: tuple[str, str]) -> None:
        try:
            await asyncio.to_thread(picard.send, self.picard_pipe_dir, *commands)
        except picard.PicardUnavailable as error:
            raise BatchAbort(f"Lost contact with Picard: {error}")

    def _fail(self, rel: str, message: str, status: str = store.PROBLEM) -> None:
        self.store.update(rel, status=status, message=message)
        self._event(f"{rel}: {message}", "error", rel)
        self.audit("album_failed", path=rel, message=message)

    async def _process_one(self, rel: str) -> None:
        row = self.store.get(rel)
        if not row or row["status"] != store.READY or not row["release_mbid"]:
            return
        directory = self._abs(rel)
        mbid = row["release_mbid"]
        self._event(f"Verifying {rel}", path=rel)

        # 1. Has anything changed since it was matched?
        if not directory.is_dir() or await asyncio.to_thread(discovery.fingerprint, directory) != row["fingerprint"]:
            self.store.update(rel, status=store.PENDING, message="Changed since it was matched. Re-matching needed.")
            self._event(f"{rel}: changed since it was matched, skipped", "warn", rel)
            return

        # 2. Re-fetch the release and re-judge from scratch; never act on a cached verdict alone.
        album = await asyncio.to_thread(tags.scan_directory, directory, False)
        if album is None:
            return self._fail(rel, "No readable audio files.")
        release = parse_release(await self.client.lookup_release(mbid))
        plan = match_tracks(album.tracks, release)
        check = evaluate_candidate(album, release, plan, 100.0)
        # Unattended albums must be fully confident. One you explicitly picked may differ
        # in name, but its tracks must still match exactly.
        approved = (row.get("verdict") or {}).get("approved") == mbid
        if not (check.confident or (approved and check.track_exact)):
            self.store.update(rel, status=store.REVIEW, message="No longer a confident match: " + "; ".join(check.problems))
            self._event(f"{rel}: no longer confident, moved to Review", "warn", rel)
            return

        if self.before_import is not None:
            note = await self.before_import(directory, mbid)
            if note:
                self._fail(rel, note)
                return

        # 3. Tag, load, save, verify.
        started = time.time()
        self.store.update(rel, status=store.PROCESSING, message="Tagging…")
        self.audit("album_start", path=rel, release=mbid, files=len(album.tracks))
        try:
            written = await asyncio.to_thread(releasetags.write_tags, plan)
        except releasetags.TagWriteError as error:
            self._fail(rel, str(error))
            raise BatchAbort(f"Couldn't tag {rel}: {error}")
        self.audit("tagged", path=rel, files=written)

        picard_path = picard.to_picard_path(directory, self.root, self.picard_library_root)
        await self._send(("LOAD", picard_path))
        self.audit("loaded", path=rel, picard_path=picard_path)
        self.store.update(rel, message="Loaded in Picard, waiting for it to match…")
        await asyncio.sleep(min(WARMUP_MAX_SECONDS, WARMUP_BASE_SECONDS + WARMUP_PER_TRACK_SECONDS * len(album.tracks)))

        deadline = time.monotonic() + SAVE_TIMEOUT_SECONDS
        last_save = 0.0
        remaining = len(album.tracks)
        while time.monotonic() < deadline:
            if time.monotonic() - last_save >= SAVE_RESEND_SECONDS:
                await self._send(("SAVE_MATCHED", ""))
                last_save = time.monotonic()
                self.audit("save_sent", path=rel)
                self.store.update(rel, message="Saving in Picard…")
            await asyncio.sleep(POLL_SECONDS)
            remaining = await asyncio.to_thread(discovery.count_audio, directory) if directory.exists() else 0
            if remaining == 0:
                break
        if remaining:
            self._fail(rel, f"{remaining} audio file(s) are still in the folder {SAVE_TIMEOUT_SECONDS:.0f}s after saving. Picard probably didn't match them.")
            raise BatchAbort(f"{rel} wasn't fully moved by Picard. Check Picard before continuing.")

        # 4. Verify they landed where Picard should have put them.
        destination = "destination not verified (PICARD_DEST_ROOT isn't set)"
        if self.dest_root is not None:
            hits = await asyncio.to_thread(locate_moved, self.dest_root, started, mbid)
            if len(hits) < len(album.tracks):
                self._fail(rel, f"The folder emptied but only {len(hits)} of {len(album.tracks)} files were found at the destination with the right release ID.")
                raise BatchAbort(f"Couldn't confirm where {rel} went. Check {self.dest_root} before continuing.")
            destination = str(hits[0].parent)
        await self._send(("REMOVE_SAVED", ""))
        self.store.update(rel, status=store.DONE, processed=time.time(), message=f"Saved by Picard. {destination}")
        self._event(f"Done: {rel}", path=rel)
        self.audit("album_done", path=rel, release=mbid, destination=destination)

        if self.after_saved is not None and self.dest_root is not None and hits:
            try:
                note = await self.after_saved(hits[0].parent, mbid)
            except Exception as error:  # noqa: BLE001 - any failure here needs a human
                self.store.update(rel, message=f"Saved by Picard. {destination}. Lidarr: {error}")
                self.audit("lidarr_failed", path=rel, error=str(error))
                raise BatchAbort(f"Lidarr hand-off failed for {rel}: {error}") from error
            if note:
                self.store.update(rel, message=f"Saved by Picard. {destination}. Lidarr: {note}")
                self.audit("lidarr_done", path=rel, note=note)
                self._event(f"Lidarr: {note}", path=rel)

    # -- maintenance ----------------------------------------------------------

    def reconcile(self, root_rel: str) -> int:
        """Anything whose folder no longer holds audio has been processed (by this
        app, or by hand in Picard): mark it done so lists stay truthful."""
        changed = 0
        for status in (store.PENDING, store.READY, store.REVIEW, store.MISSING, store.IN_PICARD, store.PROBLEM, store.SKIPPED):
            for rel in self.store.paths_with_status(root_rel, status):
                directory = self._abs(rel)
                if not directory.is_dir() or discovery.count_audio(directory) == 0:
                    self.store.update(rel, status=store.DONE, message="No audio left in this folder (processed).", processed=time.time())
                    changed += 1
        return changed

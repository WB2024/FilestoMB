"""Find album folders under a root, whatever the nesting (Unmanaged/A/Artist/Album,
flat, or multi-disc), without ever descending into an album once found."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from ..tags import AUDIO_EXTENSIONS

# "CD1", "Disc 2", "disk_03", "Volume 1" ...
DISC_RE = re.compile(r"^(cd|disc|disk|dvd|vol|volume)[\s._-]*0*\d+\b", re.IGNORECASE)
SKIP_DIRS = {"@eaDir", "$RECYCLE.BIN", "System Volume Information", "lost+found", "__MACOSX"}


def _is_audio(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTENSIONS


def _scan(directory: Path):
    try:
        return list(os.scandir(directory))
    except OSError:
        return []


def has_audio_directly(directory: Path) -> bool:
    return any(e.is_file() and _is_audio(e.name) for e in _scan(directory))


def find_album_dirs(root: Path, cancelled: Callable[[], bool] = lambda: False) -> list[Path]:
    """Album folder = a folder holding audio files directly, or a folder whose
    disc sub-folders (CD1, CD2...) hold them. Hidden/system folders and
    symlinks are skipped."""
    found: list[Path] = []

    def walk(directory: Path) -> None:
        if cancelled():
            return
        entries = _scan(directory)
        if any(e.is_file() and _is_audio(e.name) for e in entries):
            found.append(directory)
            return
        subdirs = [
            e for e in entries
            if e.is_dir(follow_symlinks=False) and not e.name.startswith(".") and e.name not in SKIP_DIRS
        ]
        disc_dirs = [e for e in subdirs if DISC_RE.match(e.name)]
        if disc_dirs and any(has_audio_directly(Path(e.path)) for e in disc_dirs):
            found.append(directory)
            return
        for entry in sorted(subdirs, key=lambda e: e.name.lower()):
            walk(Path(entry.path))

    walk(Path(root))
    return found


def fingerprint(album_dir: Path) -> str:
    """Cheap change detector over the album's audio files (names, sizes, mtimes).
    Compared again right before anything is written, so a folder that changed
    since it was matched is never processed on stale information."""
    digest = hashlib.sha1()
    for current, dirs, files in os.walk(album_dir):
        dirs.sort()
        for name in sorted(files):
            if not _is_audio(name):
                continue
            try:
                st = os.stat(os.path.join(current, name))
            except OSError:
                continue
            rel = os.path.relpath(os.path.join(current, name), album_dir)
            digest.update(f"{rel}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def count_audio(album_dir: Path) -> int:
    return sum(1 for _, _, files in os.walk(album_dir) for f in files if _is_audio(f))

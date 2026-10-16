"""Awareness of the finished ("Clean") library.

* An index (sqlite, in /config) of which MusicBrainz releases live in which
  folders, kept fresh by re-reading only folders whose files changed.
* A quality summary and comparison for two copies of the same release.
* "Replace" never deletes: the existing files are *moved* into an archive
  folder on the same filesystem, so the swap can always be undone by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path

import mutagen

from .tags import AUDIO_EXTENSIONS

LOSSLESS_SUFFIXES = {".flac", ".wv", ".ape"}
# Rough "how many kbps of MP3 is this worth" so lossy codecs can be compared fairly.
CODEC_FACTOR = {"MP3": 1.0, "AAC": 1.3, "Vorbis": 1.2, "Opus": 1.5}
SIMILAR_TOLERANCE = 1.10


class LibraryError(Exception):
    """Safe to show to the user."""


# ---------------------------------------------------------------- index


def _hidden(name: str) -> bool:
    return name.startswith(".")


class LibraryIndex:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.lock = threading.Lock()  # one refresh at a time
        self.building = False
        self.progress: dict = {}
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def _init(self) -> None:
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS folders (path TEXT PRIMARY KEY, sig TEXT, audio INTEGER, releases TEXT, groups TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

    def meta(self, key: str, default: str = "") -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def _set_meta(self, db: sqlite3.Connection, key: str, value: str) -> None:
        db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def stats(self) -> dict:
        with self._connect() as db:
            folders = db.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
        return {"folders": folders, "root": self.meta("root"), "last_built": float(self.meta("last_built", "0") or 0),
                "building": self.building, "progress": dict(self.progress)}

    # -- reading one folder ------------------------------------------------

    @staticmethod
    def _audio_entries(directory: str) -> list[os.DirEntry]:
        try:
            return sorted((e for e in os.scandir(directory) if e.is_file() and Path(e.name).suffix.lower() in AUDIO_EXTENSIONS), key=lambda e: e.name)
        except OSError:
            return []

    @staticmethod
    def _signature(entries: list[os.DirEntry]) -> str:
        h = hashlib.sha1()
        for e in entries:
            try:
                st = e.stat()
            except OSError:
                continue
            h.update(f"{e.name}|{st.st_size}|{st.st_ctime_ns}\n".encode())
        return h.hexdigest()

    @staticmethod
    def _read_ids(entries: list[os.DirEntry]) -> tuple[Counter, Counter]:
        releases: Counter = Counter()
        groups: Counter = Counter()
        for e in entries:
            try:
                audio = mutagen.File(e.path, easy=True)
            except Exception:  # noqa: BLE001 - unreadable files simply aren't indexed
                continue
            if not audio:
                continue
            for value in (audio.get("musicbrainz_albumid") or [])[:1]:
                releases[value.lower()] += 1
            for value in (audio.get("musicbrainz_releasegroupid") or [])[:1]:
                groups[value.lower()] += 1
        return releases, groups

    def _index_folder(self, db: sqlite3.Connection, root: Path, directory: str, force: bool = False) -> bool:
        """Re-read one folder if its files changed. Returns True when it was re-read."""
        rel = Path(directory).relative_to(root).as_posix()
        entries = self._audio_entries(directory)
        if not entries:
            db.execute("DELETE FROM folders WHERE path=?", (rel,))
            return False
        sig = self._signature(entries)
        row = db.execute("SELECT sig FROM folders WHERE path=?", (rel,)).fetchone()
        if row and row[0] == sig and not force:
            return False
        releases, groups = self._read_ids(entries)
        db.execute("INSERT OR REPLACE INTO folders(path,sig,audio,releases,groups) VALUES(?,?,?,?,?)",
                   (rel, sig, len(entries), json.dumps(releases), json.dumps(groups)))
        return True

    def refresh_folder(self, root: Path, folder: Path) -> None:
        """Re-index just one folder (e.g. one Picard has just saved into)."""
        root, folder = Path(root).resolve(), Path(folder).resolve()
        try:
            folder.relative_to(root)
        except ValueError:
            return
        with self.lock, self._connect() as db:
            self._index_folder(db, root, str(folder), force=True)

    def refresh(self, root: Path, skip: Path | None = None) -> None:
        """Walk the library, re-reading only folders that changed and forgetting vanished ones."""
        root = Path(root).resolve()
        with self.lock:
            self.building = True
            self.progress = {"folders_seen": 0, "folders_read": 0}
            try:
                with self._connect() as db:
                    if self.meta("root") != str(root):  # a different library: start clean
                        db.execute("DELETE FROM folders")
                    seen: set[str] = set()
                    for directory, subdirs, _files in os.walk(root):
                        subdirs[:] = [d for d in subdirs if not _hidden(d) and not (skip and Path(directory, d) == skip)]
                        if self._audio_entries(directory):
                            seen.add(Path(directory).relative_to(root).as_posix())
                            self.progress["folders_seen"] += 1
                            if self._index_folder(db, root, directory):
                                self.progress["folders_read"] += 1
                            if self.progress["folders_seen"] % 50 == 0:
                                db.commit()
                    for (path,) in db.execute("SELECT path FROM folders").fetchall():
                        if path not in seen:
                            db.execute("DELETE FROM folders WHERE path=?", (path,))
                    self._set_meta(db, "root", str(root))
                    self._set_meta(db, "last_built", str(time.time()))
            finally:
                self.building = False

    # -- lookups -----------------------------------------------------------

    def _find(self, column: str, mbid: str) -> list[tuple[str, int, int]]:
        mbid = mbid.lower()
        found = []
        with self._connect() as db:
            for path, audio, data in db.execute(f"SELECT path, audio, {column} FROM folders").fetchall():  # noqa: S608 - column is internal
                count = json.loads(data).get(mbid, 0)
                if count:
                    found.append((path, count, audio))
        return sorted(found)

    def find_release(self, mbid: str) -> list[tuple[str, int, int]]:
        """(folder relative to the library root, files with this release, audio files in the folder)."""
        return self._find("releases", mbid)

    def find_group(self, mbid: str) -> list[tuple[str, int, int]]:
        return self._find("groups", mbid)


# ---------------------------------------------------------------- quality


def _codec(path: Path, info) -> tuple[str, bool]:
    suffix = path.suffix.lower()
    if suffix == ".flac":
        return "FLAC", True
    if suffix == ".mp3":
        return "MP3", False
    if suffix == ".opus":
        return "Opus", False
    if suffix == ".ogg":
        return "Vorbis", False
    if suffix == ".wv":
        return "WavPack", True
    if suffix == ".ape":
        return "APE", True
    if suffix == ".m4a":
        if str(getattr(info, "codec", "")).lower().startswith("alac"):
            return "ALAC", True
        return "AAC", False
    return suffix.lstrip(".").upper(), False


def summarize(files: list[Path]) -> dict:
    """What a set of audio files is worth: format, resolution or bitrate, size, length."""
    formats: Counter = Counter()
    lossless_all, bits, rates, kbps, seconds, size, readable = True, [], [], [], 0.0, 0, 0
    for path in files:
        try:
            audio = mutagen.File(path)
            size += path.stat().st_size
        except Exception:  # noqa: BLE001
            continue
        if audio is None or audio.info is None:
            continue
        readable += 1
        name, lossless = _codec(path, audio.info)
        formats[name] += 1
        lossless_all &= lossless
        if getattr(audio.info, "bits_per_sample", 0):
            bits.append(audio.info.bits_per_sample)
        if getattr(audio.info, "sample_rate", 0):
            rates.append(audio.info.sample_rate)
        if getattr(audio.info, "bitrate", 0):
            kbps.append(audio.info.bitrate / 1000)
        seconds += getattr(audio.info, "length", 0) or 0
    return {
        "tracks": readable,
        "formats": dict(formats),
        "format": " + ".join(f"{k}" for k, _ in formats.most_common()) or "unknown",
        "lossless": bool(readable) and lossless_all,
        "bits": min(bits) if bits else 0,
        "sample_rate": min(rates) if rates else 0,
        "kbps": round(sum(kbps) / len(kbps)) if kbps else 0,
        "seconds": round(seconds),
        "bytes": size,
    }


def describe(q: dict) -> str:
    parts = [q["format"]]
    if q["lossless"]:
        if q["bits"] or q["sample_rate"]:
            parts.append(f"{q['bits'] or '?'}-bit/{q['sample_rate'] / 1000:g} kHz")
    elif q["kbps"]:
        parts.append(f"{q['kbps']} kbps")
    parts.append(f"{q['tracks']} track{'s' if q['tracks'] != 1 else ''}")
    parts.append(f"{q['bytes'] / 1e6:.0f} MB")
    return " · ".join(parts)


def _effective_kbps(q: dict) -> float:
    main = max(q["formats"], key=q["formats"].get) if q["formats"] else ""
    return q["kbps"] * CODEC_FACTOR.get(main, 1.0)


def compare(existing: dict, new: dict) -> dict:
    """Which copy is better? Returns {"verdict": existing_better|new_better|similar, "reasons": [...]}.
    Lossless beats lossy; then resolution (lossless) or codec-weighted bitrate (lossy)."""
    reasons: list[str] = []
    verdict = "similar"
    if existing["lossless"] != new["lossless"]:
        verdict = "existing_better" if existing["lossless"] else "new_better"
        winner, loser = (existing, new) if existing["lossless"] else (new, existing)
        reasons.append(f"{'The existing copy' if winner is existing else 'The new copy'} is lossless ({winner['format']}); the other is lossy ({loser['format']}).")
    elif existing["lossless"]:
        e, n = (existing["bits"], existing["sample_rate"]), (new["bits"], new["sample_rate"])
        if n > e:
            verdict = "new_better"
            reasons.append(f"The new copy has higher resolution ({describe(new).split(' · ')[1]} vs {describe(existing).split(' · ')[1]}).")
        elif e > n:
            verdict = "existing_better"
            reasons.append(f"The existing copy has higher resolution ({describe(existing).split(' · ')[1]} vs {describe(new).split(' · ')[1]}).")
        else:
            reasons.append("Both are lossless at the same resolution.")
    else:
        e, n = _effective_kbps(existing), _effective_kbps(new)
        if n > e * SIMILAR_TOLERANCE:
            verdict = "new_better"
            reasons.append(f"The new copy has a higher bitrate ({new['format']} {new['kbps']} kbps vs {existing['format']} {existing['kbps']} kbps).")
        elif e > n * SIMILAR_TOLERANCE:
            verdict = "existing_better"
            reasons.append(f"The existing copy has a higher bitrate ({existing['format']} {existing['kbps']} kbps vs {new['format']} {new['kbps']} kbps).")
        else:
            reasons.append("Both are lossy at a similar bitrate.")
    if existing["tracks"] != new["tracks"]:
        more = "existing" if existing["tracks"] > new["tracks"] else "new"
        reasons.append(f"Track counts differ: {existing['tracks']} existing vs {new['tracks']} new. The {more} copy has more.")
    if existing["seconds"] and new["seconds"] and abs(existing["seconds"] - new["seconds"]) > 10 and existing["tracks"] == new["tracks"]:
        reasons.append(f"Running time differs by {abs(existing['seconds'] - new['seconds'])}s.")
    return {"verdict": verdict, "reasons": reasons}


# ---------------------------------------------------------------- replace (archive, never delete)


def release_files(folder: Path, release_mbid: str) -> tuple[list[Path], list[Path]]:
    """(audio files in the folder carrying this release, all audio files in the folder)."""
    mine, everything = [], []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        everything.append(entry)
        try:
            audio = mutagen.File(entry, easy=True)
        except Exception:  # noqa: BLE001
            continue
        if audio and release_mbid.lower() in [v.lower() for v in audio.get("musicbrainz_albumid") or []]:
            mine.append(entry)
    return mine, everything


def archive_existing(library_root: Path, archive_root: Path, folder: Path, release_mbid: str, stamp: str) -> dict:
    """Move the existing copy of a release out of the library into `archive_root/<stamp>/...`.

    Moves the whole folder when every audio file in it is this release; otherwise only
    this release's audio files, so another edition sharing the folder stays put."""
    library_root, archive_root, folder = Path(library_root).resolve(), Path(archive_root).resolve(), Path(folder).resolve()
    try:
        relative = folder.relative_to(library_root)
    except ValueError as error:
        raise LibraryError("That folder isn't inside the Clean library.") from error
    if not folder.is_dir():
        raise LibraryError("That folder no longer exists.")
    if archive_root == library_root or archive_root == folder or folder in archive_root.parents:
        raise LibraryError("The replaced-albums folder can't contain the album being replaced.")
    mine, everything = release_files(folder, release_mbid)
    if not mine:
        raise LibraryError("That folder has no files for this release any more. Nothing was moved.")
    target = archive_root / stamp / relative
    archive_root.mkdir(parents=True, exist_ok=True)
    if os.stat(archive_root).st_dev != os.stat(library_root).st_dev:
        raise LibraryError("The replaced-albums folder is on a different filesystem, so moving would mean copying. Pick a folder beside the library.")
    if target.exists():
        raise LibraryError(f"{target} already exists. Try again in a moment.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if len(mine) == len(everything):
        os.rename(folder, target)
        return {"archived_to": str(target), "files": len(mine), "whole_folder": True}
    target.mkdir()
    for path in mine:
        os.rename(path, target / path.name)
    return {"archived_to": str(target), "files": len(mine), "whole_folder": False}

"""ReplayGain 2.0 via rsgain, mirroring Picard's "ReplayGain 2.0" plugin.

The plugin only scans (``rsgain custom -s s``) and leaves Picard to write the
tags on save. FilesToMB runs the same scan with the same options but writes the
tags itself (``-s i``) once Picard has saved the album, after showing the
numbers first. Only audio files tagged with the given release are touched.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import mutagen
from mutagen.id3 import ID3, TXXX

from .tags import AUDIO_EXTENSIONS

CLIP_MODES = {"n", "p", "a"}
OPUS_MODES = {"d", "r", "s"}  # standard tags / R128 tags / R128 referenced to -23 LUFS
RUN_TIMEOUT_SECONDS = 600


class ReplayGainError(Exception):
    """Safe to show to the user."""


@dataclass
class Options:
    album: bool = True
    true_peak: bool = True
    reference_tag: bool = True
    target: float = -18.0
    clip_mode: str = "p"
    max_peak: float = 0.0
    opus_mode: str = "d"

    def validate(self) -> None:
        if not -30 <= self.target <= -5:
            raise ReplayGainError("Target loudness must be between -30 and -5 LUFS.")
        if self.clip_mode not in CLIP_MODES:
            raise ReplayGainError("Unknown clipping protection mode.")
        if self.opus_mode not in OPUS_MODES:
            raise ReplayGainError("Unknown Opus mode.")
        if not -20 <= self.max_peak <= 20:
            raise ReplayGainError("Max peak must be between -20 and 20 dB.")


@dataclass
class Row:
    filename: str
    loudness: str
    gain: str
    peak: str
    peak_db: str


@dataclass
class Result:
    tracks: list[Row] = field(default_factory=list)
    album: Row | None = None
    wrote: bool = False
    verified: int = 0
    notes: list[str] = field(default_factory=list)


def check_binary(path: str) -> Path:
    if not path:
        raise ReplayGainError("Set the path to rsgain in Settings first.")
    binary = Path(path)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ReplayGainError(f"rsgain isn't at {path} (or isn't executable). Check that folder is mounted into the container.")
    return binary


def build_command(binary: Path, options: Options, files: list[Path], write: bool) -> list[str]:
    cmd = [str(binary), "custom", "-O", "-s", "i" if write else "s"]
    if options.album:
        cmd.append("-a")
    if options.true_peak:
        cmd.append("-t")
    cmd += ["-l", f"{options.target:g}", "-c", options.clip_mode, "-m", f"{options.max_peak:g}", "-o", options.opus_mode]
    return cmd + [str(f) for f in files]


def parse_output(output: str, expect_tracks: int, album: bool) -> tuple[list[Row], Row | None]:
    """rsgain -O prints a header line, one row per file, then an album row."""
    rows = []
    for line in output.splitlines():
        cols = line.split("\t")
        if len(cols) == 7 and cols[0] != "Filename":
            rows.append(Row(cols[0], cols[1], cols[2], cols[3], cols[4].strip()))
    want = expect_tracks + (1 if album else 0)
    if len(rows) != want:
        raise ReplayGainError(f"rsgain printed {len(rows)} result rows, expected {want}. Output: {output.strip()[-300:]}")
    return (rows[:-1], rows[-1]) if album else (rows, None)


def audio_files_for_release(folder: Path, release_mbid: str | None) -> list[Path]:
    """Audio files directly in the folder, limited to this release when an ID is given
    (a folder can also hold another edition, which must not skew the album gain)."""
    files = []
    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if release_mbid:
            try:
                audio = mutagen.File(entry, easy=True)
            except Exception:  # noqa: BLE001 - unreadable files are skipped
                continue
            if not audio or release_mbid.lower() not in [v.lower() for v in audio.get("musicbrainz_albumid") or []]:
                continue
        files.append(entry)
    return files


def _set_reference_loudness(path: Path, target: float) -> bool:
    """Picard's plugin also writes the reference loudness; rsgain doesn't."""
    text = f"{target:.2f} LUFS"
    stat = path.stat()
    try:
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            tags = ID3(path)
            tags.setall("TXXX:REPLAYGAIN_REFERENCE_LOUDNESS", [TXXX(encoding=3, desc="REPLAYGAIN_REFERENCE_LOUDNESS", text=text)])
            tags.save(path)
        elif suffix == ".m4a":
            audio = mutagen.File(path)
            audio["----:com.apple.iTunes:REPLAYGAIN_REFERENCE_LOUDNESS"] = [text.encode()]
            audio.save()
        elif suffix in {".flac", ".ogg", ".opus"}:
            audio = mutagen.File(path)
            audio["REPLAYGAIN_REFERENCE_LOUDNESS"] = [text]
            audio.save()
        else:
            return False
        return True
    finally:
        try:  # best effort: needs ownership of the file, which Picard's saved files may not give us
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        except OSError:
            pass


def _has_track_gain(path: Path) -> bool:
    try:
        audio = mutagen.File(path, easy=False)
    except Exception:  # noqa: BLE001
        return False
    if audio is None or audio.tags is None:
        return False
    keys = {str(k).lower() for k in audio.tags.keys()}
    return any(("replaygain_track_gain" in k) or ("r128_track_gain" in k) for k in keys)


def run(binary: Path, options: Options, files: list[Path], write: bool) -> Result:
    options.validate()
    if not files:
        raise ReplayGainError("No audio files tagged with this release were found in that folder.")
    cmd = build_command(binary, options, files, write)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as error:
        raise ReplayGainError("rsgain took longer than 10 minutes and was stopped.") from error
    if proc.returncode:
        raise ReplayGainError(f"rsgain failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()[-300:]}")
    tracks, album = parse_output(proc.stdout, len(files), options.album)
    result = Result(tracks=tracks, album=album, wrote=write)
    if write:
        if options.reference_tag and options.opus_mode == "d":
            skipped = sum(1 for f in files if not _set_reference_loudness(f, options.target))
            if skipped:
                result.notes.append(f"Reference loudness tag skipped for {skipped} file(s) of a type it doesn't support.")
        result.verified = sum(1 for f in files if _has_track_gain(f))
        if result.verified != len(files):
            result.notes.append(f"Only {result.verified} of {len(files)} files show ReplayGain tags afterwards.")
    return result

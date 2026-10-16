"""AcoustID fingerprints computed here with fpcalc (Chromaprint), no lookups.

Picard's remote FINGERPRINT command also looks files up on AcoustID and can
re-match them to other tracks, so FilesToMB fingerprints the audio itself and
writes the standard ``ACOUSTID_FINGERPRINT`` tag, which Picard keeps. Nothing
is matched, submitted or looked up.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import mutagen
from mutagen.id3 import ID3, TXXX

FPCALC_TIMEOUT_SECONDS = 120
ID3_DESC = "Acoustid Fingerprint"
MP4_KEY = "----:com.apple.iTunes:Acoustid Fingerprint"
VORBIS_KEY = "ACOUSTID_FINGERPRINT"


class FingerprintError(Exception):
    """Safe to show to the user."""


def find_fpcalc() -> str | None:
    return os.environ.get("FPCALC") or shutil.which("fpcalc")


def calculate(path: Path, fpcalc: str) -> str:
    try:
        proc = subprocess.run([fpcalc, "-json", str(path)], capture_output=True, text=True, timeout=FPCALC_TIMEOUT_SECONDS, check=False)  # noqa: S603
    except subprocess.TimeoutExpired as error:
        raise FingerprintError(f"{path.name}: fpcalc timed out.") from error
    if proc.returncode:
        raise FingerprintError(f"{path.name}: {(proc.stderr or proc.stdout).strip()[-200:] or 'fpcalc failed'}")
    try:
        fingerprint = json.loads(proc.stdout)["fingerprint"]
    except (ValueError, KeyError) as error:
        raise FingerprintError(f"{path.name}: unexpected fpcalc output.") from error
    if not fingerprint:
        raise FingerprintError(f"{path.name}: no fingerprint produced (file too short?).")
    return fingerprint


def write_tag(path: Path, fingerprint: str) -> None:
    suffix = path.suffix.lower()
    try:
        if suffix == ".mp3":
            try:
                tags = ID3(path)
            except mutagen.id3.ID3NoHeaderError:
                tags = ID3()
            tags.setall(f"TXXX:{ID3_DESC}", [TXXX(encoding=3, desc=ID3_DESC, text=fingerprint)])
            tags.save(path)
        elif suffix == ".m4a":
            audio = mutagen.File(path)
            audio[MP4_KEY] = [fingerprint.encode()]
            audio.save()
        elif suffix in {".flac", ".ogg", ".opus", ".wv", ".ape"}:
            audio = mutagen.File(path)
            if audio.tags is None:
                audio.add_tags()
            audio[VORBIS_KEY] = [fingerprint] if suffix in {".flac", ".ogg", ".opus"} else fingerprint
            audio.save()
        else:
            raise FingerprintError(f"{path.name}: this file type isn't supported.")
    except (OSError, mutagen.MutagenError) as error:
        raise FingerprintError(f"{path.name}: couldn't write the tag ({error}).") from error

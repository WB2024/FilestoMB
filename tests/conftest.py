from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture
def make_flac(tmp_path: Path):
    """Return a factory that writes a tiny, real, tagged FLAC file."""
    if FFMPEG is None:
        pytest.skip("ffmpeg is required to generate test audio fixtures")

    counter = {"n": 0}

    def _make(tags: dict[str, str], directory: Path | None = None) -> Path:
        counter["n"] += 1
        target_dir = directory or tmp_path
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"track{counter['n']}.flac"
        subprocess.run(
            [
                FFMPEG,
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.1",
                "-y",
                str(path),
                "-loglevel",
                "error",
            ],
            check=True,
        )

        import mutagen

        audio = mutagen.File(path, easy=True)
        for key, value in tags.items():
            audio[key] = value
        audio.save()
        return path

    return _make

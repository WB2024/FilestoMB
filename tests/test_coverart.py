from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from filestomb import coverart
from filestomb.models import Track

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is required for these fixtures")


def _make_cover_image(path: Path) -> Path:
    subprocess.run(
        [FFMPEG, "-f", "lavfi", "-i", "color=c=blue:s=8x8", "-frames:v", "1", "-y", str(path), "-loglevel", "error"],
        check=True,
    )
    return path


def _make_bare_audio(path: Path) -> Path:
    subprocess.run(
        [FFMPEG, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.1", "-y", str(path), "-loglevel", "error"],
        check=True,
    )
    return path


def _embed_cover(audio_path: Path, cover_path: Path) -> Path:
    output = audio_path.with_name(f"withart{audio_path.suffix}")
    subprocess.run(
        [
            FFMPEG,
            "-i", str(audio_path),
            "-i", str(cover_path),
            "-map", "0:a",
            "-map", "1",
            "-c:a", "copy",
            "-c:v", "png",
            "-disposition:v", "attached_pic",
            "-y", str(output),
            "-loglevel", "error",
        ],
        check=True,
    )
    return output


@pytest.mark.parametrize("suffix", [".flac", ".mp3", ".m4a"])
def test_extract_embedded_cover_across_formats(tmp_path: Path, suffix: str) -> None:
    cover = _make_cover_image(tmp_path / "cover.png")
    bare = _make_bare_audio(tmp_path / f"bare{suffix}")
    track_path = _embed_cover(bare, cover)

    extracted = coverart.extract_embedded_cover(track_path)

    assert extracted is not None
    assert extracted.exists()
    assert extracted.stat().st_size > 0
    extracted.unlink()


def test_extract_embedded_cover_returns_none_without_art(tmp_path: Path) -> None:
    bare = _make_bare_audio(tmp_path / "bare.flac")

    assert coverart.extract_embedded_cover(bare) is None


def test_find_cover_file_matches_conventional_names(tmp_path: Path) -> None:
    _make_cover_image(tmp_path / "cover.png")

    found = coverart.find_cover_file(tmp_path)

    assert found == tmp_path / "cover.png"


def test_find_cover_file_ignores_unrelated_images(tmp_path: Path) -> None:
    _make_cover_image(tmp_path / "random-photo.png")

    assert coverart.find_cover_file(tmp_path) is None


def test_find_or_extract_cover_prefers_standalone_file(tmp_path: Path) -> None:
    cover = _make_cover_image(tmp_path / "cover.png")
    bare = _make_bare_audio(tmp_path / "bare.flac")
    track_path = _embed_cover(bare, cover)

    track = Track(path=track_path, title="Song", artist="Artist", album="Album", album_artist="Artist")

    result = coverart.find_or_extract_cover(tmp_path, [track])

    # Both a standalone cover.png and embedded art exist here; the standalone
    # file should win without needing to touch the embedded extraction path.
    assert result == cover


def test_find_or_extract_cover_falls_back_to_embedded_art(tmp_path: Path) -> None:
    cover = _make_cover_image(tmp_path / "cover-src.png")
    bare = _make_bare_audio(tmp_path / "bare.flac")
    track_path = _embed_cover(bare, cover)

    track = Track(path=track_path, title="Song", artist="Artist", album="Album", album_artist="Artist")

    result = coverart.find_or_extract_cover(tmp_path, [track])

    assert result is not None
    assert result.exists()
    result.unlink()


def test_find_or_extract_cover_returns_none_when_nothing_found(tmp_path: Path) -> None:
    bare = _make_bare_audio(tmp_path / "bare.flac")
    track = Track(path=bare, title="Song", artist="Artist", album="Album", album_artist="Artist")

    assert coverart.find_or_extract_cover(tmp_path, [track]) is None

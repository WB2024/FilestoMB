"""Best-effort local cover art discovery.

MusicBrainz's Cover Art Archive has no public upload API. Uploading only
happens through a real, logged-in browser session on musicbrainz.org: its
upload wizard talks to the Internet Archive's S3-like API using temporary,
session-scoped credentials the server hands out. That's confirmed straight
from musicbrainz-server's source -- Controller::WS::js's cover_art_upload
action calls cookie_login_or_error, which requires an actual website
session cookie, not an OAuth2 access token. There's no way for an external
app to perform that upload itself, so this module's job is narrower: find
the right local image and make it effortless to drag into that page once
it's open (see screens/submit.py).
"""

from __future__ import annotations

import base64
import platform
import subprocess
import tempfile
from pathlib import Path

import mutagen
import mutagen.flac
import mutagen.id3
import mutagen.mp4

from .models import Track

COVER_STEMS = {
    "cover",
    "front",
    "folder",
    "albumart",
    "album art",
    "artwork",
    "cover-front",
    "front-cover",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def find_cover_file(directory: Path) -> Path | None:
    """Look for a conventionally-named standalone image file in the album directory."""
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return None
    for path in entries:
        if (
            path.is_file()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and path.stem.lower() in COVER_STEMS
        ):
            return path
    return None


def _extension_for_mime(mime: str) -> str:
    return ".png" if "png" in mime else ".jpg"


def _extract_from_flac(path: Path) -> tuple[bytes, str] | None:
    audio = mutagen.flac.FLAC(path)
    if audio.pictures:
        picture = audio.pictures[0]
        return picture.data, picture.mime or "image/jpeg"
    return None


def _extract_from_id3(path: Path) -> tuple[bytes, str] | None:
    tags = mutagen.id3.ID3(path)
    for frame in tags.getall("APIC"):
        return frame.data, frame.mime or "image/jpeg"
    return None


def _extract_from_mp4(path: Path) -> tuple[bytes, str] | None:
    audio = mutagen.mp4.MP4(path)
    covers = audio.tags.get("covr") if audio.tags else None
    if covers:
        cover = covers[0]
        mime = "image/png" if cover.imageformat == mutagen.mp4.AtomDataType.PNG else "image/jpeg"
        return bytes(cover), mime
    return None


def _extract_from_vorbis_comment(path: Path) -> tuple[bytes, str] | None:
    audio = mutagen.File(path)
    if audio is None or audio.tags is None:
        return None
    for key in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
        values = audio.tags.get(key)
        if values:
            picture = mutagen.flac.Picture(base64.b64decode(values[0]))
            return picture.data, picture.mime or "image/jpeg"
    return None


_EXTRACTORS = {
    ".flac": _extract_from_flac,
    ".mp3": _extract_from_id3,
    ".m4a": _extract_from_mp4,
    ".mp4": _extract_from_mp4,
    ".ogg": _extract_from_vorbis_comment,
    ".opus": _extract_from_vorbis_comment,
}


def extract_embedded_cover(track_path: Path) -> Path | None:
    """Pull the embedded artwork out of a track's tags and write it to a
    local temp file, returning its path. Returns None if the track has no
    embedded art or its format isn't supported.
    """
    extractor = _EXTRACTORS.get(track_path.suffix.lower())
    if extractor is None:
        return None
    try:
        result = extractor(track_path)
    except Exception:
        return None
    if result is None:
        return None

    data, mime = result
    handle = tempfile.NamedTemporaryFile(
        suffix=_extension_for_mime(mime), prefix="filestomb-cover-", delete=False
    )
    handle.write(data)
    handle.close()
    return Path(handle.name)


def reveal_in_file_manager(path: Path) -> None:
    """Best-effort: open the OS file manager at `path`'s location, so the
    user doesn't have to hunt for it before dragging it into a browser tab.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        elif system == "Windows":
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError:
        pass


def find_or_extract_cover(directory: Path, tracks: list[Track]) -> Path | None:
    """The main entry point: prefer a standalone cover file in the album
    directory, otherwise fall back to whatever's embedded in the first
    track that has any.
    """
    cover_file = find_cover_file(directory)
    if cover_file is not None:
        return cover_file
    for track in tracks:
        extracted = extract_embedded_cover(track.path)
        if extracted is not None:
            return extracted
    return None

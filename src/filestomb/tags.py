"""Reads embedded metadata from a directory of audio files into an Album."""

from __future__ import annotations

from pathlib import Path

import mutagen
from mutagen.easyid3 import EasyID3

from . import coverart
from .models import Album, Track

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wv", ".ape"}

# Common freeform ID3 tags that aren't part of mutagen's default "easy" key
# set. Registering them lets label/catalog number/barcode round-trip the
# same way title/artist/album already do for MP3 files.
for _key, _frame in (("label", "LABEL"), ("catalognumber", "CATALOGNUMBER"), ("barcode", "BARCODE")):
    try:
        EasyID3.RegisterTXXXKey(_key, _frame)
    except Exception:
        pass


def _first(tags, *keys: str) -> str | None:
    if tags is None:
        return None
    for key in keys:
        try:
            value = tags.get(key) if hasattr(tags, "get") else tags[key]
        except Exception:
            value = None
        if not value:
            continue
        return str(value[0]) if isinstance(value, list) else str(value)
    return None


def _read_track(path: Path) -> Track | None:
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        return None
    if audio is None:
        return None
    tags = audio.tags

    length_ms = None
    if audio.info is not None and getattr(audio.info, "length", None):
        length_ms = round(audio.info.length * 1000)

    artist = _first(tags, "artist") or ""
    return Track(
        path=path,
        title=_first(tags, "title") or path.stem,
        artist=artist,
        album=_first(tags, "album") or "",
        album_artist=_first(tags, "albumartist") or artist,
        track_number=_first(tags, "tracknumber"),
        disc_number=_first(tags, "discnumber"),
        date=_first(tags, "date", "originaldate", "year"),
        length_ms=length_ms,
        musicbrainz_release_id=_first(tags, "musicbrainz_albumid"),
        musicbrainz_artist_id=_first(tags, "musicbrainz_artistid"),
        musicbrainz_release_group_id=_first(tags, "musicbrainz_releasegroupid"),
    )


def scan_directory(directory: Path, with_cover: bool = True) -> Album | None:
    """Read every audio file directly under `directory` (recursively, so
    multi-disc folders work) and summarize them as a single Album.

    Returns None if no readable audio files are found. `with_cover=False`
    skips cover discovery (which writes embedded art to a temp file) for
    callers, like the web UI, that look the cover up separately.
    """
    directory = Path(directory)
    tracks: list[Track] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        track = _read_track(path)
        if track is not None:
            tracks.append(track)

    if not tracks:
        return None

    first = tracks[0]
    label = catalog_number = barcode = None
    try:
        first_tags = mutagen.File(first.path, easy=True).tags
        label = _first(first_tags, "label")
        catalog_number = _first(first_tags, "catalognumber")
        barcode = _first(first_tags, "barcode")
    except Exception:
        pass

    return Album(
        directory=directory,
        title=first.album or directory.name,
        artist=first.album_artist or first.artist,
        date=first.date,
        label=label,
        catalog_number=catalog_number,
        barcode=barcode,
        tracks=tracks,
        cover_art_path=coverart.find_or_extract_cover(directory, tracks) if with_cover else None,
    )

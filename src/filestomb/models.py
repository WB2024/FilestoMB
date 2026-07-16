"""Data model shared across tag reading, matching, and the TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class EntityType(str, Enum):
    ARTIST = "artist"
    LABEL = "label"
    RELEASE_GROUP = "release-group"
    RELEASE = "release"


class MatchStatus(str, Enum):
    UNCHECKED = "unchecked"
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


@dataclass
class Track:
    path: Path
    title: str
    artist: str
    album: str
    album_artist: str
    track_number: str | None = None
    disc_number: str | None = None
    date: str | None = None
    length_ms: int | None = None
    musicbrainz_release_id: str | None = None
    musicbrainz_artist_id: str | None = None
    musicbrainz_release_group_id: str | None = None


@dataclass
class Album:
    directory: Path
    title: str
    artist: str
    date: str | None = None
    label: str | None = None
    catalog_number: str | None = None
    barcode: str | None = None
    tracks: list[Track] = field(default_factory=list)
    cover_art_path: Path | None = None


@dataclass
class Candidate:
    mbid: str
    name: str
    score: float
    disambiguation: str | None = None
    # Free-form extra context, e.g. a release group's primary type or a release's date.
    extra: str | None = None


@dataclass
class MatchResult:
    entity_type: EntityType
    query: str
    status: MatchStatus = MatchStatus.UNCHECKED
    candidates: list[Candidate] = field(default_factory=list)
    selected_mbid: str | None = None

    @property
    def selected_candidate(self) -> Candidate | None:
        for candidate in self.candidates:
            if candidate.mbid == self.selected_mbid:
                return candidate
        return None

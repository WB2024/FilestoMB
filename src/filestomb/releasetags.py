"""Match a folder's tracks to a MusicBrainz release and write MBIDs into the tags.

This is the bridge to Picard: files carrying ``MUSICBRAINZ_ALBUMID`` are
loaded straight onto that release by Picard (unless it's set to ignore MBIDs),
with no lookup or drag-and-drop. Writing the per-track IDs as well, where we
can match with confidence, makes Picard's own matching exact. Nothing else in
the tags is touched; Picard rewrites the rest when you save.
"""

from __future__ import annotations

import errno
import re
from dataclasses import dataclass, field
from pathlib import Path

import mutagen
from rapidfuzz import fuzz

from .models import Track

TITLE_MATCH_BY_POSITION = 50  # accept a same-position track if titles are at least this similar
TITLE_MATCH_BY_TITLE = 85  # otherwise titles alone must be this similar


class TagWriteError(Exception):
    """Tags couldn't be written; the message is safe to show to the user."""


@dataclass
class ReleaseTrack:
    disc: int
    position: int
    title: str
    length_ms: int | None
    track_id: str
    recording_id: str
    artist_ids: list[str]


@dataclass
class ReleaseInfo:
    mbid: str
    title: str
    artist: str
    artist_ids: list[str]
    release_group_id: str
    date: str
    tracks: list[ReleaseTrack]


@dataclass
class Pairing:
    track: Track
    release_track: ReleaseTrack | None
    score: float = 0.0


@dataclass
class Plan:
    release: ReleaseInfo
    pairs: list[Pairing]
    unmatched_release_tracks: list[ReleaseTrack] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.unmatched_release_tracks and all(p.release_track for p in self.pairs)


def parse_release(data: dict) -> ReleaseInfo:
    """Build a ReleaseInfo from a ws/2 release lookup (inc=recordings artist-credits release-groups)."""
    credit = data.get("artist-credit") or []
    tracks: list[ReleaseTrack] = []
    for medium_index, medium in enumerate(data.get("media") or [], start=1):
        disc = int(medium.get("position") or medium_index)
        for index, track in enumerate(medium.get("tracks") or [], start=1):
            recording = track.get("recording") or {}
            tracks.append(
                ReleaseTrack(
                    disc=disc,
                    position=int(track.get("position") or index),
                    title=track.get("title") or recording.get("title") or "",
                    length_ms=track.get("length") or recording.get("length"),
                    track_id=track.get("id") or "",
                    recording_id=recording.get("id") or "",
                    artist_ids=[c["artist"]["id"] for c in (track.get("artist-credit") or []) if c.get("artist")],
                )
            )
    return ReleaseInfo(
        mbid=data["id"],
        title=data.get("title", ""),
        artist="".join(f"{c.get('name', '')}{c.get('joinphrase', '')}" for c in credit),
        artist_ids=[c["artist"]["id"] for c in credit if c.get("artist")],
        release_group_id=(data.get("release-group") or {}).get("id", ""),
        date=data.get("date") or "",
        tracks=tracks,
    )


def _leading_int(value: str | None) -> int | None:
    match = re.match(r"\s*(\d+)", value or "")
    return int(match.group(1)) if match else None


def _norm(text: str) -> str:
    folded = text.casefold().replace("&", " and ").replace("\u2019", "'")
    return re.sub(r"[^\w]+", " ", folded.replace("'", "")).strip()


def _similarity(a: str, b: str) -> float:
    return float(fuzz.token_set_ratio(_norm(a), _norm(b)))


def match_tracks(local_tracks: list[Track], release: ReleaseInfo) -> Plan:
    """Pair each local file with a release track: same disc/position first
    (if the titles broadly agree), then by title for whatever's left."""
    by_position = {(t.disc, t.position): t for t in release.tracks}
    taken: set[tuple[int, int]] = set()
    pairs: dict[int, Pairing] = {}

    for index, local in enumerate(local_tracks):
        key = (_leading_int(local.disc_number) or 1, _leading_int(local.track_number) or -1)
        candidate = by_position.get(key)
        if candidate and key not in taken:
            score = _similarity(local.title, candidate.title)
            if score >= TITLE_MATCH_BY_POSITION:
                pairs[index] = Pairing(local, candidate, score)
                taken.add(key)

    for index, local in enumerate(local_tracks):
        if index in pairs:
            continue
        best: tuple[float, ReleaseTrack] | None = None
        for candidate in release.tracks:
            if (candidate.disc, candidate.position) in taken:
                continue
            score = _similarity(local.title, candidate.title)
            if score >= TITLE_MATCH_BY_TITLE and (best is None or score > best[0]):
                best = (score, candidate)
        if best:
            pairs[index] = Pairing(local, best[1], best[0])
            taken.add((best[1].disc, best[1].position))
        else:
            pairs[index] = Pairing(local, None)

    ordered = [pairs[i] for i in range(len(local_tracks))]
    unmatched = [t for t in release.tracks if (t.disc, t.position) not in taken]
    return Plan(release=release, pairs=ordered, unmatched_release_tracks=unmatched)


def _set(audio, key: str, values: list[str]) -> bool:
    values = [v for v in values if v]
    if not values:
        return False
    try:
        audio[key] = values
        return True
    except (KeyError, ValueError, TypeError):
        return False  # this format has no "easy" key for it (e.g. some MP4 fields)


def write_tags(plan: Plan) -> int:
    """Write MusicBrainz IDs into every file in the plan. Returns the number of files written."""
    release = plan.release
    written = 0
    for pairing in plan.pairs:
        path = Path(pairing.track.path)
        try:
            audio = mutagen.File(path, easy=True)
            if audio is None:
                raise TagWriteError(f"{path.name} isn't a readable audio file.")
            if audio.tags is None:
                audio.add_tags()
            _set(audio, "musicbrainz_albumid", [release.mbid])
            _set(audio, "musicbrainz_releasegroupid", [release.release_group_id])
            _set(audio, "musicbrainz_albumartistid", release.artist_ids)
            if pairing.release_track:
                _set(audio, "musicbrainz_releasetrackid", [pairing.release_track.track_id])
                _set(audio, "musicbrainz_trackid", [pairing.release_track.recording_id])
                _set(audio, "musicbrainz_artistid", pairing.release_track.artist_ids)
            audio.save()
            written += 1
        except (OSError, mutagen.MutagenError) as error:
            # mutagen wraps OS errors, so look at the text as well as errno.
            text = str(error).lower()
            if getattr(error, "errno", None) in (errno.EACCES, errno.EPERM, errno.EROFS) or "permission denied" in text or "read-only" in text:
                raise TagWriteError(
                    f"No permission to write {path.name}. Is the library mounted read-only?"
                ) from error
            raise TagWriteError(f"Couldn't write tags to {path.name}: {error}") from error
    return written

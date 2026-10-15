"""Classifies MusicBrainz search results into matched/ambiguous/missing."""

from __future__ import annotations

from .mb.client import MusicBrainzClient
from .models import Album, Candidate, EntityType, MatchResult, MatchStatus

# MusicBrainz's own relevance score (0-100) is good enough to act on without
# reimplementing fuzzy matching: a single strong hit is treated as a match,
# anything weaker is left for the user to confirm.
AUTO_MATCH_THRESHOLD = 90.0


def _classify(candidates: list[Candidate], entity_type: EntityType, query: str) -> MatchResult:
    result = MatchResult(entity_type=entity_type, query=query, candidates=candidates)
    if not candidates:
        result.status = MatchStatus.MISSING
        return result

    top = candidates[0]
    if top.score >= AUTO_MATCH_THRESHOLD:
        result.status = MatchStatus.MATCHED
        result.selected_mbid = top.mbid
    else:
        result.status = MatchStatus.AMBIGUOUS
    return result


async def match_artists(client: MusicBrainzClient, names: list[str]) -> list[MatchResult]:
    """One classified artist search per name (for a credit like "A & B")."""
    return [_classify(await client.search_artist(name), EntityType.ARTIST, name) for name in names]


async def match_album(client: MusicBrainzClient, album: Album, skip_artist: bool = False) -> dict[EntityType, MatchResult]:
    """Search MusicBrainz for each entity referenced by `album` and classify
    the results. Callers decide what to do about anything not MATCHED.
    """
    results: dict[EntityType, MatchResult] = {}

    if not skip_artist:
        artist_candidates = await client.search_artist(album.artist)
        results[EntityType.ARTIST] = _classify(artist_candidates, EntityType.ARTIST, album.artist)

    if album.label:
        label_candidates = await client.search_label(album.label)
        results[EntityType.LABEL] = _classify(label_candidates, EntityType.LABEL, album.label)

    rg_candidates = await client.search_release_group(album.title, album.artist)
    results[EntityType.RELEASE_GROUP] = _classify(rg_candidates, EntityType.RELEASE_GROUP, album.title)

    release_candidates = await client.search_release(album.title, album.artist)
    results[EntityType.RELEASE] = _classify(release_candidates, EntityType.RELEASE, album.title)

    return results

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from filestomb.matching import match_album
from filestomb.models import Album, Candidate, EntityType, MatchStatus


def _client_stub(**overrides) -> AsyncMock:
    client = AsyncMock()
    client.search_artist.return_value = overrides.get("artist", [])
    client.search_label.return_value = overrides.get("label", [])
    client.search_release_group.return_value = overrides.get("release_group", [])
    client.search_release.return_value = overrides.get("release", [])
    return client


@pytest.mark.asyncio
async def test_strong_top_score_is_auto_matched() -> None:
    album = Album(directory=Path("/tmp/test-album"), title="Test Album", artist="Test Artist")
    client = _client_stub(
        artist=[Candidate(mbid="artist-1", name="Test Artist", score=100.0)],
        release_group=[Candidate(mbid="rg-1", name="Test Album", score=95.0)],
        release=[Candidate(mbid="rel-1", name="Test Album", score=100.0)],
    )

    results = await match_album(client, album)

    assert results[EntityType.ARTIST].status == MatchStatus.MATCHED
    assert results[EntityType.ARTIST].selected_mbid == "artist-1"
    assert results[EntityType.RELEASE_GROUP].status == MatchStatus.MATCHED
    assert results[EntityType.RELEASE].status == MatchStatus.MATCHED
    assert EntityType.LABEL not in results


@pytest.mark.asyncio
async def test_weak_score_is_ambiguous_not_auto_selected() -> None:
    album = Album(directory=Path("/tmp/test-album"), title="Test Album", artist="Test Artist")
    client = _client_stub(
        artist=[
            Candidate(mbid="artist-1", name="Test Artist", score=60.0),
            Candidate(mbid="artist-2", name="Test Artists", score=55.0),
        ],
        release_group=[],
        release=[],
    )

    results = await match_album(client, album)

    assert results[EntityType.ARTIST].status == MatchStatus.AMBIGUOUS
    assert results[EntityType.ARTIST].selected_mbid is None
    assert results[EntityType.RELEASE_GROUP].status == MatchStatus.MISSING
    assert results[EntityType.RELEASE].status == MatchStatus.MISSING


@pytest.mark.asyncio
async def test_label_only_searched_when_present() -> None:
    album = Album(directory=Path("/tmp/test-album"), title="Test Album", artist="Test Artist", label="Test Records")
    client = _client_stub(label=[Candidate(mbid="label-1", name="Test Records", score=100.0)])

    results = await match_album(client, album)

    client.search_label.assert_awaited_once_with("Test Records")
    assert results[EntityType.LABEL].status == MatchStatus.MATCHED

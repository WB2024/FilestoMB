from __future__ import annotations

import respx
from httpx import Response

from filestomb.mb.client import MusicBrainzClient


@respx.mock
async def test_search_artist_parses_candidates() -> None:
    route = respx.get("https://musicbrainz.org/ws/2/artist").mock(
        return_value=Response(
            200,
            json={
                "artists": [
                    {"id": "abc-123", "name": "Test Artist", "score": 100, "disambiguation": "the band"},
                ]
            },
        )
    )
    client = MusicBrainzClient(user_agent="FilesToMB/0.1.0 ( test@example.com )")

    candidates = await client.search_artist("Test Artist")

    assert route.called
    request = route.calls.last.request
    assert request.headers["user-agent"] == "FilesToMB/0.1.0 ( test@example.com )"
    assert len(candidates) == 1
    assert candidates[0].mbid == "abc-123"
    assert candidates[0].score == 100.0
    assert candidates[0].disambiguation == "the band"

    await client.aclose()


@respx.mock
async def test_search_release_group_parses_primary_type_as_extra() -> None:
    respx.get("https://musicbrainz.org/ws/2/release-group").mock(
        return_value=Response(
            200,
            json={
                "release-groups": [
                    {"id": "rg-1", "title": "Test Album", "score": 90, "primary-type": "Album"},
                ]
            },
        )
    )
    client = MusicBrainzClient(user_agent="FilesToMB/0.1.0 ( test@example.com )")

    candidates = await client.search_release_group("Test Album", "Test Artist")

    assert candidates[0].extra == "Album"

    await client.aclose()

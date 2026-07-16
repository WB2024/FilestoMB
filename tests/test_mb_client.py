from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

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


@respx.mock
async def test_list_collections_sends_bearer_token() -> None:
    route = respx.get("https://musicbrainz.org/ws/2/collection").mock(
        return_value=Response(
            200,
            json={"collections": [{"id": "col-1", "name": "My Albums", "entity-type": "release"}]},
        )
    )
    client = MusicBrainzClient(user_agent="FilesToMB/0.1.0 ( test@example.com )")

    collections = await client.list_collections("access-token-1", username="test_user")

    assert route.called
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer access-token-1"
    assert parse_qs(urlsplit(str(request.url)).query)["editor"] == ["test_user"]
    assert collections == [{"id": "col-1", "name": "My Albums", "entity-type": "release"}]

    await client.aclose()


@respx.mock
async def test_add_release_to_collection_puts_with_bearer_token() -> None:
    route = respx.put(
        "https://musicbrainz.org/ws/2/collection/col-1/releases/release-1"
    ).mock(return_value=Response(200))
    client = MusicBrainzClient(user_agent="FilesToMB/0.1.0 ( test@example.com )")

    await client.add_release_to_collection("col-1", "release-1", "access-token-1")

    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer access-token-1"

    await client.aclose()

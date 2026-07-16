from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit

import respx
from httpx import Response

from filestomb.mb.oauth import MusicBrainzOAuth, Token, build_authorize_url


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_build_authorize_url_uses_oob_redirect() -> None:
    url = build_authorize_url("client-123", state="xyz")
    assert url.startswith("https://musicbrainz.org/oauth2/authorize?")
    query = _query(url)
    assert query["client_id"] == ["client-123"]
    assert query["redirect_uri"] == ["urn:ietf:wg:oauth:2.0:oob"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["xyz"]


def test_token_expiry() -> None:
    fresh = Token(access_token="a", refresh_token="r", expires_at=time.time() + 3600)
    assert not fresh.is_expired

    stale = Token(access_token="a", refresh_token="r", expires_at=time.time() - 10)
    assert stale.is_expired


def test_token_round_trips_through_disk(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    token = Token(access_token="a", refresh_token="r", expires_at=time.time() + 3600)
    token.save()

    loaded = Token.load()
    assert loaded == token

    Token.clear()
    assert Token.load() is None


@respx.mock
async def test_exchange_code_stores_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.post("https://musicbrainz.org/oauth2/token").mock(
        return_value=Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )
    )

    oauth = MusicBrainzOAuth(client_id="client-123", client_secret="secret-123")
    token = await oauth.exchange_code("auth-code")

    assert token.access_token == "access-1"
    assert oauth.is_logged_in
    await oauth.aclose()


@respx.mock
async def test_get_access_token_refreshes_when_expired(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    respx.post("https://musicbrainz.org/oauth2/token").mock(
        return_value=Response(
            200,
            json={"access_token": "refreshed", "refresh_token": "refresh-1", "expires_in": 3600},
        )
    )

    oauth = MusicBrainzOAuth(client_id="client-123", client_secret="secret-123")
    oauth.token = Token(access_token="stale", refresh_token="refresh-1", expires_at=time.time() - 10)

    access_token = await oauth.get_access_token()

    assert access_token == "refreshed"
    await oauth.aclose()


@respx.mock
async def test_fetch_username_uses_bearer_header(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    route = respx.get("https://musicbrainz.org/oauth2/userinfo").mock(
        return_value=Response(200, json={"sub": "test_user"})
    )

    oauth = MusicBrainzOAuth(client_id="client-123", client_secret="secret-123")
    oauth.token = Token(access_token="access-1", refresh_token="refresh-1", expires_at=time.time() + 3600)

    username = await oauth.fetch_username()

    assert username == "test_user"
    assert route.calls.last.request.headers["authorization"] == "Bearer access-1"
    await oauth.aclose()

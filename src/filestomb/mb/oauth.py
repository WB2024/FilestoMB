"""OAuth2 login for a MusicBrainz "Installed application" client.

Reference: https://musicbrainz.org/doc/Development/OAuth2

Searching MusicBrainz and opening seeded "create" forms (see mb/seed.py)
need no authentication at all. OAuth2 only comes in for the narrower set
of actions MusicBrainz's ws/2 API does support as real authenticated
writes: managing collections, personal ratings, and personal tags.

Installed/desktop apps have nowhere to receive a browser redirect, so this
uses the out-of-band flow: MusicBrainz shows the authorization code on a
page for the user to copy, and pastes it back into the app.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

from ..paths import config_dir

AUTHORIZE_URL = "https://musicbrainz.org/oauth2/authorize"
TOKEN_URL = "https://musicbrainz.org/oauth2/token"
USERINFO_URL = "https://musicbrainz.org/oauth2/userinfo"

# The redirect_uri MusicBrainz reserves for apps with no callback server.
# Whatever redirect_uri you registered the application with must match this
# exactly, or MusicBrainz will refuse the authorization request.
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

DEFAULT_SCOPE = "profile collection"


def _token_path() -> Path:
    return config_dir() / "token.json"


@dataclass
class Token:
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 30

    def save(self) -> None:
        path = _token_path()
        path.write_text(json.dumps(asdict(self)))
        path.chmod(0o600)

    @classmethod
    def load(cls) -> "Token | None":
        path = _token_path()
        if not path.exists():
            return None
        try:
            return cls(**json.loads(path.read_text()))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    @classmethod
    def clear(cls) -> None:
        _token_path().unlink(missing_ok=True)


def build_authorize_url(client_id: str, scope: str = DEFAULT_SCOPE, state: str = "") -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": scope,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class MusicBrainzOAuth:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._client = httpx.AsyncClient(timeout=10.0)
        self.token: Token | None = Token.load()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def is_logged_in(self) -> bool:
        return self.token is not None

    def _parse_token_response(self, data: dict) -> Token:
        refresh_token = data.get("refresh_token") or (self.token.refresh_token if self.token else "")
        return Token(
            access_token=data["access_token"],
            refresh_token=refresh_token,
            expires_at=time.time() + float(data.get("expires_in", 3600)),
            token_type=data.get("token_type", "Bearer"),
        )

    async def exchange_code(self, code: str) -> Token:
        response = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": REDIRECT_URI,
            },
        )
        response.raise_for_status()
        self.token = self._parse_token_response(response.json())
        self.token.save()
        return self.token

    async def _refresh(self) -> Token:
        assert self.token is not None
        response = await self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.token.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        response.raise_for_status()
        self.token = self._parse_token_response(response.json())
        self.token.save()
        return self.token

    async def get_access_token(self) -> str:
        if self.token is None:
            raise RuntimeError("Not logged in to MusicBrainz.")
        if self.token.is_expired:
            await self._refresh()
        return self.token.access_token

    async def fetch_username(self) -> str:
        access_token = await self.get_access_token()
        response = await self._client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        response.raise_for_status()
        data = response.json()
        return data.get("sub") or data.get("metabrainz_user_id") or ""

    def logout(self) -> None:
        self.token = None
        Token.clear()

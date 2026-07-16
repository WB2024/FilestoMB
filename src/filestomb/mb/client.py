"""A small async client for MusicBrainz's read-only search API (ws/2).

MusicBrainz doesn't expose a public write API for creating artists, labels,
release groups, or releases -- see mb/seed.py for how new entities actually
get created (browser-based "seeded" edit forms). This client only searches
for what already exists.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from ..models import Candidate

DEFAULT_BASE_URL = "https://musicbrainz.org/ws/2"

# MusicBrainz asks anonymous/non-bursty clients to keep to roughly one
# request per second: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
MIN_REQUEST_INTERVAL = 1.0


def _escape(value: str) -> str:
    """Escape a value for use inside a Lucene query string."""
    special = '+-&&||!(){}[]^"~*?:\\/'
    return "".join(f"\\{char}" if char in special else char for char in value)


class MusicBrainzClient:
    def __init__(self, user_agent: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=10.0,
        )
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MusicBrainzClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict[str, str | int]) -> dict:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < MIN_REQUEST_INTERVAL:
                await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
            response = await self._client.get(path, params={**params, "fmt": "json"})
            self._last_request = time.monotonic()
        response.raise_for_status()
        return response.json()

    async def search_artist(self, name: str, limit: int = 5) -> list[Candidate]:
        query = f'artist:"{_escape(name)}"'
        data = await self._get("/artist", {"query": query, "limit": limit})
        return [
            Candidate(
                mbid=item["id"],
                name=item.get("name", ""),
                score=float(item.get("score", 0)),
                disambiguation=item.get("disambiguation") or None,
            )
            for item in data.get("artists", [])
        ]

    async def search_label(self, name: str, limit: int = 5) -> list[Candidate]:
        query = f'label:"{_escape(name)}"'
        data = await self._get("/label", {"query": query, "limit": limit})
        return [
            Candidate(
                mbid=item["id"],
                name=item.get("name", ""),
                score=float(item.get("score", 0)),
                disambiguation=item.get("disambiguation") or None,
            )
            for item in data.get("labels", [])
        ]

    async def search_release_group(self, title: str, artist: str, limit: int = 5) -> list[Candidate]:
        query = f'releasegroup:"{_escape(title)}" AND artist:"{_escape(artist)}"'
        data = await self._get("/release-group", {"query": query, "limit": limit})
        return [
            Candidate(
                mbid=item["id"],
                name=item.get("title", ""),
                score=float(item.get("score", 0)),
                disambiguation=item.get("disambiguation") or None,
                extra=item.get("primary-type") or None,
            )
            for item in data.get("release-groups", [])
        ]

    async def search_release(self, title: str, artist: str, limit: int = 5) -> list[Candidate]:
        query = f'release:"{_escape(title)}" AND artist:"{_escape(artist)}"'
        data = await self._get("/release", {"query": query, "limit": limit})
        return [
            Candidate(
                mbid=item["id"],
                name=item.get("title", ""),
                score=float(item.get("score", 0)),
                disambiguation=item.get("disambiguation") or None,
                extra=item.get("date") or None,
            )
            for item in data.get("releases", [])
        ]

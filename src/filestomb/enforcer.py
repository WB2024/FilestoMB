"""Client for Music Genre Enforcer's HTTP API.

FilesToMB never reads or writes the enforcer's data itself: every action is a
call to the running enforcer, which stays the single source of truth for
artist genres and for tagging files.
"""

from __future__ import annotations

import httpx


class EnforcerError(Exception):
    """Safe to show to the user."""


class EnforcerClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=f"{self.base_url}/api", timeout=60.0, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, **kwargs):
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise EnforcerError(f"Couldn't reach Music Genre Enforcer at {self.base_url}: {error or type(error).__name__}") from error
        if response.status_code >= 400:
            detail = ""
            try:
                detail = str(response.json().get("detail") or "")
            except (ValueError, AttributeError):
                pass
            raise EnforcerError(detail or f"Music Genre Enforcer returned {response.status_code} for {method} {path}.")
        return response.json() if response.content else None

    async def state(self) -> dict:
        return await self._call("GET", "/state")

    async def artists(self) -> dict:
        return await self._call("GET", "/artists")

    async def peek_tags(self, name: str) -> dict:
        return await self._call("GET", "/artist/tags", params={"name": name})

    async def lastfm(self, name: str) -> dict:
        return await self._call("GET", "/lastfm", params={"name": name})

    async def set_genre(self, name: str, genre: str) -> dict:
        return await self._call("PUT", "/artist", json={"name": name, "genre": genre})

    async def apply_selected(self, names: list[str]) -> dict:
        return await self._call("POST", "/apply", json={"mode": "selected", "artists": names})

    async def job(self) -> dict | None:
        return await self._call("GET", "/job")

    async def watcher(self) -> dict:
        return await self._call("GET", "/watcher")

    async def notify(self) -> None:
        """Rescan now so new folders/artists are noticed, and wake the watcher."""
        await self._call("POST", "/scan")
        await self._call("POST", "/watcher/run")


def artist_for_folder(folder_rel_to_dest: str, flat_folders: list[str]) -> str | None:
    """The enforcer's artist key for an album folder inside its library: its
    layout is <group>/<artist>/<album>, except 'flat' groups, which are the artist."""
    parts = [p for p in folder_rel_to_dest.strip("/").split("/") if p]
    if not parts:
        return None
    if parts[0].casefold() in {f.casefold() for f in flat_folders}:
        return parts[0]
    return parts[1] if len(parts) >= 2 else None

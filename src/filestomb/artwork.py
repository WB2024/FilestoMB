"""Find cover art online: the Cover Art Archive and fanart.tv.

Both are looked up by MusicBrainz IDs. Downloads are restricted to the hosts
these services actually serve images from, so a crafted request can't make the
server fetch arbitrary URLs.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

CAA = "https://coverartarchive.org"
FANART = "https://webservice.fanart.tv/v3/music/albums"
MAX_BYTES = 20 * 1024 * 1024


class ArtworkError(Exception):
    """Safe to show to the user."""


def allowed_url(url: str) -> bool:
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return False
    return host == "coverartarchive.org" or host.endswith(".archive.org") or host == "archive.org" or host in {
        "assets.fanart.tv", "fanart.tv"
    }


def _client(user_agent: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": user_agent}, timeout=15.0, follow_redirects=True)


def _https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


async def _caa(client: httpx.AsyncClient, kind: str, mbid: str, scope: str) -> list[dict]:
    try:
        response = await client.get(f"{CAA}/{kind}/{mbid}", headers={"Accept": "application/json"})
    except httpx.HTTPError:
        return []
    if response.status_code != 200:  # 404 just means no art
        return []
    found = []
    for image in response.json().get("images", []):
        thumbs = image.get("thumbnails") or {}
        full = _https(image.get("image", ""))
        if not full:
            continue
        types = image.get("types") or []
        found.append({
            "source": "caa",
            "scope": scope,
            "id": f"caa-{kind}-{image.get('id')}",
            "label": ", ".join(types) or "Image",
            "front": bool(image.get("front")),
            "thumb": _https(thumbs.get("250") or thumbs.get("small") or full),
            "url": full,
        })
    return found


async def _fanart(client: httpx.AsyncClient, release_group: str, key: str) -> tuple[list[dict], str | None]:
    try:
        response = await client.get(f"{FANART}/{release_group}", params={"api_key": key}, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        return [], f"Couldn't reach fanart.tv: {error or type(error).__name__}"
    if response.status_code == 404:
        return [], None
    if response.status_code in (401, 403):
        return [], "fanart.tv rejected the API key."
    if response.status_code != 200:
        return [], f"fanart.tv returned {response.status_code}."
    found = []
    for album in (response.json().get("albums") or {}).values():
        for field, label in (("albumcover", "Album cover"), ("cdart", "Disc")):
            for image in album.get(field) or []:
                url = _https(image.get("url", ""))
                if not url:
                    continue
                found.append({
                    "source": "fanart",
                    "scope": "release group",
                    "id": f"fanart-{image.get('id')}",
                    "label": label,
                    "front": field == "albumcover",
                    "thumb": url.replace("/fanart/", "/preview/") if "/fanart/" in url else url,
                    "url": url,
                    "likes": int(image.get("likes") or 0),
                })
    return found, None


async def find_artwork(
    user_agent: str, *, release: str | None, release_group: str | None, fanart_key: str
) -> dict:
    """Candidates from every source that applies, plus per-source notes."""
    notes: list[str] = []
    images: list[dict] = []
    async with _client(user_agent) as client:
        if release:
            images += await _caa(client, "release", release, "this release")
        if release_group:
            images += await _caa(client, "release-group", release_group, "release group")
            if fanart_key:
                extra, note = await _fanart(client, release_group, fanart_key)
                images += extra
                if note:
                    notes.append(note)
            else:
                notes.append("Add a fanart.tv API key in Settings to search fanart.tv too.")
        elif not release:
            notes.append("Needs a matched release or release group first.")
    # Same image can be reachable through both release and release group.
    seen: set[str] = set()
    unique = []
    for image in images:
        if image["url"] not in seen:
            seen.add(image["url"])
            unique.append(image)
    return {"images": unique, "notes": notes}


async def download(user_agent: str, url: str) -> bytes:
    if not allowed_url(url):
        raise ArtworkError("That address isn't from the Cover Art Archive or fanart.tv.")
    async with _client(user_agent) as client:
        try:
            async with client.stream("GET", url) as response:
                if not allowed_url(str(response.url)):
                    raise ArtworkError("The image redirected somewhere unexpected.")
                if response.status_code != 200:
                    raise ArtworkError(f"The image server returned {response.status_code}.")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise ArtworkError("Image is larger than 20 MB.")
        except httpx.HTTPError as error:
            raise ArtworkError(f"Couldn't download the image: {error or type(error).__name__}") from error
    return bytes(data)

"""Online cover art (Cover Art Archive, fanart.tv) and the settings store."""

from __future__ import annotations

import httpx
import pytest
import respx

from filestomb import artwork, integrations
from tests.test_web import ALBUM, PNG, client, library  # noqa: F401  (fixtures)

RG = "1b022e01-4da6-387b-8658-8678046e4cef"
REL = "11111111-2222-3333-4444-555555555555"


def caa_body(image_url: str) -> dict:
    return {"images": [{"id": 7, "image": image_url, "front": True, "types": ["Front"],
                        "thumbnails": {"250": "http://coverartarchive.org/release/x/7-250.jpg"}}]}


@respx.mock
async def test_find_artwork_merges_sources_and_dedupes(client, monkeypatch):
    monkeypatch.setenv("FANART_API_KEY", "k")
    img = "http://coverartarchive.org/release/x/7.jpg"
    respx.get(f"https://coverartarchive.org/release/{REL}").respond(json=caa_body(img))
    respx.get(f"https://coverartarchive.org/release-group/{RG}").respond(json=caa_body(img))
    fan = respx.get(f"{artwork.FANART}/{RG}").respond(
        json={"albums": {RG: {"albumcover": [{"id": "9", "url": "http://assets.fanart.tv/fanart/music/a/albumcover/b.jpg", "likes": "3"}]}}}
    )
    data = (await client.get("/api/artwork", params={"release": REL, "release_group": RG})).json()
    assert [i["source"] for i in data["images"]] == ["caa", "fanart"]  # duplicate CAA image dropped
    assert data["images"][0]["url"].startswith("https://")
    assert fan.calls.last.request.url.params["api_key"] == "k"


@respx.mock
async def test_find_artwork_without_key_notes_it_and_tolerates_404(client):
    respx.get(f"https://coverartarchive.org/release-group/{RG}").respond(404)
    data = (await client.get("/api/artwork", params={"release_group": RG})).json()
    assert data["images"] == [] and any("fanart.tv API key" in n for n in data["notes"])


async def test_artwork_rejects_bad_ids(client):
    assert (await client.get("/api/artwork", params={"release": "../x"})).status_code == 422


@respx.mock
async def test_use_online_cover_sets_cover(client):
    respx.get("https://assets.fanart.tv/a.png").respond(content=PNG)
    r = await client.post("/api/cover/online", json={"path": ALBUM, "url": "https://assets.fanart.tv/a.png"})
    assert r.status_code == 200 and r.json()["custom"] is True
    assert (await client.get("/api/cover", params={"path": ALBUM})).content == PNG


@respx.mock
async def test_online_cover_refuses_other_hosts_and_non_images(client):
    bad = await client.post("/api/cover/online", json={"path": ALBUM, "url": "https://evil.example/a.png"})
    assert bad.status_code == 502 and "isn't from" in bad.json()["detail"]
    respx.get("https://assets.fanart.tv/x.png").respond(content=b"<html>")
    assert (await client.post("/api/cover/online", json={"path": ALBUM, "url": "https://assets.fanart.tv/x.png"})).status_code == 415


@respx.mock
async def test_online_cover_refuses_redirect_off_allowlist(client):
    respx.get("https://coverartarchive.org/r").respond(302, headers={"location": "https://evil.example/a.png"})
    respx.get("https://evil.example/a.png").respond(content=PNG)
    r = await client.post("/api/cover/online", json={"path": ALBUM, "url": "https://coverartarchive.org/r"})
    assert r.status_code == 502


async def test_settings_never_return_the_secret(client, tmp_path):
    assert (await client.get("/api/settings")).json()["fanart_api_key"]["set"] is False
    saved = (await client.put("/api/settings", json={"fanart_api_key": " secret123 "})).json()
    assert saved["fanart_api_key"]["set"] is True and "secret123" not in str(saved)
    assert integrations.get("fanart_api_key") == "secret123"
    assert (await client.put("/api/settings", json={})).json()["fanart_api_key"]["set"] is True  # untouched
    assert (await client.put("/api/settings", json={"fanart_api_key": ""})).json()["fanart_api_key"]["set"] is False


@respx.mock
async def test_fanart_key_test(client):
    assert (await client.post("/api/settings/test-fanart")).status_code == 422
    await client.put("/api/settings", json={"fanart_api_key": "bad"})
    respx.get(f"{artwork.FANART}/{RG}").respond(401)
    assert (await client.post("/api/settings/test-fanart")).status_code == 502

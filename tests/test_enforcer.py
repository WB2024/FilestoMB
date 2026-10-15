"""The Music Genre Enforcer integration, against a mocked enforcer API."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from filestomb.enforcer import artist_for_folder
from tests.test_web import client, library  # noqa: F401  (fixtures)

BASE = "http://enforcer:8320/api"
STATE = {"counts": {"artists": 10, "defined": 9, "undefined": 1, "orphans": 0, "genres": 3}, "library_exists": True,
         "config": {"dry_run": False, "lastfm_configured": True, "auto_apply": True, "flat_folders": ["Various Artists"]}, "job": None}
ARTISTS = {"artists": [
    {"name": "Hole", "group": "H", "genre": "Rock - Grunge", "on_disk": True},
    {"name": "New Band", "group": "N", "genre": "", "on_disk": True},
    {"name": "Gone", "group": "", "genre": "Folk", "on_disk": False},
    {"name": "Ghost", "group": "", "genre": "", "on_disk": False},
], "genres": [{"genre": "Rock - Grunge", "count": 1}]}


@pytest.fixture
async def configured(client):
    await client.put("/api/settings", json={"enforcer_url": "http://enforcer:8320"})
    return client


def test_artist_for_folder_follows_the_enforcers_layout():
    assert artist_for_folder("H/Hole/[1993] Little Parties", ["Various Artists"]) == "Hole"
    assert artist_for_folder("Various Artists/Some Compilation", ["various artists"]) == "Various Artists"
    assert artist_for_folder("H", []) is None


async def test_unconfigured_reports_so_and_refuses_actions(client):
    assert (await client.get("/api/enforcer/status")).json() == {"configured": False}
    assert (await client.get("/api/enforcer/queue")).status_code == 422


@respx.mock
async def test_status_and_unreachable(configured):
    respx.get(f"{BASE}/state").respond(json=STATE)
    status = (await configured.get("/api/enforcer/status")).json()
    assert status["reachable"] and status["counts"]["undefined"] == 1 and status["lastfm"] is True
    respx.get(f"{BASE}/state").mock(side_effect=httpx.ConnectError("down"))
    down = (await configured.get("/api/enforcer/status")).json()
    assert down["configured"] and down["reachable"] is False and "Couldn't reach" in down["error"]


@respx.mock
async def test_queue_only_lists_artists_on_disk_without_a_genre(configured):
    respx.get(f"{BASE}/artists").respond(json=ARTISTS)
    queue = (await configured.get("/api/enforcer/queue")).json()
    assert [a["name"] for a in queue["artists"]] == ["New Band"]
    one = (await configured.get("/api/enforcer/artist", params={"name": "Hole"})).json()
    assert one["known"] and one["genre"] == "Rock - Grunge"
    unknown = (await configured.get("/api/enforcer/artist", params={"name": "Nobody"})).json()
    assert unknown["known"] is False and unknown["genre"] == ""


@respx.mock
async def test_setting_a_genre_saves_it_then_applies_only_that_artist(configured):
    put = respx.put(f"{BASE}/artist").respond(json={"ok": True})
    apply = respx.post(f"{BASE}/apply").respond(json={"id": "abc", "state": "running"})
    r = (await configured.put("/api/enforcer/genre", json={"name": "New Band", "genre": "Indie"})).json()
    assert r["job"]["id"] == "abc"
    assert json.loads(put.calls.last.request.content) == {"name": "New Band", "genre": "Indie"}
    assert json.loads(apply.calls.last.request.content) == {"mode": "selected", "artists": ["New Band"]}


@respx.mock
async def test_enforcer_validation_errors_are_passed_through(configured):
    respx.put(f"{BASE}/artist").respond(422, json={"detail": "Single genre only (no ';', '|', or '/')."})
    r = await configured.put("/api/enforcer/genre", json={"name": "X", "genre": "a/b"})
    assert r.status_code == 502 and "Single genre only" in r.json()["detail"]


@respx.mock
async def test_notify_rescans_then_wakes_the_watcher(configured):
    scan = respx.post(f"{BASE}/scan").respond(json={"artists": 1})
    wake = respx.post(f"{BASE}/watcher/run").respond(json={"ok": True})
    assert (await configured.post("/api/enforcer/notify")).json() == {"ok": True}
    assert scan.called and wake.called


@respx.mock
async def test_for_folder_maps_destination_folder_to_artist(client, library, tmp_path, monkeypatch):
    from filestomb.config import Settings
    from filestomb.web.server import create_app

    dest = library / "Clean"
    (dest / "H" / "Hole" / "Album").mkdir(parents=True)
    app = create_app(Settings(app_name="T", app_version="0", contact="t@example.com", api_base_url="https://musicbrainz.org/ws/2",
                              music_root=library, picard_dest_root=str(dest)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.put("/api/settings", json={"enforcer_url": "http://enforcer:8320"})
        respx.get(f"{BASE}/state").respond(json=STATE)
        r = await c.get("/api/enforcer/for-folder", params={"path": "Clean/H/Hole/Album"})
        assert r.json() == {"name": "Hole"}
        assert (await c.get("/api/enforcer/for-folder", params={"path": "Artist One"})).status_code == 422

"""The Lidarr hand-off, against a mocked Lidarr API."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from filestomb import lidarr
from filestomb.lidarr import LidarrClient, LidarrError, to_lidarr_path

BASE = "http://lidarr:8686/api/v1"
REL = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-2222-3333-4444-555555555555"
RG = "e6b486b3-68e7-331c-a078-94fd71d61877"
ROOT = "/data/Media/Audio/Music/Sources/Clean"
FOLDER = f"{ROOT}/The Cranberries/Everybody Else"
ROOTFOLDER = {"path": ROOT, "defaultQualityProfileId": 3, "defaultMetadataProfileId": 2, "defaultTags": []}


def album_json(monitored_release: str | None = None, artist_path: str = f"{ROOT}/The Cranberries") -> dict:
    return {
        "id": 42, "title": "Everybody Else", "foreignAlbumId": RG, "artistId": 7, "monitored": True,
        "artist": {"id": 7, "path": artist_path, "foreignArtistId": "art-1"},
        "releases": [
            {"foreignReleaseId": REL, "monitored": monitored_release == REL},
            {"foreignReleaseId": OTHER, "monitored": monitored_release == OTHER},
        ],
    }


def call_names(mock) -> list[str]:
    return [f"{c.request.method} {c.request.url.path.removeprefix('/api/v1')}" for c in mock.calls]


async def send(client, **kw):
    return await client.send_album(release_mbid=REL, release_group_mbid=RG, album_folder_lidarr=FOLDER, root_folder=ROOT, expected_tracks=2, **kw)


@pytest.fixture
def client():
    return LidarrClient("http://lidarr:8686", "key")


def command_ok(mock):
    mock.post(f"{BASE}/command").respond(json={"id": 5})
    mock.get(f"{BASE}/command/5").respond(json={"id": 5, "status": "completed"})


@respx.mock
async def test_adds_new_album_in_place_pins_release_and_rescans(client):
    respx.get(f"{BASE}/album", params={"foreignAlbumId": RG}).side_effect = [
        httpx.Response(200, json=[]),
    ]
    respx.get(f"{BASE}/album/lookup").respond(json=[{"title": "Everybody Else", "foreignAlbumId": RG, "artist": {"foreignArtistId": "art-1", "artistName": "The Cranberries"}}])
    respx.get(f"{BASE}/rootfolder").respond(json=[ROOTFOLDER])
    respx.get(f"{BASE}/artist").respond(json=[])
    added = respx.post(f"{BASE}/album").respond(json=album_json())
    respx.get(f"{BASE}/album/42").respond(json=album_json())
    put = respx.put(f"{BASE}/album/42").respond(json=album_json(REL))
    command_ok(respx)
    respx.get(f"{BASE}/trackfile").respond(json=[{"path": f"{FOLDER}/01.flac"}, {"path": f"{FOLDER}/02.flac"}])

    out = await send(client)
    assert out.ok and "left where they are" in out.summary
    import json
    body = json.loads(added.calls.last.request.content)
    assert body["artist"]["path"] == f"{ROOT}/The Cranberries"  # existing folder, so Lidarr moves nothing
    assert body["artist"]["qualityProfileId"] == 3 and body["artist"]["metadataProfileId"] == 2
    assert body["addOptions"]["searchForNewAlbum"] is False and body["artist"]["addOptions"]["searchForMissingAlbums"] is False
    pinned = json.loads(put.calls.last.request.content)["releases"]
    assert [r["monitored"] for r in pinned] == [True, False]
    # No search, no manual import (which would move files): only a rescan command.
    assert json.loads(respx.calls[-3].request.content)["name"] == "RescanArtist"
    assert not any("manualimport" in n.lower() for n in call_names(respx))


@respx.mock
async def test_existing_album_with_pinned_release_just_rescans(client):
    respx.get(f"{BASE}/album", params={"foreignAlbumId": RG}).respond(json=[album_json(REL)])
    respx.get(f"{BASE}/album/42").respond(json=album_json(REL))
    command_ok(respx)
    respx.get(f"{BASE}/trackfile").respond(json=[{"path": f"{FOLDER}/a.flac"}])
    out = await send(client)
    assert not out.ok and "only mapped 1 of 2" in out.summary  # partial mapping is reported, not hidden
    assert "PUT /album/42" not in call_names(respx)


@respx.mock
async def test_refuses_when_lidarr_has_the_artist_elsewhere(client):
    respx.get(f"{BASE}/album", params={"foreignAlbumId": RG}).respond(json=[album_json(artist_path="/data/Other/The Cranberries")])
    with pytest.raises(LidarrError, match="Nothing was changed"):
        await send(client)
    assert all(m.startswith("GET") for m in call_names(respx))


@respx.mock
async def test_refuses_files_outside_the_lidarr_root(client):
    with pytest.raises(LidarrError, match="root folder"):
        await client.send_album(release_mbid=REL, release_group_mbid=RG, album_folder_lidarr="/data/Elsewhere/A/B", root_folder=ROOT, expected_tracks=2)
    assert respx.calls.call_count == 0


@respx.mock
async def test_release_unknown_to_lidarr_is_an_error(client):
    a = album_json()
    a["releases"] = [{"foreignReleaseId": OTHER, "monitored": True}]
    respx.get(f"{BASE}/album", params={"foreignAlbumId": RG}).respond(json=[a])
    respx.get(f"{BASE}/album/42").respond(json=a)
    with pytest.raises(LidarrError, match="exact release"):
        await send(client)


@respx.mock
async def test_dry_run_changes_nothing(client):
    respx.get(f"{BASE}/album", params={"foreignAlbumId": RG}).respond(json=[album_json()])
    respx.get(f"{BASE}/album/42").respond(json=album_json())
    out = await send(client, dry_run=True)
    assert out.ok and "Dry run" in out.summary
    assert all(m.startswith("GET") for m in call_names(respx))


@respx.mock
async def test_bad_key_and_unreachable_are_reported(client):
    respx.get(f"{BASE}/system/status").respond(401)
    with pytest.raises(LidarrError, match="API key"):
        await client.status()
    respx.get(f"{BASE}/rootfolder").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(LidarrError, match="Couldn't reach"):
        await client.root_folders()


def test_path_translation(tmp_path: Path):
    root = tmp_path / "music"
    (root / "Media" / "Clean" / "A" / "B").mkdir(parents=True)
    assert to_lidarr_path(root / "Media/Clean/A/B", root, "/data") == "/data/Media/Clean/A/B"
    with pytest.raises(LidarrError):
        to_lidarr_path(tmp_path / "elsewhere", root, "/data")


# -- HTTP layer ---------------------------------------------------------------

from tests.test_web import client as web_client, library  # noqa: E402,F401


@respx.mock
async def test_settings_roundtrip_and_test_endpoint(web_client):
    saved = (await web_client.put("/api/settings", json={
        "lidarr_url": "http://lidarr:8686", "lidarr_api_key": "sekret", "lidarr_root_folder": ROOT, "lidarr_auto": "1",
    })).json()
    assert saved["lidarr_url"]["value"] == "http://lidarr:8686" and "sekret" not in str(saved)
    assert (await web_client.get("/api/lidarr/status")).json() == {"configured": True, "auto": True, "url": "http://lidarr:8686"}
    respx.get(f"{BASE}/system/status").respond(json={"version": "2.9"})
    respx.get(f"{BASE}/rootfolder").respond(json=[ROOTFOLDER])
    result = (await web_client.post("/api/settings/test-lidarr")).json()
    assert result["version"] == "2.9" and result["root_folder_found"] is True


async def test_send_requires_configuration(web_client):
    r = await web_client.post("/api/lidarr/send", json={"path": "Artist One/Great Album", "release_mbid": REL})
    assert r.status_code == 422

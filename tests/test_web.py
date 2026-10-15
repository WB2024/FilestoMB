"""API tests for the web backend, driven through the real ASGI app with
MusicBrainz's HTTP API mocked by respx."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from filestomb.config import Settings
from filestomb.web.server import create_app


@pytest.fixture
def library(tmp_path: Path, make_flac) -> Path:
    root = tmp_path / "library"
    album = root / "Artist One" / "Great Album"
    make_flac(
        {"title": "Opener", "artist": "Artist One", "album": "Great Album", "tracknumber": "1", "date": "2020-05-01"},
        album,
    )
    make_flac(
        {"title": "Closer", "artist": "Artist One", "album": "Great Album", "tracknumber": "2", "date": "2020-05-01"},
        album,
    )
    (album / "cover.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    (root / "Empty Folder").mkdir()
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "x.txt").write_text("nope")
    return root


@pytest.fixture
async def client(library: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    settings = Settings(
        app_name="T", app_version="0", contact="t@example.com",
        api_base_url="https://musicbrainz.org/ws/2", music_root=library,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_config_and_index(client):
    config = (await client.get("/api/config")).json()
    assert config["library_exists"] is True
    assert "Official" in config["options"]["release_statuses"]
    assert "Album" in config["options"]["rg_primary_types"]
    index = await client.get("/")
    assert index.status_code == 200 and "FilesToMB" in index.text
    # Assets are version-stamped and always revalidated, so updates reach the browser.
    assert "__ASSET_VERSION__" not in index.text and "/static/app.js?v=" in index.text
    assert (await client.get("/static/app.js")).headers["cache-control"] == "no-cache"


async def test_browse_flags_albums(client):
    data = (await client.get("/api/browse", params={"path": "Artist One"})).json()
    assert [d["name"] for d in data["dirs"]] == ["Great Album"]
    assert data["dirs"][0]["has_audio"] is True
    assert [c["name"] for c in data["crumbs"]] == ["library", "Artist One"]
    root = (await client.get("/api/browse")).json()
    assert {d["name"]: d["has_audio"] for d in root["dirs"]} == {"Artist One": False, "Empty Folder": False}


@pytest.mark.parametrize("path", ["..", "../secret", "Artist One/../../secret", "/../secret"])
async def test_browse_rejects_escape(client, path):
    response = await client.get("/api/browse", params={"path": path})
    assert response.status_code in (400, 404)
    assert "x.txt" not in response.text


async def test_scan_and_cover(client):
    album = (await client.post("/api/scan", json={"path": "Artist One/Great Album"})).json()
    assert album["title"] == "Great Album" and album["artist"] == "Artist One"
    assert [t["title"] for t in album["tracks"]] == ["Opener", "Closer"]
    assert album["cover"]["filename"] == "cover.jpg"
    cover = await client.get("/api/cover", params={"path": "Artist One/Great Album", "download": "1"})
    assert cover.status_code == 200 and cover.content.startswith(b"\xff\xd8")
    assert "attachment" in cover.headers["content-disposition"]
    assert (await client.post("/api/scan", json={"path": "Empty Folder"})).status_code == 404


@respx.mock
async def test_match(client):
    respx.get("https://musicbrainz.org/ws/2/artist").respond(json={"artists": [{"id": "a1", "name": "Artist One", "score": 100}]})
    respx.get("https://musicbrainz.org/ws/2/release-group").respond(json={"release-groups": []})
    respx.get("https://musicbrainz.org/ws/2/release").respond(json={"releases": [{"id": "r1", "title": "Great Album", "score": 60}]})
    data = (await client.post("/api/match", json={"title": "Great Album", "artist": "Artist One"})).json()
    assert data["artist"]["status"] == "matched" and data["artist"]["selected_mbid"] == "a1"
    assert data["release-group"]["status"] == "missing"
    assert data["release"]["status"] == "ambiguous"
    assert "label" not in data


@respx.mock
async def test_match_reports_musicbrainz_failure(client, monkeypatch):
    monkeypatch.setattr("filestomb.mb.client.RETRY_DELAY", 0)
    respx.get("https://musicbrainz.org/ws/2/artist").respond(503)
    response = await client.post("/api/match", json={"title": "x", "artist": "y"})
    assert response.status_code == 502


async def test_seed_endpoints(client):
    artist = (await client.post("/api/seed/artist", json={"name": "Artist One"})).json()["url"]
    assert artist.startswith("https://musicbrainz.org/artist/create?") and "edit-artist.name=Artist+One" in artist

    rg = (await client.post("/api/seed/release-group", json={
        "title": "Great Album", "artist": "Artist One", "primary_type": "Album", "secondary_types": ["Live"],
    })).json()["url"]
    assert "primary_type_id=1" in rg and "secondary_type_ids.0=6" in rg

    seeded = (await client.post("/api/seed/release", json={
        "album": {"title": "Great Album", "artist": "Artist One", "date": "2020-05-01", "label": "L", "tracks": [
            {"title": "Opener", "track_number": "1", "length_ms": 1000},
        ]},
        "artist_mbid": "https://musicbrainz.org/artist/76df3287-6cda-33eb-8e9a-044b5e15ffdd",
        "details": {"status": "Official", "external_links": ["https://example.com", " "]},
    })).json()
    fields = seeded["fields"]
    assert seeded["action"] == "https://musicbrainz.org/release/add"
    assert fields["artist_credit.names.0.mbid"] == "76df3287-6cda-33eb-8e9a-044b5e15ffdd"
    assert fields["events.0.date.year"] == "2020" and fields["status"] == "Official"
    assert fields["mediums.0.track.0.name"] == "Opener" and fields["urls.0.url"] == "https://example.com"
    assert "urls.1.url" not in fields and fields["labels.0.name"] == "L"


async def test_login_not_configured(client):
    assert (await client.get("/api/auth/status")).json() == {"configured": False, "logged_in": False, "username": ""}
    assert (await client.post("/api/auth/start")).status_code == 400
    assert (await client.get("/api/collections")).status_code == 401


async def test_userscript_is_templated(client):
    response = await client.get("/filestomb.user.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    text = response.text
    assert "==UserScript==" in text and "__BASE_URL__" not in text and "__VERSION__" not in text
    assert "// @match        http://test/*" in text and "// @connect      test" in text
    assert "// @downloadURL  http://test/filestomb.user.js" in text


async def test_job_and_captures(client):
    assert (await client.get("/api/job")).json() == {"active": False}
    job = {"path": "Artist One/Great Album", "title": "Great Album", "artist": "Artist One", "has_cover": True, "cover_filename": "cover.jpg"}
    assert (await client.put("/api/job", json=job)).status_code == 200
    assert (await client.get("/api/job")).json()["cover_filename"] == "cover.jpg"

    mbid = "76df3287-6cda-33eb-8e9a-044b5e15ffdd"
    assert (await client.post("/api/job/capture", json={"entity": "release", "mbid": mbid, "name": "X"})).status_code == 200
    assert (await client.post("/api/job/capture", json={"entity": "bogus", "mbid": mbid})).status_code == 422
    assert (await client.get("/api/job")).json()["release_mbid"] == mbid
    taken = (await client.get("/api/job/captures")).json()["captures"]
    assert taken == [{"entity": "release", "mbid": mbid, "name": "X"}]
    assert (await client.get("/api/job/captures")).json()["captures"] == []

    bad = dict(job, path="../secret")
    assert (await client.put("/api/job", json=bad)).status_code in (400, 404)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ALBUM = "Artist One/Great Album"


async def test_upload_cover_overrides_and_resets(client, library):
    # Upload beats the auto-detected cover.jpg, and shows up everywhere.
    response = await client.put("/api/cover", params={"path": ALBUM, "filename": "my front.png"}, content=PNG)
    assert response.status_code == 200
    assert response.json() == {"filename": "my_front.png", "bytes": len(PNG), "custom": True}
    served = await client.get("/api/cover", params={"path": ALBUM})
    assert served.content == PNG and served.headers["content-type"] == "image/png"
    scanned = (await client.post("/api/scan", json={"path": ALBUM})).json()
    assert scanned["cover"]["custom"] is True

    reset = (await client.delete("/api/cover", params={"path": ALBUM})).json()
    assert reset["cover"]["filename"] == "cover.jpg" and reset["cover"]["custom"] is False
    assert (await client.get("/api/cover", params={"path": ALBUM})).content.startswith(b"\xff\xd8")


async def test_upload_cover_for_album_without_art(client, library):
    folder = library / "Bare"
    folder.mkdir()
    (library / "Bare" / "x.mp3").write_bytes(b"")
    assert (await client.get("/api/cover", params={"path": "Bare"})).status_code == 404
    ok = await client.put("/api/cover", params={"path": "Bare"}, content=PNG)
    assert ok.status_code == 200 and (await client.get("/api/cover", params={"path": "Bare"})).content == PNG


@pytest.mark.parametrize("kind,status", [("empty", 422), ("not-an-image", 415), ("too-big", 413)])
async def test_upload_cover_rejects_bad_input(client, kind, status):
    body = {"empty": b"", "not-an-image": b"not an image at all", "too-big": b"\xff\xd8\xff" + b"0" * (20 * 1024 * 1024)}[kind]
    response = await client.put("/api/cover", params={"path": ALBUM}, content=body)
    assert response.status_code == status


async def test_pick_cover_from_folder(client, library):
    scans = library / "Artist One" / "Great Album" / "scans"
    scans.mkdir()
    (scans / "front.png").write_bytes(PNG)
    (scans / "notes.txt").write_text("skip me")

    images = (await client.get("/api/images", params={"path": ALBUM})).json()["images"]
    assert sorted(i["name"] for i in images) == ["cover.jpg", "scans/front.png"]
    assert (await client.get("/api/image", params={"path": ALBUM, "name": "scans/front.png"})).content == PNG

    picked = (await client.post("/api/cover/use", json={"path": ALBUM, "image": "scans/front.png"})).json()
    assert picked["filename"] == "front.png" and picked["custom"] is True
    assert (await client.get("/api/cover", params={"path": ALBUM})).content == PNG


@pytest.mark.parametrize("name", ["../../../secret/x.txt", "../../Empty Folder", "scans/notes.txt", "/etc/passwd"])
async def test_image_picker_blocks_escapes_and_non_images(client, name):
    assert (await client.get("/api/image", params={"path": ALBUM, "name": name})).status_code in (400, 404)
    assert (await client.post("/api/cover/use", json={"path": ALBUM, "image": name})).status_code in (400, 404)


@respx.mock
async def test_lookup_finds_new_entities_by_browsing(client):
    # Search can lag behind new edits, so /api/lookup browses from the parent
    # entity instead: artist -> release group -> release.
    artist, group = "76df3287-6cda-33eb-8e9a-044b5e15ffdd", "11111111-2222-3333-4444-555555555555"
    rg_route = respx.get("https://musicbrainz.org/ws/2/release-group").respond(json={"release-groups": [
        {"id": group, "title": "Great  Album!", "primary-type": "Album"},
        {"id": "other", "title": "Something Else"},
    ]})
    rel_route = respx.get("https://musicbrainz.org/ws/2/release").respond(json={"releases": [
        {"id": "rel-1", "title": "Great Album", "date": "2020-05-01"},
    ]})

    found = (await client.post("/api/lookup", json={"title": "great album", "artist_mbid": artist})).json()
    assert [c["mbid"] for c in found["release-group"]] == [group]
    assert [c["mbid"] for c in found["release"]] == ["rel-1"]  # chained off the single group found
    assert rg_route.calls.last.request.url.params["artist"] == artist
    assert rel_route.calls.last.request.url.params["release-group"] == group

    # With the group already known, only the release is browsed.
    rg_calls_before = len(rg_route.calls)
    again = (await client.post("/api/lookup", json={"title": "Great Album", "release_group_mbid": group})).json()
    assert again["release-group"] == [] and again["release"][0]["mbid"] == "rel-1"
    assert len(rg_route.calls) == rg_calls_before

    # Nothing to browse from -> nothing found, no requests.
    assert (await client.post("/api/lookup", json={"title": "x"})).json() == {"release-group": [], "release": []}


async def test_job_carries_awaiting_names_for_userscript(client):
    job = {"path": ALBUM, "title": "Great Album", "artist": "Artist One", "awaiting": ["release-group", "bogus"],
           "names": {"release-group": "Great Album"}}
    assert (await client.put("/api/job", json=job)).status_code == 200
    stored = (await client.get("/api/job")).json()
    assert stored["awaiting"] == ["release-group"] and stored["names"] == {"release-group": "Great Album"}
    assert "expected.some((n) => norm(pageName()) === norm(n))" in (await client.get("/filestomb.user.js")).text


async def test_favourites_roundtrip(client, library):
    assert (await client.get("/api/favourites")).json() == {"favourites": []}
    added = (await client.post("/api/favourites", json={"path": "Artist One/Great Album"})).json()["favourites"]
    assert added == [{"path": "Artist One/Great Album", "name": "Great Album", "parent": "Artist One"}]
    await client.post("/api/favourites", json={"path": "Artist One/Great Album"})  # idempotent
    await client.post("/api/favourites", json={"path": "Empty Folder"})
    listed = (await client.get("/api/favourites")).json()["favourites"]
    assert [f["path"] for f in listed] == ["Artist One/Great Album", "Empty Folder"]
    assert listed[1]["parent"] == ""

    # A favourite whose folder has since gone away is hidden rather than breaking the list.
    (library / "Empty Folder").rmdir()
    assert [f["path"] for f in (await client.get("/api/favourites")).json()["favourites"]] == ["Artist One/Great Album"]

    after = (await client.delete("/api/favourites", params={"path": "Artist One/Great Album"})).json()
    assert after == {"favourites": []}


@pytest.mark.parametrize("path,status", [("", 422), ("../secret", 400), ("Nope/Nothing", 404), ("Artist One/Great Album/cover.jpg", 404)])
async def test_favourites_validate_paths(client, path, status):
    assert (await client.post("/api/favourites", json={"path": path})).status_code == status


import zipfile


def _zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)


async def test_browse_lists_archives(client, library):
    _zip(library / "Artist One" / "Album Download.zip", {"x/01.flac": b"a"})
    (library / "Artist One" / "notes.txt").write_text("x")
    listing = (await client.get("/api/browse", params={"path": "Artist One"})).json()
    assert listing["archives"] == [{"name": "Album Download.zip", "path": "Artist One/Album Download.zip", "bytes": (library / "Artist One" / "Album Download.zip").stat().st_size}]
    assert listing["writable"] is True
    assert (await client.get("/api/browse")).json()["archives"] == []


async def test_extract_then_browse_new_folder(client, library):
    from filestomb import archives

    if archives.find_sevenzip() is None:
        pytest.skip("7-Zip is not installed")
    _zip(library / "Artist One" / "Second Album.zip", {"01.flac": b"a", "02.flac": b"b"})
    result = (await client.post("/api/extract", json={"path": "Artist One/Second Album.zip"})).json()
    assert result == {"path": "Artist One/Second Album", "name": "Second Album", "files": 2}
    listing = (await client.get("/api/browse", params={"path": "Artist One"})).json()
    assert "Second Album" in [d["name"] for d in listing["dirs"]]
    assert (library / "Artist One" / "Second Album.zip").exists()


@pytest.mark.parametrize("path,status", [("Artist One/Great Album/cover.jpg", 422), ("Nope.zip", 404), ("../secret/x.txt", 400), ("Empty Folder", 404)])
async def test_extract_rejects_bad_targets(client, path, status):
    assert (await client.post("/api/extract", json={"path": path})).status_code == status


async def test_extract_reports_bad_archives(client, library):
    (library / "Empty Folder" / "broken.zip").write_bytes(b"not really a zip")
    response = await client.post("/api/extract", json={"path": "Empty Folder/broken.zip"})
    assert response.status_code == 422 and response.json()["detail"]


@respx.mock
async def test_match_splits_a_credit_into_separate_artist_searches(client):
    searches = []

    def artist_search(request):
        searches.append(request.url.params["query"])
        return httpx.Response(200, json={"artists": []})

    respx.get("https://musicbrainz.org/ws/2/artist").mock(side_effect=artist_search)
    respx.get("https://musicbrainz.org/ws/2/release-group").respond(json={"release-groups": []})
    respx.get("https://musicbrainz.org/ws/2/release").respond(json={"releases": []})
    out = (await client.post("/api/match", json={"title": "T", "artist": "A & B", "artists": ["A", "B"]})).json()
    assert {"artist", "artist-2", "release-group", "release"} <= set(out)
    assert out["artist"]["query"] == "A" and out["artist-2"]["query"] == "B"
    assert len(searches) == 2  # the combined "A & B" string is not searched as an artist


async def test_release_seed_endpoint_passes_the_split_credit(client):
    body = {"album": {"title": "T", "artist": "A & B", "tracks": []}, "artists": [{"name": "A", "mbid": None}, {"name": "B", "mbid": None}], "join_phrase": " & "}
    fields = (await client.post("/api/seed/release", json=body)).json()["fields"]
    assert fields["artist_credit.names.0.join_phrase"] == " & " and fields["artist_credit.names.1.name"] == "B"


@respx.mock
async def test_manual_search_falls_back_from_exact_phrase_to_any_order(client):
    queries = []

    def release_group_search(request):
        queries.append(request.url.params["query"])
        if len(queries) == 1:
            return httpx.Response(200, json={"release-groups": []})
        return httpx.Response(200, json={"release-groups": [{
            "id": "rg-1", "title": "Killamangiro", "score": 88, "primary-type": "EP", "first-release-date": "2004",
            "artist-credit": [{"name": "Babyshambles", "joinphrase": ""}],
        }]})

    respx.get("https://musicbrainz.org/ws/2/release-group").mock(side_effect=release_group_search)
    r = (await client.post("/api/search", json={"entity": "release-group", "name": "Killamangiro EP", "artist": "Babyshambles"})).json()
    assert queries[0].startswith('releasegroup:"Killamangiro EP"') and 'artist:"Babyshambles"' in queries[0]
    assert "AND" in queries[1] and '"Killamangiro EP"' not in queries[1]  # second try: the words in any order
    hit = r["results"][0]
    assert hit["mbid"] == "rg-1" and hit["artist"] == "Babyshambles" and hit["detail"] == "EP · 2004"


@respx.mock
async def test_manual_search_with_no_results_and_bad_input(client):
    respx.get("https://musicbrainz.org/ws/2/artist").respond(json={"artists": []})
    assert (await client.post("/api/search", json={"entity": "artist", "name": "Zzzz Nobody"})).json() == {"results": []}
    assert (await client.post("/api/search", json={"entity": "artist", "name": "  "})).status_code == 422
    assert (await client.post("/api/search", json={"entity": "recording", "name": "x"})).status_code == 422

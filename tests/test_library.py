"""Clean-library check: index, quality comparison, replace-by-archiving, API and batch guard."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import mutagen
import pytest

from filestomb import integrations, library
from filestomb.config import Settings
from filestomb.web.server import create_app

FFMPEG = shutil.which("ffmpeg")
RELEASE = "7ba9d555-ac48-457f-a6a1-299dcd560172"
GROUP = "b2185948-5d94-4cca-8538-bcfdc1d7848f"
OTHER = "11111111-2222-3333-4444-555555555555"


def q(**kw):
    base = {"tracks": 10, "formats": {"FLAC": 10}, "format": "FLAC", "lossless": True, "bits": 16, "sample_rate": 44100, "kbps": 900, "seconds": 2400, "bytes": 3e8}
    return {**base, **kw}


def lossy(fmt="MP3", kbps=320, **kw):
    return q(formats={fmt: 10}, format=fmt, lossless=False, bits=0, kbps=kbps, **kw)


# ---------------------------------------------------------------- comparison (pure)


def test_lossless_beats_lossy_either_way():
    assert library.compare(q(), lossy())["verdict"] == "existing_better"
    assert library.compare(lossy(), q())["verdict"] == "new_better"


def test_lossless_resolution_decides_between_lossless_copies():
    assert library.compare(q(), q(bits=24, sample_rate=96000))["verdict"] == "new_better"
    assert library.compare(q(bits=24, sample_rate=96000), q())["verdict"] == "existing_better"
    assert library.compare(q(), q())["verdict"] == "similar"


def test_lossy_bitrate_decides_with_codec_weighting_and_tolerance():
    assert library.compare(lossy(kbps=128), lossy(kbps=320))["verdict"] == "new_better"
    assert library.compare(lossy(kbps=320), lossy(kbps=320))["verdict"] == "similar"
    assert library.compare(lossy(kbps=320), lossy(kbps=300))["verdict"] == "similar"  # within tolerance
    # 192k Opus is worth more than 192k MP3
    assert library.compare(lossy("MP3", 192), lossy("Opus", 192))["verdict"] == "new_better"


def test_track_count_difference_is_called_out():
    cmp = library.compare(q(tracks=12), q(tracks=11))
    assert any("12 existing vs 11 new" in r for r in cmp["reasons"])


# ---------------------------------------------------------------- files


@pytest.fixture
def clean(tmp_path, make_flac):
    root = tmp_path / "lib" / "Clean"
    folder = root / "A" / "Artist" / "[2020] Album"
    a = make_flac({"title": "One", "musicbrainz_albumid": RELEASE, "musicbrainz_releasegroupid": GROUP}, folder)
    b = make_flac({"title": "Two", "musicbrainz_albumid": RELEASE, "musicbrainz_releasegroupid": GROUP}, folder)
    return tmp_path / "lib", root, folder, [a, b]


def test_index_finds_releases_and_notices_changes(clean, tmp_path):
    lib, root, folder, files = clean
    index = library.LibraryIndex(tmp_path / "idx.db")
    index.refresh(root)
    assert index.find_release(RELEASE) == [("A/Artist/[2020] Album", 2, 2)]
    assert index.find_group(GROUP) and not index.find_release(OTHER)
    # retag in place (no new files, directory untouched): the next refresh must notice
    for f in files:
        audio = mutagen.File(f, easy=True)
        audio["musicbrainz_albumid"] = OTHER
        audio.save()
    index.refresh(root)
    assert not index.find_release(RELEASE) and index.find_release(OTHER)
    shutil.rmtree(folder)
    index.refresh(root)
    assert index.find_release(OTHER) == []


def test_archive_moves_a_whole_folder_and_never_deletes(clean, tmp_path):
    lib, root, folder, files = clean
    result = library.archive_existing(root, lib / "Replaced", folder, RELEASE, "20260101-000000")
    assert result["whole_folder"] and result["files"] == 2
    assert not folder.exists()
    assert len(list((lib / "Replaced" / "20260101-000000" / "A" / "Artist" / "[2020] Album").glob("*.flac"))) == 2


def test_archive_only_moves_this_releases_files_when_editions_share_a_folder(clean, make_flac):
    lib, root, folder, files = clean
    other = make_flac({"title": "Z", "musicbrainz_albumid": OTHER}, folder)
    result = library.archive_existing(root, lib / "Replaced", folder, RELEASE, "s")
    assert not result["whole_folder"] and result["files"] == 2
    assert other.exists() and not files[0].exists()


def test_archive_refuses_unsafe_requests(clean, tmp_path):
    lib, root, folder, _ = clean
    with pytest.raises(library.LibraryError):
        library.archive_existing(root, lib / "Replaced", tmp_path, RELEASE, "s")  # outside the library
    with pytest.raises(library.LibraryError):
        library.archive_existing(root, folder / "inside", folder, RELEASE, "s")  # archive inside the album
    with pytest.raises(library.LibraryError):
        library.archive_existing(root, lib / "Replaced", folder, OTHER, "s")  # no files for that release


def test_summarize_reads_real_audio(clean):
    _, _, _, files = clean
    s = library.summarize(files)
    assert s["format"] == "FLAC" and s["lossless"] and s["tracks"] == 2
    assert "FLAC" in library.describe(s)


# ---------------------------------------------------------------- API + batch guard


@pytest.fixture
async def web(tmp_path, make_flac, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    lib = tmp_path / "lib"
    existing = lib / "Clean" / "A" / "Artist" / "[2020] Album"
    for n in (1, 2):
        make_flac({"title": f"T{n}", "musicbrainz_albumid": RELEASE}, existing)
    new = lib / "Unmanaged" / "Album"
    for n in (1, 2):
        make_flac({"title": f"T{n}"}, new)
    integrations.update({"clean_library": str(lib / "Clean")})
    app = create_app(Settings("T", "0", "t@example.com", "https://musicbrainz.org/ws/2", music_root=lib))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, lib, existing, new, app


async def wait_indexed(client):
    import asyncio
    for _ in range(100):
        s = (await client.get("/api/library/status")).json()
        if s["last_built"] and not s["building"]:
            return s
        await asyncio.sleep(0.05)
    raise AssertionError("index never finished")


async def test_check_reports_existing_copy_with_comparison(web):
    client, lib, existing, new, _ = web
    status = await wait_indexed(client)
    assert status["configured"] and status["folders"] == 1 and status["archive"].endswith("/lib/Replaced")
    res = (await client.post("/api/library/check", json={"path": "Unmanaged/Album", "release_mbid": RELEASE})).json()
    assert len(res["matches"]) == 1 and res["matches"][0]["folder"] == "Clean/A/Artist/[2020] Album"
    assert res["matches"][0]["verdict"] == "similar" and "FLAC" in res["matches"][0]["existing"]
    none = (await client.post("/api/library/check", json={"path": "Unmanaged/Album", "release_mbid": OTHER})).json()
    assert none["matches"] == []


async def test_replace_archives_the_existing_copy_and_refuses_other_folders(web):
    client, lib, existing, new, _ = web
    await wait_indexed(client)
    bad = await client.post("/api/library/replace", json={"path": "Unmanaged/Album", "release_mbid": RELEASE, "folder": "Unmanaged/Album"})
    assert bad.status_code == 422 and new.exists()
    ok = await client.post("/api/library/replace", json={"path": "Unmanaged/Album", "release_mbid": RELEASE, "folder": "Clean/A/Artist/[2020] Album"})
    assert ok.status_code == 200 and not existing.exists()
    assert list((lib / "Replaced").rglob("*.flac"))
    assert len(list(new.glob("*.flac"))) == 2  # the album being imported is untouched
    again = (await client.post("/api/library/check", json={"path": "Unmanaged/Album", "release_mbid": RELEASE})).json()
    assert again["matches"] == []


async def test_not_configured_and_batch_guard(web, tmp_path):
    client, lib, existing, new, app = web
    await wait_indexed(client)
    msg = await app.state.batch.before_import(new, RELEASE)
    assert "Already in your library at Clean/A/Artist/[2020] Album" in msg
    assert await app.state.batch.before_import(new, OTHER) is None
    integrations.update({"clean_library": ""})
    assert (await client.post("/api/library/check", json={"path": "Unmanaged/Album", "release_mbid": RELEASE})).json() == {"configured": False, "matches": []}
    assert await app.state.batch.before_import(new, RELEASE) is None

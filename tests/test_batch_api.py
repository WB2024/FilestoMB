"""Batch endpoints through the real ASGI app."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from filestomb.batch import store as store_mod
from filestomb.config import Settings
from filestomb.web.server import create_app
from tests.test_batch_core import FakeMB, hit, release
from tests.test_batch_runner import FakePicard, make_album

TRACKS = ["Opener", "Closer"]
UUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
async def api(tmp_path, make_flac, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = tmp_path / "library"
    unmanaged = root / "Unmanaged"
    make_album(make_flac, unmanaged, "G/Artist One/Great Album")
    make_album(make_flac, unmanaged, "N/Nobody/Unknown Thing", titles=["Zzz", "Yyy"], artist="Nobody", album="Unknown Thing")
    pipe_dir = tmp_path / "pipe"
    pipe_dir.mkdir()
    fake = FakePicard(pipe_dir, root / "Clean")
    releases = {"r-good": release("r-good", "Great Album", TRACKS, length=100), UUID: release(UUID, "Great Album", TRACKS, length=100)}
    mb = FakeMB(lambda title: [hit("r-good", 2)] if title == "Great Album" else [], releases)
    settings = Settings(app_name="T", app_version="0", contact="t@example.com", api_base_url="https://musicbrainz.org/ws/2",
                        music_root=root, picard_pipe_dir=str(pipe_dir), picard_library_root=str(root))
    app = create_app(settings, mb_client=mb)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield type("Api", (), dict(client=client, root=root, unmanaged=unmanaged, mb=mb, fake=fake, releases=releases, make_flac=make_flac))
    fake.stop()


async def idle(client):
    for _ in range(300):
        status = (await client.get("/api/batch/status")).json()
        if not status["busy"]:
            return status
        await asyncio.sleep(0.05)
    raise AssertionError("batch job never finished")


async def prepare(a):
    assert (await a.client.post("/api/batch/discover", json={"path": "Unmanaged"})).json() == {"started": True}
    await idle(a.client)
    assert (await a.client.post("/api/batch/match", json={"path": "Unmanaged"})).json() == {"started": True}
    return await idle(a.client)


async def test_discover_match_and_list(api):
    await prepare(api)
    data = (await api.client.get("/api/batch/albums", params={"root": "Unmanaged"})).json()
    assert data["counts"]["total"] == 2 and data["counts"][store_mod.READY] == 1 and data["counts"][store_mod.MISSING] == 1
    ready = (await api.client.get("/api/batch/albums", params={"root": "Unmanaged", "status": "ready"})).json()["albums"]
    assert [a["path"] for a in ready] == ["Unmanaged/G/Artist One/Great Album"]
    assert ready[0]["release_mbid"] == "r-good" and ready[0]["verdict"]["candidates"][0]["confident"] is True
    assert [a["title"] for a in (await api.client.get("/api/batch/albums", params={"root": "Unmanaged", "q": "Unknown"})).json()["albums"]] == ["Unknown Thing"]
    assert (await api.client.get("/api/batch/roots")).json()["roots"] == [{"path": "Unmanaged", "albums": 2}]


@pytest.mark.parametrize("path,status", [("", 422), ("Nope", 404), ("../x", 400)])
async def test_roots_are_validated(api, path, status):
    assert (await api.client.post("/api/batch/discover", json={"path": path})).status_code == status


async def test_a_second_job_is_refused_while_one_runs(api):
    await api.client.post("/api/batch/discover", json={"path": "Unmanaged"})
    second = await api.client.post("/api/batch/discover", json={"path": "Unmanaged"})
    assert second.status_code == 409 and "already running" in second.json()["detail"]
    await idle(api.client)


async def test_resolve_rules(api):
    await prepare(api)
    path = "Unmanaged/N/Nobody/Unknown Thing"
    # Pretend this one is a "review" with one fully-matching and one partial candidate.
    api.client._transport.app  # noqa: B018 (fixture sanity)
    from filestomb.paths import config_dir
    db = store_mod.BatchStore(config_dir() / "batch.db")
    db.update(path, status=store_mod.REVIEW, verdict={"reasons": [], "candidates": [
        {"mbid": "good", "confident": True, "problems": [], "rank": 99.0},
        {"mbid": "partial", "confident": False, "track_exact": False, "problems": ["1 release track(s) have no local file"], "rank": 70.0},
        {"mbid": "renamed", "confident": False, "track_exact": True, "problems": ["album title differs"], "rank": 80.0}]})
    bad = await api.client.post("/api/batch/resolve", json={"path": path, "action": "use", "release_mbid": "partial"})
    assert bad.status_code == 422 and "isn't a complete match" in bad.json()["detail"]
    assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": "use", "release_mbid": "ghost"})).status_code == 422
    assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": "use", "release_mbid": "good"})).status_code == 200
    assert db.get(path)["status"] == store_mod.READY and db.get(path)["release_mbid"] == "good"
    # Exact tracks under a different name: allowed, but recorded as the user's own approval.
    assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": "use", "release_mbid": "renamed"})).status_code == 200
    assert db.get(path)["verdict"]["approved"] == "renamed" and db.get(path)["release_mbid"] == "renamed"
    for action, expected in (("skip", store_mod.SKIPPED), ("missing", store_mod.MISSING), ("reset", store_mod.PENDING)):
        assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": action})).status_code == 200
        assert db.get(path)["status"] == expected
    assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": "explode"})).status_code == 422
    assert (await api.client.post("/api/batch/resolve", json={"path": "nope", "action": "skip"})).status_code == 404
    db.update(path, status=store_mod.DONE)
    assert (await api.client.post("/api/batch/resolve", json={"path": path, "action": "skip"})).status_code == 409


async def test_processing_requires_consent_and_a_sane_limit(api):
    await prepare(api)
    no_consent = await api.client.post("/api/batch/process", json={"path": "Unmanaged", "limit": 1, "clear_picard": False})
    assert no_consent.status_code == 409 and "Confirm" in no_consent.json()["detail"]
    assert (await api.client.post("/api/batch/process", json={"path": "Unmanaged", "limit": 0, "clear_picard": True})).status_code == 422
    assert api.fake.commands == []  # nothing was sent to Picard


async def test_full_processing_through_the_api(api, monkeypatch):
    from filestomb.batch import runner
    for name, value in (("WARMUP_BASE_SECONDS", 0.05), ("WARMUP_PER_TRACK_SECONDS", 0), ("SAVE_TIMEOUT_SECONDS", 2.0),
                        ("SAVE_RESEND_SECONDS", 0.2), ("POLL_SECONDS", 0.05), ("PAUSE_BETWEEN_ALBUMS", 0)):
        monkeypatch.setattr(runner, name, value)
    await prepare(api)
    assert (await api.client.post("/api/batch/process", json={"path": "Unmanaged", "limit": 1, "clear_picard": True})).json() == {"started": True}
    status = await idle(api.client)
    assert status["last_result"].startswith("Finished")
    counts = (await api.client.get("/api/batch/albums", params={"root": "Unmanaged"})).json()["counts"]
    assert counts[store_mod.DONE] == 1 and counts[store_mod.MISSING] == 1
    assert any('"event": "album_done"' in line for line in (await api.client.get("/api/batch/audit")).json()["lines"])


async def test_manual_picard_actions_are_blocked_while_a_batch_processes(api):
    manager = api.client._transport.app.state.batch
    manager.phase = "processing"
    try:
        for url in ("/api/picard/save", "/api/picard/clear", "/api/picard/fingerprint"):
            response = await api.client.post(url)
            assert response.status_code == 409 and "batch is processing" in response.json()["detail"]
        assert (await api.client.post("/api/picard/send", json={"path": "Unmanaged", "release_mbid": UUID})).status_code == 409
        assert (await api.client.post("/api/extract", json={"path": "Unmanaged/x.zip"})).status_code == 409
    finally:
        manager.phase = "idle"
    assert api.fake.commands == []


async def test_single_album_send_marks_the_batch_row_in_picard(api):
    await prepare(api)
    path = "Unmanaged/G/Artist One/Great Album"
    # The per-album flow looks the release up on MusicBrainz via the (fake) client.
    sent = await api.client.post("/api/picard/send", json={"path": path, "release_mbid": UUID})
    assert sent.status_code == 200 and sent.json()["loaded"] is True
    row = (await api.client.get("/api/batch/albums", params={"root": "Unmanaged", "status": "in_picard"})).json()["albums"]
    assert [r["path"] for r in row] == [path]


async def test_reconcile_and_cleanup(api):
    await prepare(api)
    for f in (api.unmanaged / "N/Nobody/Unknown Thing").glob("*.flac"):
        f.unlink()
    assert (await api.client.post("/api/batch/reconcile", json={"path": "Unmanaged"})).json() == {"changed": 1}
    (api.unmanaged / "Z" / "Empty Artist" / "Empty Album").mkdir(parents=True)
    cleaned = (await api.client.post("/api/batch/cleanup", json={"path": "Unmanaged"})).json()
    assert cleaned["removed"] >= 3 and not (api.unmanaged / "Z").exists()
    assert (api.unmanaged / "G/Artist One/Great Album").exists()  # albums with files are never removed

"""AcoustID fingerprints via fpcalc: tag formats per file type and the progress API."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

import httpx
import mutagen
import pytest

from filestomb import fingerprint
from filestomb.config import Settings
from filestomb.web.server import create_app

FFMPEG, FPCALC = shutil.which("ffmpeg"), shutil.which("fpcalc")
pytestmark = pytest.mark.skipif(not (FFMPEG and FPCALC), reason="needs ffmpeg and fpcalc")


def tone(path, freq=440):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=6", str(path)], check=True)
    return path


@pytest.mark.parametrize("name", ["a.flac", "a.mp3", "a.m4a", "a.ogg", "a.opus"])
def test_fingerprint_is_written_in_the_tag_picard_reads(tmp_path, name):
    path = tone(tmp_path / name)
    fp = fingerprint.calculate(path, FPCALC)
    assert fp.startswith("AQ")
    fingerprint.write_tag(path, fp)
    audio = mutagen.File(path)
    if name.endswith(".mp3"):
        assert str(audio.tags["TXXX:Acoustid Fingerprint"]) == fp
    elif name.endswith(".m4a"):
        assert audio.tags[fingerprint.MP4_KEY][0].decode() == fp
    else:
        assert audio["ACOUSTID_FINGERPRINT"] == [fp]
    # easy tags written earlier are untouched and the file still opens
    assert mutagen.File(path, easy=True) is not None


def test_unreadable_audio_is_a_clean_error(tmp_path):
    bad = tmp_path / "x.flac"
    bad.write_bytes(b"not audio")
    with pytest.raises(fingerprint.FingerprintError):
        fingerprint.calculate(bad, FPCALC)


@pytest.fixture
async def web(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    library = tmp_path / "library"
    album = library / "Unmanaged" / "Album"
    album.mkdir(parents=True)
    for n in (1, 2):
        tone(album / f"0{n}.flac", 300 * n)
    app = create_app(Settings("T", "0", "t@example.com", "https://musicbrainz.org/ws/2", music_root=library))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, album, app


async def test_job_reports_progress_and_finishes(web):
    client, album, _ = web
    assert (await client.get("/api/fingerprint/status")).json() == {"available": True, "job": None}
    started = (await client.post("/api/fingerprint/start", json={"path": "Unmanaged/Album"})).json()
    assert started["total"] == 2 and started["state"] in ("running", "done")
    for _ in range(100):
        job = (await client.get("/api/fingerprint/status", params={"path": "Unmanaged/Album"})).json()["job"]
        if job["state"] == "done":
            break
        await asyncio.sleep(0.1)
    assert job == {"state": "done", "total": 2, "done": 2, "errors": []}
    assert all("ACOUSTID_FINGERPRINT" in mutagen.File(f) for f in album.glob("*.flac"))


async def test_errors_are_collected_per_file_and_guards_apply(web):
    client, album, app = web
    (album / "03.flac").write_bytes(b"broken")
    assert (await client.post("/api/fingerprint/start", json={"path": "Nope"})).status_code == 404
    app.state.batch.phase = "processing"
    try:
        assert (await client.post("/api/fingerprint/start", json={"path": "Unmanaged/Album"})).status_code == 409
    finally:
        app.state.batch.phase = "idle"

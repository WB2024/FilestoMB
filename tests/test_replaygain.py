"""ReplayGain via rsgain: command building, output parsing, file selection and the HTTP flow."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import httpx
import mutagen
import pytest

from filestomb import integrations, replaygain
from filestomb.config import Settings
from filestomb.web.server import create_app

RELEASE_ID = "7ba9d555-ac48-457f-a6a1-299dcd560172"
OTHER_ID = "11111111-2222-3333-4444-555555555555"

# Stands in for rsgain: same output shape, writes a tag when asked to (-s i).
FAKE = f"""#!{sys.executable}
import sys, mutagen
args = sys.argv[1:]
write = args[args.index("-s") + 1] == "i"
files = [a for a in args if a.endswith((".flac", ".mp3"))]
print("Filename\\tLoudness (LUFS)\\tGain (dB)\\tPeak\\t Peak (dB)\\tPeak Type\\tClipping Adjustment?")
for f in files:
    print(f"{{f}}\\t-20.00\\t2.00\\t0.5\\t-6.02\\tTrue\\tN")
    if write:
        a = mutagen.File(f); a["replaygain_track_gain"] = ["2.00 dB"]; a.save()
if "-a" in args:
    print("Album\\t-20.00\\t2.00\\t0.5\\t-6.02\\tTrue\\tN")
open(sys.argv[0] + ".args", "w").write(" ".join(args))
"""


@pytest.fixture
def fake_rsgain(tmp_path):
    path = tmp_path / "rsgain"
    path.write_text(FAKE)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_command_mirrors_the_picard_plugin_options(tmp_path):
    o = replaygain.Options(album=True, true_peak=True, target=-18, clip_mode="p", max_peak=0, opus_mode="d")
    cmd = replaygain.build_command(Path("/rsgain"), o, [Path("/a.flac")], write=False)
    assert cmd[:7] == ["/rsgain", "custom", "-O", "-p", "-s", "s", "-a"]
    assert ["-l", "-18", "-c", "p", "-m", "0", "-o", "d"] == cmd[8:16] and "-t" in cmd and cmd[-1] == "/a.flac"
    assert replaygain.build_command(Path("/rsgain"), o, [], write=True)[5] == "i"


@pytest.mark.parametrize("bad", [{"target": 0}, {"target": -40}, {"clip_mode": "x"}, {"opus_mode": "z"}])
def test_options_are_validated(bad):
    with pytest.raises(replaygain.ReplayGainError):
        replaygain.Options(**bad).validate()


def test_parse_output_rejects_unexpected_row_counts():
    out = "Filename\tL\tG\tP\tPdB\tT\tC\na.flac\t-20\t2\t0.5\t-6\tTrue\tN\n"
    with pytest.raises(replaygain.ReplayGainError):
        replaygain.parse_output(out, expect_tracks=2, album=False)
    tracks, album = replaygain.parse_output(out + "Album\t-20\t2\t0.5\t-6\tTrue\tN\n", 1, True)
    assert len(tracks) == 1 and album.filename == "Album"


def test_only_files_of_this_release_are_selected(tmp_path, make_flac):
    folder = tmp_path / "album"
    mine = make_flac({"title": "A", "musicbrainz_albumid": RELEASE_ID}, folder)
    make_flac({"title": "B", "musicbrainz_albumid": OTHER_ID}, folder)
    (folder / "cover.jpg").write_bytes(b"x")
    assert replaygain.audio_files_for_release(folder, RELEASE_ID) == [mine]
    assert len(replaygain.audio_files_for_release(folder, None)) == 2


def test_missing_binary_is_reported(tmp_path):
    with pytest.raises(replaygain.ReplayGainError, match="Settings"):
        replaygain.check_binary("")
    with pytest.raises(replaygain.ReplayGainError, match="isn't at"):
        replaygain.check_binary(str(tmp_path / "nope"))


@pytest.fixture
async def web(tmp_path, make_flac, monkeypatch, fake_rsgain):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    library = tmp_path / "library"
    album = library / "Clean" / "Great Album"
    for n in (1, 2):
        make_flac({"title": f"T{n}", "musicbrainz_albumid": RELEASE_ID}, album)
    integrations.update({"rsgain_path": str(fake_rsgain)})
    app = create_app(Settings("T", "0", "t@example.com", "https://musicbrainz.org/ws/2", music_root=library))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, album, app


async def test_scan_shows_numbers_without_writing_then_write_tags_and_remembers_options(web):
    client, album, _ = web
    status = (await client.get("/api/replaygain/status")).json()
    assert status["configured"] and status["options"]["target"] == -18.0

    body = {"path": "Clean/Great Album", "release_mbid": RELEASE_ID, "write": False, "options": {"target": -16, "clip_mode": "a", "album": True}}
    scan = (await client.post("/api/replaygain/run", json=body)).json()
    assert len(scan["tracks"]) == 2 and scan["album"] and not scan["wrote"]
    assert all("replaygain_track_gain" not in mutagen.File(f) for f in album.glob("*.flac"))

    wrote = (await client.post("/api/replaygain/run", json={**body, "write": True})).json()
    assert wrote["wrote"] and wrote["verified"] == 2
    for f in album.glob("*.flac"):
        audio = mutagen.File(f)
        assert audio["replaygain_track_gain"] == ["2.00 dB"] and audio["replaygain_reference_loudness"] == ["-16.00 LUFS"]
    # last-used choices come back next time
    options = (await client.get("/api/replaygain/status")).json()["options"]
    assert options["target"] == -16.0 and options["clip_mode"] == "a"


async def test_errors_and_batch_guard(web):
    client, _, app = web
    assert (await client.post("/api/replaygain/run", json={"path": "Nope"})).status_code == 404
    bad = await client.post("/api/replaygain/run", json={"path": "Clean/Great Album", "options": {"target": 5}})
    assert bad.status_code == 422
    nothing = await client.post("/api/replaygain/run", json={"path": "Clean/Great Album", "release_mbid": OTHER_ID})
    assert nothing.status_code == 422 and "No audio files" in nothing.json()["detail"]
    app.state.batch.phase = "processing"
    try:
        assert (await client.post("/api/replaygain/run", json={"path": "Clean/Great Album"})).status_code == 409
    finally:
        app.state.batch.phase = "idle"


@pytest.mark.skipif(not os.environ.get("RSGAIN_PATH"), reason="set RSGAIN_PATH to test against the real rsgain")
def test_real_rsgain_writes_tags(tmp_path, make_flac):
    folder = tmp_path / "album"
    files = [make_flac({"title": "A"}, folder), make_flac({"title": "B"}, folder)]
    result = replaygain.run(replaygain.check_binary(os.environ["RSGAIN_PATH"]), replaygain.Options(), files, write=True)
    assert result.verified == 2 and result.album
    assert mutagen.File(files[0])["replaygain_reference_loudness"] == ["-18.00 LUFS"]

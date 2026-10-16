"""Picard integration: the pipe protocol, track matching, and MBID tag writing."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import httpx
import mutagen
import pytest
import respx

from filestomb import picard, releasetags, tags
from filestomb.config import Settings
from filestomb.models import Track
from filestomb.web.server import create_app

RELEASE_ID = "7ba9d555-ac48-457f-a6a1-299dcd560172"
GROUP_ID = "b2185948-5d94-4cca-8538-bcfdc1d7848f"
ARTIST_ID = "94f6def3-dbfe-403b-bb40-d324c8c13fbb"


def release_json(titles: list[str], media: int = 1) -> dict:
    per = len(titles) // media
    return {
        "id": RELEASE_ID,
        "title": "Great Album",
        "date": "2020-05-01",
        "artist-credit": [{"name": "Artist One", "joinphrase": "", "artist": {"id": ARTIST_ID}}],
        "release-group": {"id": GROUP_ID},
        "media": [
            {
                "position": m + 1,
                "tracks": [
                    {
                        "id": f"track-{m}-{i}",
                        "position": i + 1,
                        "title": title,
                        "length": 180000,
                        "artist-credit": [{"artist": {"id": ARTIST_ID}}],
                        "recording": {"id": f"rec-{m}-{i}"},
                    }
                    for i, title in enumerate(titles[m * per : (m + 1) * per])
                ],
            }
            for m in range(media)
        ],
    }


def local(title: str, number: str | None, disc: str | None = None, name: str | None = None) -> Track:
    return Track(path=Path(name or f"{title}.flac"), title=title, artist="", album="", album_artist="",
                 track_number=number, disc_number=disc)


# ---------------------------------------------------------------- pipe protocol


@pytest.fixture
def fifo(tmp_path):
    """A real FIFO named like Picard's, with a reader thread that records what it receives."""
    path = tmp_path / "Picard_v2.13.3_main_pipe_file"
    os.mkfifo(path)
    received: list[bytes] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                import select
                select.select([fd], [], [], 0.05)
                data = os.read(fd, 65536)
                if data:
                    received.append(data)
            except BlockingIOError:
                pass
            finally:
                os.close(fd)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    yield tmp_path, received
    stop.set()
    thread.join(timeout=2)


def test_send_uses_picards_wire_format(fifo):
    directory, received = fifo
    picard.send(directory, ("LOAD", "/music/Unmanaged/Artist - Album (2004) [FLAC]"), ("SAVE_MATCHED", ""))
    for _ in range(40):
        if received:
            break
        threading.Event().wait(0.05)
    assert b"".join(received) == b"LOAD /music/Unmanaged/Artist - Album (2004) [FLAC]\0SAVE_MATCHED\0"


def test_find_pipe_ignores_regular_files_and_missing_dirs(tmp_path):
    (tmp_path / "Picard_v2.13.3_main_pipe_file").write_text("not a fifo")
    assert picard.find_pipe(tmp_path) is None
    assert picard.find_pipe(tmp_path / "nope") is None
    assert picard.find_pipe("") is None and picard.find_pipe(None) is None
    assert picard.is_connected(tmp_path) is False


def test_no_reader_means_picard_is_not_running(tmp_path, monkeypatch):
    os.mkfifo(tmp_path / "Picard_v2.13.3_main_pipe_file")  # a stale FIFO: nobody is listening
    monkeypatch.setattr(picard, "SEND_TIMEOUT_SECONDS", 0.2)
    assert picard.is_connected(tmp_path) is False
    with pytest.raises(picard.PicardUnavailable, match="isn't listening"):
        picard.send(tmp_path, ("SHOW", ""))
    with pytest.raises(picard.PicardUnavailable, match="wasn't found"):
        picard.send(tmp_path / "missing", ("SHOW", ""))


def test_is_connected_true_with_reader(fifo):
    directory, _ = fifo
    assert picard.is_connected(directory) is True


def test_path_translation(tmp_path):
    album = tmp_path / "Unmanaged" / "A B" / "Album"
    album.mkdir(parents=True)
    assert picard.to_picard_path(album, tmp_path, "/music") == "/music/Unmanaged/A B/Album"
    assert picard.to_picard_path(album, tmp_path, "/data/lib") == "/data/lib/Unmanaged/A B/Album"


# ---------------------------------------------------------------- matching


def test_matches_by_position_and_title():
    release = releasetags.parse_release(release_json(["Opener", "Middle Song", "Closer"]))
    plan = releasetags.match_tracks(
        [local("Opener", "1"), local("Middle Song", "2/3"), local("Closer", "3")], release
    )
    assert plan.complete
    assert [p.release_track.title for p in plan.pairs] == ["Opener", "Middle Song", "Closer"]
    assert release.artist == "Artist One" and release.release_group_id == GROUP_ID


def test_title_typos_still_match_but_wrong_tracks_do_not():
    release = releasetags.parse_release(release_json(["Black Boy Lane", "Pipey Magregor"]))
    plan = releasetags.match_tracks(
        [local("Black Boy Lane (Untitled)", "1"), local("Totally Different Song", "2")], release
    )
    assert plan.pairs[0].release_track.title == "Black Boy Lane"
    assert plan.pairs[1].release_track is None
    assert [t.title for t in plan.unmatched_release_tracks] == ["Pipey Magregor"]
    assert not plan.complete


def test_wrong_numbering_falls_back_to_titles():
    release = releasetags.parse_release(release_json(["Alpha", "Bravo", "Charlie"]))
    # Tags say 7, 8, 9 but the titles are unmistakable.
    plan = releasetags.match_tracks([local("Charlie", "9"), local("Alpha", "7"), local("Bravo", "8")], release)
    assert [p.release_track.title for p in plan.pairs] == ["Charlie", "Alpha", "Bravo"]


def test_multi_disc_uses_disc_numbers():
    release = releasetags.parse_release(release_json(["One", "Two", "One Again", "Two Again"], media=2))
    plan = releasetags.match_tracks(
        [local("One Again", "1", "2/2"), local("One", "1", "1/2"), local("Two", "2", "1/2"), local("Two Again", "2", "2")],
        release,
    )
    assert [(p.release_track.disc, p.release_track.position) for p in plan.pairs] == [(2, 1), (1, 1), (1, 2), (2, 2)]
    assert plan.complete


def test_a_release_track_is_never_claimed_twice():
    release = releasetags.parse_release(release_json(["Same Name", "Other"]))
    plan = releasetags.match_tracks([local("Same Name", "1", name="a.flac"), local("Same Name", "1", name="b.flac")], release)
    matched = [p for p in plan.pairs if p.release_track]
    assert len(matched) == 1


# ---------------------------------------------------------------- tag writing

FFMPEG = shutil.which("ffmpeg")


def make_audio(path: Path, codec_args: list[str]) -> Path:
    if FFMPEG is None:
        pytest.skip("ffmpeg is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([FFMPEG, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.2", *codec_args, "-y", str(path), "-loglevel", "error"], capture_output=True)
    if result.returncode != 0:
        pytest.skip(f"ffmpeg can't encode {path.suffix}")
    return path


@pytest.mark.parametrize("suffix,args", [(".flac", []), (".mp3", ["-c:a", "libmp3lame"]), (".ogg", ["-c:a", "libvorbis"]), (".m4a", ["-c:a", "aac"])])
def test_write_tags_roundtrip_in_every_format(tmp_path, suffix, args):
    album = tmp_path / "Album"
    files = []
    for n, title in enumerate(["Opener", "Closer"], start=1):
        path = make_audio(album / f"{n:02d}{suffix}", args)
        audio = mutagen.File(path, easy=True)
        if audio.tags is None:
            audio.add_tags()
        audio["title"], audio["tracknumber"], audio["artist"], audio["album"] = title, str(n), "Artist One", "Great Album"
        audio.save()
        files.append(path)

    scanned = tags.scan_directory(album, with_cover=False)
    release = releasetags.parse_release(release_json(["Opener", "Closer"]))
    plan = releasetags.match_tracks(scanned.tracks, release)
    assert releasetags.write_tags(plan) == 2

    for path in files:
        audio = mutagen.File(path, easy=True)
        assert audio["musicbrainz_albumid"] == [RELEASE_ID]
        assert audio["title"][0] in ("Opener", "Closer")  # nothing else was disturbed
    rescanned = tags.scan_directory(album, with_cover=False)
    assert {t.musicbrainz_release_id for t in rescanned.tracks} == {RELEASE_ID}
    if suffix != ".m4a":  # MP4's "easy" interface has no release-group/release-track keys
        first = mutagen.File(files[0], easy=True)
        assert first["musicbrainz_releasegroupid"] == [GROUP_ID]
        assert first["musicbrainz_releasetrackid"] == ["track-0-0"]
        assert first["musicbrainz_albumartistid"] == [ARTIST_ID]


def test_write_tags_on_untagged_mp3_and_read_only_files(tmp_path):
    path = make_audio(tmp_path / "bare.mp3", ["-c:a", "libmp3lame"])
    plan = releasetags.Plan(release=releasetags.parse_release(release_json(["X"])), pairs=[releasetags.Pairing(local("X", "1", name=str(path)), None)])
    plan.pairs[0].track.path = path
    assert releasetags.write_tags(plan) == 1
    assert mutagen.File(path, easy=True)["musicbrainz_albumid"] == [RELEASE_ID]

    path.chmod(0o444)
    try:
        if os.access(path, os.W_OK):
            pytest.skip("running as a user that ignores file permissions")
        with pytest.raises(releasetags.TagWriteError, match="No permission|read-only"):
            releasetags.write_tags(plan)
    finally:
        path.chmod(0o644)


# ---------------------------------------------------------------- web API


@pytest.fixture
async def web(tmp_path, make_flac, monkeypatch, fifo):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    pipe_dir, received = fifo
    library = tmp_path / "library"
    album = library / "Unmanaged" / "Great Album [FLAC]"
    for n, title in enumerate(["Opener", "Closer"], start=1):
        make_flac({"title": title, "artist": "Artist One", "album": "Great Album", "tracknumber": str(n)}, album)
    settings = Settings(app_name="T", app_version="0", contact="t@example.com", api_base_url="https://musicbrainz.org/ws/2",
                        music_root=library, picard_pipe_dir=str(pipe_dir), picard_url="http://picard:8086", picard_library_root="/music")
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, album, received


async def wait_for(received, count=1):
    for _ in range(60):
        if len(b"".join(received).split(b"\0")) > count:
            break
        await __import__("asyncio").sleep(0.05)
    return b"".join(received)


async def test_status_reports_connection(web):
    client, _, _ = web
    status = (await client.get("/api/picard/status")).json()
    assert status == {"configured": True, "connected": True, "url": "http://picard:8086"}


async def test_status_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    app = create_app(Settings("T", "0", "t@example.com", "https://musicbrainz.org/ws/2", music_root=tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/picard/status")).json() == {"configured": False, "connected": False, "url": ""}
        assert (await client.post("/api/picard/save")).status_code == 503


@respx.mock
async def test_plan_previews_without_writing(web):
    client, album, _ = web
    respx.get(f"https://musicbrainz.org/ws/2/release/{RELEASE_ID}").respond(json=release_json(["Opener", "Closer"]))
    plan = (await client.post("/api/picard/plan", json={"path": "Unmanaged/Great Album [FLAC]", "release_mbid": f"https://musicbrainz.org/release/{RELEASE_ID}"})).json()
    assert plan["complete"] is True and [p["match"]["title"] for p in plan["pairs"]] == ["Opener", "Closer"]
    assert all(mutagen.File(f, easy=True).get("musicbrainz_albumid") is None for f in album.glob("*.flac"))


@respx.mock
async def test_send_tags_files_and_tells_picard_to_load(web):
    client, album, received = web
    respx.get(f"https://musicbrainz.org/ws/2/release/{RELEASE_ID}").respond(json=release_json(["Opener", "Closer"]))
    result = (await client.post("/api/picard/send", json={"path": "Unmanaged/Great Album [FLAC]", "release_mbid": RELEASE_ID})).json()
    assert result == {"tagged": 2, "matched": 2, "unmatched_local": [], "loaded": True}
    assert (await wait_for(received)) == b"LOAD /music/Unmanaged/Great Album [FLAC]\0"
    assert {mutagen.File(f, easy=True)["musicbrainz_albumid"][0] for f in album.glob("*.flac")} == {RELEASE_ID}


@respx.mock
async def test_send_changes_nothing_when_picard_is_down(web, monkeypatch):
    client, album, _ = web
    monkeypatch.setattr(picard, "is_connected", lambda *_: False)
    respx.get(f"https://musicbrainz.org/ws/2/release/{RELEASE_ID}").respond(json=release_json(["Opener", "Closer"]))
    response = await client.post("/api/picard/send", json={"path": "Unmanaged/Great Album [FLAC]", "release_mbid": RELEASE_ID})
    assert response.status_code == 503
    assert all(mutagen.File(f, easy=True).get("musicbrainz_albumid") is None for f in album.glob("*.flac"))
    # ...but tag-only still works without Picard.
    tagged = await client.post("/api/picard/send", json={"path": "Unmanaged/Great Album [FLAC]", "release_mbid": RELEASE_ID, "tag_only": True})
    assert tagged.json()["loaded"] is False and tagged.json()["tagged"] == 2


async def test_save_and_clear_send_picard_commands(web):
    client, _, received = web
    assert (await client.post("/api/picard/save")).json() == {"ok": True}
    assert (await wait_for(received)) == b"SAVE_MATCHED\0"
    assert (await client.post("/api/picard/clear")).json() == {"ok": True}
    assert (await wait_for(received, 2)).endswith(b"REMOVE_SAVED\0")


async def test_fingerprint_sends_picard_command(web):
    client, _, received = web
    assert (await client.post("/api/picard/fingerprint")).json() == {"ok": True}
    assert (await wait_for(received)) == b"FINGERPRINT\0"


@pytest.mark.parametrize("path,mbid,status", [("../x", RELEASE_ID, 400), ("Unmanaged", "not-an-id", 422), ("Nope", RELEASE_ID, 404)])
async def test_plan_validates_input(web, path, mbid, status):
    client, _, _ = web
    assert (await client.post("/api/picard/plan", json={"path": path, "release_mbid": mbid})).status_code == status

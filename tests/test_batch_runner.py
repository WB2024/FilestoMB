"""The batch runner end to end, with a fake Picard that behaves like the real one
(loads a folder, moves matched files on SAVE_MATCHED) and a fake MusicBrainz."""

from __future__ import annotations

import asyncio
import os
import select
import shutil
import threading
from pathlib import Path

import mutagen
import pytest

from filestomb.batch import runner, store
from filestomb.batch.runner import BatchManager, cleanup_empty_dirs, locate_moved
from tests.test_batch_core import FakeMB, hit, release

TRACKS = ["Opener", "Closer"]


@pytest.fixture(autouse=True)
def fast_timings(monkeypatch):
    monkeypatch.setattr(runner, "WARMUP_BASE_SECONDS", 0.05)
    monkeypatch.setattr(runner, "WARMUP_PER_TRACK_SECONDS", 0)
    monkeypatch.setattr(runner, "SAVE_TIMEOUT_SECONDS", 1.5)
    monkeypatch.setattr(runner, "SAVE_RESEND_SECONDS", 0.2)
    monkeypatch.setattr(runner, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(runner, "PAUSE_BETWEEN_ALBUMS", 0)


class FakePicard:
    """Listens on a real FIFO and imitates Picard's relevant behaviour."""

    def __init__(self, directory: Path, dest: Path, saves: bool = True):
        self.dest, self.saves = dest, saves
        self.path = directory / "Picard_v2.13.3_main_pipe_file"
        os.mkfifo(self.path)
        self.commands: list[tuple[str, str]] = []
        self.loaded: Path | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                select.select([fd], [], [], 0.05)
                data = os.read(fd, 65536)
            except BlockingIOError:
                data = b""
            finally:
                os.close(fd)
            for message in data.decode().split("\0"):
                if message:
                    command, _, argument = message.partition(" ")
                    self.commands.append((command, argument))
                    self._handle(command, argument)

    def _handle(self, command, argument):
        if command == "LOAD":
            self.loaded = Path(argument)
        elif command == "SAVE_MATCHED" and self.saves and self.loaded and self.loaded.exists():
            for f in sorted(self.loaded.glob("*.flac")):
                audio = mutagen.File(f, easy=True)
                target = self.dest / audio["artist"][0] / audio["album"][0]
                target.mkdir(parents=True, exist_ok=True)
                shutil.move(f, target / f.name)

    def stop(self):
        self._stop.set()

    def names(self):
        return [c[0] for c in self.commands]


def make_album(make_flac, root: Path, rel: str, titles=TRACKS, artist="Artist One", album="Great Album"):
    folder = root / rel
    for n, title in enumerate(titles, start=1):
        make_flac({"title": title, "artist": artist, "album": album, "tracknumber": str(n), "date": "2020"}, folder)
    return folder


@pytest.fixture
def env(tmp_path, make_flac):
    root = tmp_path / "library"
    unmanaged = root / "Unmanaged"
    dest = root / "Clean"
    dest.mkdir(parents=True)
    pipe_dir = tmp_path / "pipe"
    pipe_dir.mkdir()
    fake = FakePicard(pipe_dir, dest)
    # Releases with 0.1s-ish track lengths so durations agree with the silent test files.
    releases = {"r-good": release("r-good", "Great Album", TRACKS, length=100)}
    mb = FakeMB([hit("r-good", 2)], releases)
    batch = store.BatchStore(tmp_path / "batch.db")
    manager = BatchManager(batch, mb, root, tmp_path / "audit.log", picard_pipe_dir=str(pipe_dir),
                           picard_library_root=str(root), dest_root=dest)  # Picard sees the same path we do
    yield type("Env", (), dict(root=root, unmanaged=unmanaged, dest=dest, fake=fake, mb=mb, batch=batch, manager=manager, make_flac=make_flac, releases=releases))
    fake.stop()


async def run(manager, start):
    start()
    while manager.busy:
        await asyncio.sleep(0.02)


async def discover_and_match(e):
    await run(e.manager, lambda: e.manager.start_discovery("Unmanaged"))
    await run(e.manager, lambda: e.manager.start_matching("Unmanaged"))


async def test_discovery_and_matching_triage_albums(env):
    make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    make_album(env.make_flac, env.unmanaged, "N/Nobody/Unknown Thing", titles=["Zzz", "Yyy"], artist="Nobody", album="Unknown Thing")
    env.mb.hits = lambda title: [hit("r-good", 2)] if title == "Great Album" else []
    await discover_and_match(env)
    rows = {r["path"]: r for r in env.batch.list("Unmanaged")}
    assert rows["Unmanaged/G/Artist One/Great Album"]["status"] == store.READY
    assert rows["Unmanaged/G/Artist One/Great Album"]["release_mbid"] == "r-good"
    assert rows["Unmanaged/N/Nobody/Unknown Thing"]["status"] == store.MISSING
    assert env.batch.counts("Unmanaged")["total"] == 2
    # Matching and discovery must never have written anything to the album folders.
    assert env.fake.commands == []
    assert all(mutagen.File(f, easy=True).get("musicbrainz_albumid") is None for f in env.unmanaged.rglob("*.flac"))


async def test_processing_tags_loads_saves_verifies_and_marks_done(env):
    folder = make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    await discover_and_match(env)
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)

    row = env.batch.get("Unmanaged/G/Artist One/Great Album")
    assert row["status"] == store.DONE, row["message"]
    assert env.fake.names()[0] == "REMOVE_ALL"  # Picard is cleared first, before anything is loaded
    assert ("LOAD", str(folder)) in env.fake.commands
    assert "SAVE_MATCHED" in env.fake.names() and env.fake.names()[-1] == "REMOVE_SAVED"
    moved = sorted(env.dest.rglob("*.flac"))
    assert len(moved) == 2 and list(folder.glob("*.flac")) == []
    assert all(mutagen.File(f, easy=True)["musicbrainz_albumid"] == ["r-good"] for f in moved)
    assert env.manager.last_result.startswith("Finished")
    log = "\n".join(env.manager.audit_tail())
    assert '"event": "tagged"' in log and '"event": "album_done"' in log


async def test_only_ready_albums_are_processed_and_limit_is_respected(env):
    make_album(env.make_flac, env.unmanaged, "A/Artist One/Great Album")
    make_album(env.make_flac, env.unmanaged, "B/Artist One/Great Album Two", album="Great Album Two")
    env.mb.hits = lambda title: [hit("r-good", 2)] if title.startswith("Great Album") and "Two" not in title else []
    await discover_and_match(env)
    counts = env.batch.counts("Unmanaged")
    assert counts[store.READY] == 1 and counts[store.MISSING] == 1
    env.manager.start_processing("Unmanaged", limit=1, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    assert env.batch.counts("Unmanaged")[store.DONE] == 1
    assert (env.unmanaged / "B/Artist One/Great Album Two").exists() and len(list((env.unmanaged / "B").rglob("*.flac"))) == 2  # untouched


async def test_a_folder_that_changed_since_matching_is_not_touched(env):
    folder = make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    await discover_and_match(env)
    (folder / "03.flac").write_bytes(b"a new file appeared")  # an extra audio file
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    row = env.batch.get("Unmanaged/G/Artist One/Great Album")
    assert row["status"] == store.PENDING and "Changed since" in row["message"]
    assert "LOAD" not in env.fake.names()
    assert all(mutagen.File(f, easy=True) is None or mutagen.File(f, easy=True).get("musicbrainz_albumid") is None for f in folder.glob("0[12].flac"))


async def test_a_release_that_stops_matching_is_demoted_to_review_without_touching_files(env):
    folder = make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    await discover_and_match(env)
    env.releases["r-good"] = release("r-good", "Great Album", [*TRACKS, "Newly Added Bonus"], length=100)  # edited on MusicBrainz meanwhile
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    row = env.batch.get("Unmanaged/G/Artist One/Great Album")
    assert row["status"] == store.REVIEW and "No longer a confident match" in row["message"]
    assert "LOAD" not in env.fake.names() and len(list(folder.glob("*.flac"))) == 2


async def test_batch_stops_on_the_first_failure_and_never_continues(env):
    env.fake.saves = False  # Picard "doesn't match": the files never leave the folder
    first = make_album(env.make_flac, env.unmanaged, "A/Artist One/Great Album")
    make_album(env.make_flac, env.unmanaged, "B/Artist Two/Great Album", artist="Artist One")
    await discover_and_match(env)
    assert env.batch.counts("Unmanaged")[store.READY] == 2
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    rows = {r["path"]: r for r in env.batch.list("Unmanaged")}
    failed = [r for r in rows.values() if r["status"] == store.PROBLEM]
    ready = [r for r in rows.values() if r["status"] == store.READY]
    assert len(failed) == 1 and "still in the folder" in failed[0]["message"]
    assert len(ready) == 1  # the second album was never attempted
    assert env.manager.last_result.startswith("Stopped") and len(list(first.glob("*.flac"))) == 2  # nothing lost


async def test_destination_check_catches_files_that_went_missing(env):
    class LeakyPicard(FakePicard):
        def _handle(self, command, argument):  # "saves" by moving files somewhere we aren't told about
            if command == "LOAD":
                self.loaded = Path(argument)
            elif command == "SAVE_MATCHED" and self.loaded and self.loaded.exists():
                elsewhere = self.dest.parent / "SomewhereElse"
                elsewhere.mkdir(exist_ok=True)
                for f in self.loaded.glob("*.flac"):
                    shutil.move(f, elsewhere / f.name)

    env.fake.stop()
    pipe_dir = env.manager.picard_pipe_dir
    os.unlink(Path(pipe_dir) / "Picard_v2.13.3_main_pipe_file")
    leaky = LeakyPicard(Path(pipe_dir), env.dest)
    try:
        make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
        await discover_and_match(env)
        env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
        while env.manager.busy:
            await asyncio.sleep(0.02)
        row = env.batch.get("Unmanaged/G/Artist One/Great Album")
        assert row["status"] == store.PROBLEM and "found at the destination" in row["message"]
        assert env.manager.last_result.startswith("Stopped")
    finally:
        leaky.stop()


async def test_refuses_to_start_without_consent_or_picard(env, tmp_path):
    with pytest.raises(RuntimeError, match="Confirm"):
        env.manager.start_processing("Unmanaged", limit=1, clear_picard=False)
    env.fake.stop()
    os.unlink(Path(env.manager.picard_pipe_dir) / "Picard_v2.13.3_main_pipe_file")
    with pytest.raises(RuntimeError, match="reachable"):
        env.manager.start_processing("Unmanaged", limit=1, clear_picard=True)


async def test_stop_between_albums_and_single_job_at_a_time(env):
    make_album(env.make_flac, env.unmanaged, "A/Artist One/Great Album")
    await run(env.manager, lambda: env.manager.start_discovery("Unmanaged"))
    env.manager.start_matching("Unmanaged")
    with pytest.raises(RuntimeError, match="already running"):
        env.manager.start_discovery("Unmanaged")
    env.manager.request_stop()
    while env.manager.busy:
        await asyncio.sleep(0.02)
    assert env.manager.phase == "idle"


async def test_persistent_musicbrainz_failures_abort_matching_but_keep_rows_pending(env):
    import httpx

    class Down(FakeMB):
        async def search_releases_raw(self, *a, **k):
            raise httpx.ConnectError("down")

    for n in range(7):
        make_album(env.make_flac, env.unmanaged, f"A{n}/Artist One/Great Album")
    env.manager.client = Down([], {})
    await run(env.manager, lambda: env.manager.start_discovery("Unmanaged"))
    await run(env.manager, lambda: env.manager.start_matching("Unmanaged"))
    assert env.manager.last_result.startswith("Stopped") and env.batch.counts("Unmanaged")[store.PENDING] == 7


def test_reconcile_marks_processed_folders_done(env):
    folder = make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    env.batch.add_found("Unmanaged", ["Unmanaged/G/Artist One/Great Album", "Unmanaged/G/Artist One/Moved Away"])
    env.batch.update("Unmanaged/G/Artist One/Great Album", status=store.IN_PICARD)
    assert env.manager.reconcile("Unmanaged") == 1  # the folder that no longer exists
    for f in folder.glob("*.flac"):
        f.unlink()
    assert env.manager.reconcile("Unmanaged") == 1
    assert env.batch.counts("Unmanaged")[store.DONE] == 2


def test_cleanup_only_removes_truly_empty_folders(tmp_path):
    root = tmp_path / "U"
    (root / "A" / "Artist" / "EmptyAlbum").mkdir(parents=True)
    (root / "B" / "Artist" / "HasLeftover").mkdir(parents=True)
    (root / "B" / "Artist" / "HasLeftover" / "cover.jpg").write_bytes(b"jpg")
    removed = sorted(p.relative_to(root).as_posix() for p in cleanup_empty_dirs(root))
    assert removed == ["A", "A/Artist", "A/Artist/EmptyAlbum"]
    assert (root / "B" / "Artist" / "HasLeftover" / "cover.jpg").exists() and root.exists()


def test_locate_moved_finds_files_even_when_picard_preserved_their_old_mtime(tmp_path, make_flac):
    import time
    # Picard with "preserve timestamps" leaves old mtimes (files and folders); ctime still moves.
    kept = make_flac({"title": "Kept", "album": "A", "artist": "X", "musicbrainz_albumid": "r1"}, tmp_path / "dest" / "L" / "X" / "A")
    for path in (kept, kept.parent, kept.parent.parent, kept.parent.parent.parent):
        os.utime(path, (1, 1))
    other = make_flac({"title": "Other", "album": "B", "artist": "Y", "musicbrainz_albumid": "r2"}, tmp_path / "dest" / "L" / "Y" / "B")
    assert locate_moved(tmp_path / "dest", time.time() - 60, "r1") == [kept]
    assert other not in locate_moved(tmp_path / "dest", time.time() - 60, "r1")
    # Anything whose inode hasn't changed since the cut-off is not "just saved".
    assert locate_moved(tmp_path / "dest", time.time() + 3600, "r1") == []


async def test_an_approved_release_with_a_different_name_is_processed_but_an_unapproved_one_is_not(env):
    folder = make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    env.releases["r-good"] = release("r-good", "A Completely Different Title", TRACKS, length=100)
    env.mb.groups, env.mb.group_releases = [{"id": "g", "score": 100}], {"g": [env.releases["r-good"]]}
    await discover_and_match(env)
    path = "Unmanaged/G/Artist One/Great Album"
    assert env.batch.get(path)["status"] == store.REVIEW  # exact tracks, different title: a human decides

    # Forced to READY without approval (e.g. a stale database), it is still refused at processing time.
    env.batch.update(path, status=store.READY, release_mbid="r-good")
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    assert env.batch.get(path)["status"] == store.REVIEW and "LOAD" not in env.fake.names()

    # The user's explicit approval lets the same album through.
    env.batch.update(path, status=store.READY, verdict={"approved": "r-good"})
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    assert env.batch.get(path)["status"] == store.DONE and len(list(env.dest.rglob("*.flac"))) == 2


async def test_after_saved_hook_gets_destination_and_note_is_recorded(env):
    calls = []

    async def hook(folder, mbid):
        calls.append((folder, mbid))
        return "Imported"

    env.manager.after_saved = hook
    make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    await discover_and_match(env)
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    row = env.batch.get("Unmanaged/G/Artist One/Great Album")
    assert row["status"] == store.DONE and row["message"].endswith("Lidarr: Imported")
    assert calls == [(env.dest / "Artist One" / "Great Album", "r-good")]


async def test_a_failing_hook_stops_the_batch_but_the_album_stays_done(env):
    async def hook(folder, mbid):
        raise RuntimeError("Lidarr said no")

    env.manager.after_saved = hook
    make_album(env.make_flac, env.unmanaged, "A/Artist One/Great Album")
    make_album(env.make_flac, env.unmanaged, "B/Artist Two/Great Album", artist="Artist One")
    await discover_and_match(env)
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    counts = env.batch.counts("Unmanaged")
    assert counts[store.DONE] == 1 and counts[store.READY] == 1  # the second one never started
    done = [r for r in env.batch.list("Unmanaged") if r["status"] == store.DONE][0]
    assert "Lidarr: Lidarr said no" in done["message"]
    assert "lidarr_failed" in "\n".join(env.manager.audit_tail())


async def test_before_import_hook_holds_an_album_back_without_touching_it_and_the_batch_continues(env):
    async def guard(directory, mbid):
        return "Already in your library at X/Y" if "Great Album" in directory.name else None

    env.manager.before_import = guard
    make_album(env.make_flac, env.unmanaged, "G/Artist One/Great Album")
    await discover_and_match(env)
    before = sorted(p.name for p in (env.unmanaged / "G/Artist One/Great Album").iterdir())
    env.manager.start_processing("Unmanaged", limit=5, clear_picard=True)
    while env.manager.busy:
        await asyncio.sleep(0.02)
    row = env.batch.get("Unmanaged/G/Artist One/Great Album")
    assert row["status"] == store.PROBLEM and "Already in your library" in row["message"]
    assert sorted(p.name for p in (env.unmanaged / "G/Artist One/Great Album").iterdir()) == before
    assert all(mutagen.File(f, easy=True).get("musicbrainz_albumid") is None for f in (env.unmanaged / "G/Artist One/Great Album").glob("*.flac"))

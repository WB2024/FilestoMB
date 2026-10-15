"""Archive extraction: the one place FilesToMB writes into the music library."""

from __future__ import annotations

import io
import os
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from filestomb import archives
from filestomb.archives import ExtractError, extract_archive

needs_7z = pytest.mark.skipif(archives.find_sevenzip() is None, reason="7-Zip is not installed")


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


def tree(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "name,expected",
    [("a.zip", True), ("A.RAR", True), ("a.7z", True), ("a.tar.gz", True), ("a.tgz", True), ("a.mp3", False),
     ("a.part1.rar", True), ("a.part01.rar", True), ("a.part2.rar", False), ("a.part10.rar", False), ("zip", False)],
)
def test_is_archive(name, expected):
    assert archives.is_archive(name) is expected


@pytest.mark.parametrize("name,stem", [("Album.zip", "Album"), ("Album.part1.rar", "Album"), ("x.tar.gz", "x"), ("..zip", "extracted")])
def test_archive_stem(name, stem):
    assert archives.archive_stem(name) == stem


@needs_7z
def test_single_top_level_folder_is_not_double_nested(tmp_path):
    z = make_zip(tmp_path / "Download.zip", {"Great Album/01.flac": b"a", "Great Album/cover.jpg": b"b"})
    result = extract_archive(z)
    assert result.directory == tmp_path / "Great Album" and result.files == 2
    assert tree(result.directory) == ["01.flac", "cover.jpg"]
    assert z.exists()  # the archive itself is left alone
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".filestomb")] == []


@needs_7z
def test_loose_files_go_in_a_folder_named_after_the_archive(tmp_path):
    z = make_zip(tmp_path / "Some Album.zip", {"01.flac": b"a", "02.flac": b"b"})
    result = extract_archive(z)
    assert result.directory == tmp_path / "Some Album"
    assert tree(result.directory) == ["01.flac", "02.flac"]
    assert not (tmp_path / "01.flac").exists()  # nothing spilled into the parent


@needs_7z
def test_never_overwrites_existing_folders(tmp_path):
    (tmp_path / "Some Album").mkdir()
    (tmp_path / "Some Album" / "keep.txt").write_text("mine")
    z = make_zip(tmp_path / "Some Album.zip", {"01.flac": b"a"})
    first = extract_archive(z)
    second = extract_archive(z)
    assert first.directory.name == "Some Album (2)" and second.directory.name == "Some Album (3)"
    assert (tmp_path / "Some Album" / "keep.txt").read_text() == "mine"


@needs_7z
def test_zip_slip_cannot_escape(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    z = make_zip(library / "evil.zip", {"../escaped.txt": b"x", "ok/01.flac": b"a"})
    try:
        extract_archive(z)
    except ExtractError:
        pass
    assert not (tmp_path / "escaped.txt").exists()
    assert not (library / "escaped.txt").exists()
    assert [p.name for p in library.iterdir() if p.name.startswith(".filestomb")] == []


@needs_7z
def test_symlinks_in_archives_are_removed(tmp_path):
    z = tmp_path / "links.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Album/01.flac", b"a")
        info = zipfile.ZipInfo("Album/passwd")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    result = extract_archive(z)
    assert tree(result.directory) == ["01.flac"]
    assert not any(p.is_symlink() for p in result.directory.rglob("*"))


@needs_7z
def test_macos_junk_is_dropped_and_permissions_are_normal(tmp_path):
    z = make_zip(tmp_path / "Mac.zip", {"Album/01.flac": b"a", "__MACOSX/Album/._01.flac": b"j", "Album/.DS_Store": b"j"})
    result = extract_archive(z)
    assert tree(result.directory) == ["01.flac"]
    assert not (tmp_path / "__MACOSX").exists()
    assert os.stat(result.directory).st_mode & 0o755 == 0o755


@needs_7z
def test_empty_and_corrupt_archives_fail_cleanly(tmp_path):
    empty = tmp_path / "empty.zip"
    zipfile.ZipFile(empty, "w").close()
    with pytest.raises(ExtractError):
        extract_archive(empty)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip file at all")
    with pytest.raises(ExtractError, match="valid archive|damaged|failed"):
        extract_archive(bad)
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".filestomb")] == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.zip", "empty.zip"]


def test_tar_gz_is_extracted_without_7zip(tmp_path):
    t = tmp_path / "Album.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        for name in ("Album/01.flac", "Album/02.flac"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tf.addfile(info, io.BytesIO(b"a"))
        evil = tarfile.TarInfo("../outside.txt")
        evil.size = 1
        tf.addfile(evil, io.BytesIO(b"x"))
    with pytest.raises(ExtractError):  # the "data" filter refuses path escapes
        extract_archive(t)
    assert not (tmp_path.parent / "outside.txt").exists()

    good = tmp_path / "Good.tgz"
    with tarfile.open(good, "w:gz") as tf:
        info = tarfile.TarInfo("Good/01.flac")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"a"))
    assert tree(extract_archive(good).directory) == ["01.flac"]


def test_refuses_read_only_folders_and_non_archives(tmp_path):
    (tmp_path / "song.mp3").write_bytes(b"x")
    with pytest.raises(ExtractError, match="supported"):
        extract_archive(tmp_path / "song.mp3")
    with pytest.raises(ExtractError, match="no longer exists"):
        extract_archive(tmp_path / "missing.zip")
    locked = tmp_path / "locked"
    locked.mkdir()
    z = make_zip(locked / "a.zip", {"01.flac": b"a"})
    locked.chmod(0o555)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("running as a user that ignores directory permissions")
        with pytest.raises(ExtractError, match="read-only"):
            extract_archive(z)
    finally:
        locked.chmod(0o755)


@needs_7z
def test_space_check_blocks_oversized_archives(tmp_path, monkeypatch):
    z = make_zip(tmp_path / "Big.zip", {"01.flac": b"a" * 5000})
    monkeypatch.setattr(archives, "MAX_UNCOMPRESSED_BYTES", 1000)
    with pytest.raises(ExtractError, match="safety limit"):
        extract_archive(z)
    monkeypatch.setattr(archives, "MAX_UNCOMPRESSED_BYTES", 10**12)
    monkeypatch.setattr(archives.shutil, "disk_usage", lambda _: type("U", (), {"free": 100})())
    with pytest.raises(ExtractError, match="Not enough disk space"):
        extract_archive(z)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Big.zip"]


def test_rar_prefers_bsdtar_and_zip_uses_7zip(tmp_path, monkeypatch):
    """RAR must go through bsdtar (Debian's 7-Zip can't decompress it); zip stays on 7-Zip."""
    calls = []

    class Done:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0].endswith("bsdtar") or cmd[1] == "x":
            dest = Path(cmd[cmd.index("-C") + 1] if "-C" in cmd else next(a[2:] for a in cmd if a.startswith("-o")))
            (dest / "Album").mkdir()
            (dest / "Album" / "01.flac").write_bytes(b"a")
        return Done()

    monkeypatch.setattr(archives.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("bsdtar", "7z") else None)
    monkeypatch.setattr(archives.subprocess, "run", fake_run)

    rar = tmp_path / "Release.rar"
    rar.write_bytes(b"Rar!")
    assert extract_archive(rar).directory == tmp_path / "Album"
    assert any(c[0] == "/usr/bin/bsdtar" and c[1] == "-xf" for c in calls)
    assert not any(c[0] == "/usr/bin/7z" and c[1] == "x" for c in calls)

    calls.clear()
    zipped = tmp_path / "Other.zip"
    zipped.write_bytes(b"PK")
    extract_archive(zipped)
    assert any(c[0] == "/usr/bin/7z" and c[1] == "x" for c in calls)
    assert not any(c[0] == "/usr/bin/bsdtar" for c in calls)


def test_rar_error_messages_are_friendly(tmp_path, monkeypatch):
    class Failed:
        returncode = 1
        stdout = ""
        stderr = "bsdtar: Passphrase required for this entry"

    monkeypatch.setattr(archives.shutil, "which", lambda name: "/usr/bin/bsdtar" if name == "bsdtar" else None)
    monkeypatch.setattr(archives.subprocess, "run", lambda *a, **k: Failed())
    rar = tmp_path / "Locked.rar"
    rar.write_bytes(b"Rar!")
    with pytest.raises(ExtractError, match="password protected"):
        extract_archive(rar)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Locked.rar"]

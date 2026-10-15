"""Safe extraction of downloaded album archives (zip, rar, 7z, tar family).

This is the one place FilesToMB writes into the music library, so it is
deliberately defensive:

* Everything is extracted into a hidden temporary folder beside the archive
  and only moved into place once it has been checked, so a failed or
  hostile archive never leaves half-extracted files among the music.
* Symlinks inside archives are removed and every path is verified to stay
  inside the temporary folder (zip-slip).
* Nothing is ever overwritten: a name clash gets " (2)", " (3)", ...
* Uncompressed size is checked against free disk space before extracting.

The result lands in the same directory as the archive. If the archive holds
a single top-level folder, that folder is used as-is; otherwise a folder named
after the archive is created, so loose files never spill into the parent.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

TAR_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".tar")
SEVENZIP_SUFFIXES = (".zip", ".rar", ".7z")
ARCHIVE_SUFFIXES = SEVENZIP_SUFFIXES + TAR_SUFFIXES

# Never extract more than this, however much disk is free.
MAX_UNCOMPRESSED_BYTES = 60 * 1024**3
# Always leave this much free after extracting.
FREE_SPACE_MARGIN = 1024**3
EXTRACT_TIMEOUT_SECONDS = 3600

_PART_RE = re.compile(r"\.part0*(\d+)$", re.IGNORECASE)
_JUNK_NAMES = {"__MACOSX", ".DS_Store", "Thumbs.db", "desktop.ini"}


class ExtractError(Exception):
    """An archive couldn't be extracted; the message is safe to show to the user."""


@dataclass
class Extracted:
    directory: Path
    files: int


def _suffix_of(name: str) -> str | None:
    lower = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lower.endswith(suffix):
            return suffix
    return None


def is_archive(name: str) -> bool:
    """True for archives we can extract. Later volumes of a split RAR
    (name.part2.rar) are excluded: extracting part 1 reads the whole set."""
    suffix = _suffix_of(name)
    if suffix is None:
        return False
    if suffix == ".rar":
        part = _PART_RE.search(name[: -len(suffix)])
        if part and int(part.group(1)) > 1:
            return False
    return True


def archive_stem(name: str) -> str:
    suffix = _suffix_of(name)
    stem = name[: -len(suffix)] if suffix else name
    if suffix == ".rar":
        stem = _PART_RE.sub("", stem)
    return stem.strip().strip(".") or "extracted"


def find_sevenzip() -> str | None:
    for candidate in ("7zz", "7z", "7za"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def find_bsdtar() -> str | None:
    return shutil.which("bsdtar")


def _clean_folder_name(name: str) -> str:
    name = re.sub(r"[\x00-\x1f/\\]", "_", name).strip().strip(".")
    return name or "extracted"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.name} ({n})")
        if not candidate.exists():
            return candidate
    raise ExtractError("Too many folders with that name already exist.")


def _uncompressed_size(sevenzip: str, archive: Path) -> int | None:
    """Total uncompressed bytes according to the archive's own listing."""
    try:
        result = subprocess.run(
            [sevenzip, "l", "-slt", "-ba", "-p-", str(archive)],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    sizes = re.findall(r"^Size = (\d+)$", result.stdout, flags=re.MULTILINE)
    return sum(int(s) for s in sizes) if sizes else None


def _check_space(needed: int | None, parent: Path) -> None:
    if needed is None:
        return
    if needed > MAX_UNCOMPRESSED_BYTES:
        raise ExtractError(f"Archive expands to {needed / 1024**3:.0f} GB, which is over the safety limit.")
    free = shutil.disk_usage(parent).free
    if needed + FREE_SPACE_MARGIN > free:
        raise ExtractError(
            f"Not enough disk space: needs {needed / 1024**3:.1f} GB, only {free / 1024**3:.1f} GB free."
        )


def _extract_tar(archive: Path, destination: Path) -> None:
    if not hasattr(tarfile, "data_filter"):
        raise ExtractError("This Python is too old to safely extract tar archives.")
    try:
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            _check_space(sum(m.size for m in members if m.isfile()), archive.parent)
            tar.extractall(destination, members=members, filter="data")
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ExtractError(f"Couldn't read that archive: {error}") from error


def _extract_sevenzip(archive: Path, destination: Path) -> None:
    sevenzip = find_sevenzip()
    if sevenzip is None:
        raise ExtractError("No 7-Zip binary is installed on the server, so this archive type can't be extracted.")
    _check_space(_uncompressed_size(sevenzip, archive), archive.parent)
    try:
        result = subprocess.run(
            [sevenzip, "x", "-y", "-bd", "-bso0", "-bsp0", "-p-", f"-o{destination}", str(archive)],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=EXTRACT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ExtractError("Extraction took too long and was stopped.") from error
    except OSError as error:
        raise ExtractError(f"Couldn't run 7-Zip: {error}") from error
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").lower()
        if "wrong password" in output or "encrypted" in output or "password" in output:
            raise ExtractError("That archive is password protected.")
        if "no space left" in output:
            raise ExtractError("Ran out of disk space while extracting.")
        if "cannot open" in output or "can not open" in output or "is not archive" in output:
            raise ExtractError("That file isn't a valid archive, or it's damaged.")
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise ExtractError(f"Extraction failed: {detail[-1] if detail else f'exit code {result.returncode}'}")


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _extract_rar(archive: Path, destination: Path) -> None:
    """RAR goes through libarchive's bsdtar when available: Debian's 7-Zip
    build can't decompress most RARs (that code is licence-restricted)."""
    bsdtar = find_bsdtar()
    if bsdtar is None:
        _extract_sevenzip(archive, destination)
        return
    sevenzip = find_sevenzip()
    if sevenzip is not None:
        _check_space(_uncompressed_size(sevenzip, archive), archive.parent)
    try:
        result = subprocess.run(
            [bsdtar, "-xf", str(archive), "-C", str(destination)],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=EXTRACT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ExtractError("Extraction took too long and was stopped.") from error
    except OSError as error:
        raise ExtractError(f"Couldn't run bsdtar: {error}") from error
    if result.returncode != 0:
        output = (result.stderr or "").lower()
        if "passphrase" in output or "encrypted" in output or "password" in output:
            raise ExtractError("That archive is password protected.")
        if "no space left" in output:
            raise ExtractError("Ran out of disk space while extracting.")
        if "unrecognized archive format" in output or "truncated" in output or "malformed" in output:
            raise ExtractError("That file isn't a valid archive, or it's damaged.")
        detail = (result.stderr or "").strip().splitlines()
        raise ExtractError(f"Extraction failed: {detail[-1] if detail else f'exit code {result.returncode}'}")


def _sanitize_tree(root: Path) -> int:
    """Drop symlinks and junk, check nothing escaped, fix permissions.
    Returns the number of regular files."""
    real_root = root.resolve()
    files = 0
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        for name in [*dirs, *names]:
            path = Path(current) / name
            if name in _JUNK_NAMES or path.is_symlink():
                _remove(path)
                dirs[:] = [d for d in dirs if d != name]
                names[:] = [n for n in names if n != name]
                continue
            if not path.resolve().is_relative_to(real_root):
                raise ExtractError("The archive tried to write outside its own folder, so it was rejected.")
            os.chmod(path, path.stat().st_mode | (0o755 if path.is_dir() else 0o644))
            if path.is_file():
                files += 1
    return files


def extract_archive(archive: Path) -> Extracted:
    """Extract `archive` next to itself and return the new folder."""
    archive = Path(archive)
    if not archive.is_file():
        raise ExtractError("That archive no longer exists.")
    if not is_archive(archive.name):
        raise ExtractError("That isn't a supported archive type.")
    parent = archive.parent
    if not os.access(parent, os.W_OK | os.X_OK):
        raise ExtractError("This folder is read-only, so nothing can be extracted into it.")

    workdir = Path(tempfile.mkdtemp(prefix=".filestomb-extract-", dir=parent))
    try:
        suffix = _suffix_of(archive.name)
        if suffix in TAR_SUFFIXES:
            _extract_tar(archive, workdir)
        elif suffix == ".rar":
            _extract_rar(archive, workdir)
        else:
            _extract_sevenzip(archive, workdir)

        files = _sanitize_tree(workdir)
        if files == 0:
            raise ExtractError("The archive was empty (or held only links).")

        entries = list(workdir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            source, name = entries[0], _clean_folder_name(entries[0].name)
        else:
            source, name = workdir, _clean_folder_name(archive_stem(archive.name))
        destination = _unique_path(parent / name)
        source.rename(destination)
        # mkdtemp creates the work folder private (0700); make the result normal.
        os.chmod(destination, destination.stat().st_mode | 0o755)
        return Extracted(directory=destination, files=files)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

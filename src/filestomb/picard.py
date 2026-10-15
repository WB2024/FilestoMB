"""Drive a running MusicBrainz Picard through its remote-command pipe.

Picard (>= 2.9) listens on a named pipe (a FIFO called
``Picard_v<version>_main_pipe_file``, in its XDG runtime directory) for the
same commands ``picard -e COMMAND ...`` accepts. This works across Docker
containers by sharing that directory as a volume; see compose.yaml.

Wire format, from Picard's own source (picard/util/pipe.py, tagger.py): a
message is ``COMMAND<space>argument`` followed by a NUL byte. Everything after
the first space is one argument, so paths with spaces need no quoting.
"""

from __future__ import annotations

import errno
import os
import stat
import time
from pathlib import Path, PurePosixPath

PIPE_GLOB = "Picard_v*_main_pipe_file"
# Picard re-opens the FIFO between messages, so a writer can briefly find no
# reader (ENXIO). Retrying for a moment makes that gap invisible.
SEND_TIMEOUT_SECONDS = 3.0


class PicardUnavailable(Exception):
    """Picard can't be reached; the message is safe to show to the user."""


def find_pipe(pipe_dir: str | Path | None) -> Path | None:
    if not pipe_dir:
        return None
    directory = Path(pipe_dir)
    try:
        candidates = sorted(directory.glob(PIPE_GLOB))
    except OSError:
        return None
    for path in reversed(candidates):  # newest version name last
        try:
            if stat.S_ISFIFO(path.stat().st_mode):
                return path
        except OSError:
            continue
    return None


def _open_for_write(path: Path, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as error:
            if error.errno == errno.ENXIO and time.monotonic() < deadline:
                time.sleep(0.05)
                continue
            if error.errno == errno.ENXIO:
                raise PicardUnavailable("Picard isn't listening. Is it running?") from error
            if error.errno in (errno.EACCES, errno.EPERM):
                raise PicardUnavailable("No permission to talk to Picard's pipe.") from error
            raise PicardUnavailable(f"Couldn't reach Picard: {error.strerror}") from error


def is_connected(pipe_dir: str | Path | None) -> bool:
    """True if a Picard is currently listening. Probes without sending a command."""
    path = find_pipe(pipe_dir)
    if path is None:
        return False
    try:
        os.close(_open_for_write(path, timeout=1.0))
    except PicardUnavailable:
        return False
    return True


def send(pipe_dir: str | Path | None, *commands: tuple[str, str]) -> None:
    """Send commands, e.g. ``send(d, ("LOAD", "/music/Album"), ("SAVE_MATCHED", ""))``."""
    path = find_pipe(pipe_dir)
    if path is None:
        raise PicardUnavailable("Picard's pipe wasn't found. Is the shared folder mounted and Picard running?")
    payload = "".join(f"{command} {argument}".rstrip() + "\0" for command, argument in commands).encode()
    if len(payload) > 4000:  # keep each write atomic (PIPE_BUF)
        raise PicardUnavailable("That command is too long to send to Picard.")
    fd = _open_for_write(path, SEND_TIMEOUT_SECONDS)
    try:
        os.write(fd, payload)
    except BrokenPipeError as error:
        raise PicardUnavailable("Picard stopped listening mid-message.") from error
    finally:
        os.close(fd)


def to_picard_path(local: Path, library_root: Path, picard_library_root: str = "/music") -> str:
    """Translate a path under our library mount to the same file as Picard sees it."""
    relative = Path(local).resolve().relative_to(Path(library_root).resolve())
    return str(PurePosixPath(picard_library_root) / PurePosixPath(*relative.parts))

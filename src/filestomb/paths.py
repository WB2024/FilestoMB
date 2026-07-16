"""Shared local-data-directory helper (OAuth tokens, remembered state)."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "") or (Path.home() / ".config"))
    directory = base / "filestomb"
    directory.mkdir(parents=True, exist_ok=True)
    return directory

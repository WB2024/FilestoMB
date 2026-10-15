"""Small local state persisted between runs: just the last browsed directory,
so the app doesn't default back to your home directory every launch when
your music actually lives somewhere else (e.g. /srv/music)."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import config_dir


def _state_path() -> Path:
    return config_dir() / "state.json"


def load_last_directory() -> Path | None:
    path = _state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        directory = Path(data["last_directory"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return directory if directory.is_dir() else None


def save_last_directory(directory: Path) -> None:
    _state_path().write_text(json.dumps({"last_directory": str(directory)}))


def _favourites_path() -> Path:
    return config_dir() / "favourites.json"


def load_favourites() -> list[str]:
    """Favourite folders, as library-relative paths, in the order they were added."""
    try:
        data = json.loads(_favourites_path().read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str) and item]


def save_favourites(paths: list[str]) -> None:
    _favourites_path().write_text(json.dumps(paths, indent=2))

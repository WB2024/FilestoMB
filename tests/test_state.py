from __future__ import annotations

from pathlib import Path

from filestomb import state


def test_load_last_directory_returns_none_when_unset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert state.load_last_directory() is None


def test_save_and_load_last_directory_round_trips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    target = tmp_path / "music"
    target.mkdir()

    state.save_last_directory(target)

    assert state.load_last_directory() == target


def test_load_last_directory_ignores_deleted_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    target = tmp_path / "gone"
    target.mkdir()
    state.save_last_directory(target)
    target.rmdir()

    assert state.load_last_directory() is None

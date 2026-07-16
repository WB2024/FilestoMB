"""The starting screen: browse to an album folder and scan its tags."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DirectoryTree, Footer, Header, Input, Static

from .. import state, tags
from ..widgets.login_status import LoginStatus


class AlbumDirectoryTree(DirectoryTree):
    def filter_paths(self, paths):
        return [path for path in paths if path.is_dir()]


class BrowseScreen(Screen):
    BINDINGS = [
        ("g", "focus_path_input", "Go to path"),
        ("u", "go_up", "Up a directory"),
    ]

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield LoginStatus()
        yield Vertical(
            Static(
                "Navigate to an album folder and press [b]Enter[/b] to scan it. "
                "Press [b]g[/b] to jump to a specific path, [b]u[/b] to go up a directory.",
                id="browse-hint",
            ),
            Horizontal(
                Input(placeholder="Jump to path...", id="path-input"),
                Button("Up", id="up-button"),
                id="path-row",
            ),
            Static(str(self._start_path), id="current-path"),
            AlbumDirectoryTree(str(self._start_path), id="tree"),
        )
        yield Footer()

    def _set_root(self, path: Path) -> None:
        tree = self.query_one(AlbumDirectoryTree)
        tree.path = path
        self.query_one("#current-path", Static).update(str(path))
        tree.focus()

    def action_focus_path_input(self) -> None:
        self.query_one("#path-input", Input).focus()

    def action_go_up(self) -> None:
        tree = self.query_one(AlbumDirectoryTree)
        parent = Path(tree.path).parent
        if parent != Path(tree.path):
            self._set_root(parent)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "up-button":
            self.action_go_up()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        candidate = Path(event.value).expanduser()
        if not candidate.is_dir():
            self.notify(f"Not a directory: {candidate}", severity="error")
            return
        self._set_root(candidate)

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._scan(event.path)

    @work(exclusive=True)
    async def _scan(self, directory: Path) -> None:
        album = tags.scan_directory(directory)
        if album is None:
            self.notify(f"No audio files found in {directory}", severity="warning")
            return

        state.save_last_directory(self.query_one(AlbumDirectoryTree).path)

        from .review import ReviewScreen

        self.app.push_screen(ReviewScreen(album))

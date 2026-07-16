"""The starting screen: browse to an album folder and scan its tags."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DirectoryTree, Footer, Header, Input, Static

from .. import tags


class AlbumDirectoryTree(DirectoryTree):
    def filter_paths(self, paths):
        return [path for path in paths if path.is_dir()]


class BrowseScreen(Screen):
    BINDINGS = [("g", "focus_path_input", "Go to path")]

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static(
                "Navigate to an album folder and press [b]Enter[/b] to scan it. "
                "Press [b]g[/b] to jump to a specific path.",
                id="browse-hint",
            ),
            Input(placeholder="Jump to path...", id="path-input"),
            AlbumDirectoryTree(str(self._start_path), id="tree"),
        )
        yield Footer()

    def action_focus_path_input(self) -> None:
        self.query_one("#path-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        candidate = Path(event.value).expanduser()
        if not candidate.is_dir():
            self.notify(f"Not a directory: {candidate}", severity="error")
            return
        self.query_one(AlbumDirectoryTree).path = candidate
        self.query_one(AlbumDirectoryTree).focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._scan(event.path)

    @work(exclusive=True)
    async def _scan(self, directory: Path) -> None:
        album = tags.scan_directory(directory)
        if album is None:
            self.notify(f"No audio files found in {directory}", severity="warning")
            return

        from .review import ReviewScreen

        self.app.push_screen(ReviewScreen(album))

"""The FilesToMB Textual application."""

from __future__ import annotations

import sys
from pathlib import Path

from textual.app import App

from .config import Settings, load_settings
from .mb.client import MusicBrainzClient
from .screens.browse import BrowseScreen


class FilesToMBApp(App):
    CSS_PATH = "app.css"
    TITLE = "FilesToMB"
    SUB_TITLE = "Turn local albums into MusicBrainz edits"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.settings: Settings = load_settings()
        self.mb_client = MusicBrainzClient(
            user_agent=self.settings.user_agent,
            base_url=self.settings.api_base_url,
        )
        self._start_path = start_path or Path.home()

    def on_mount(self) -> None:
        if not self.settings.has_contact:
            self.notify(
                "Set MB_CONTACT in your .env so MusicBrainz can identify this client "
                "(see .env.example).",
                severity="warning",
                timeout=8,
            )
        self.push_screen(BrowseScreen(self._start_path))

    async def on_unmount(self) -> None:
        await self.mb_client.aclose()


def run() -> None:
    start_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home()
    FilesToMBApp(start_path).run()


if __name__ == "__main__":
    run()

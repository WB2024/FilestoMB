"""The FilesToMB Textual application."""

from __future__ import annotations

import argparse
from importlib.metadata import version
from pathlib import Path

from textual.app import App

from .config import Settings, load_settings
from .mb.client import MusicBrainzClient
from .mb.oauth import MusicBrainzOAuth
from .screens.browse import BrowseScreen


class FilesToMBApp(App):
    CSS_PATH = "app.css"
    TITLE = "FilesToMB"
    SUB_TITLE = "Turn local albums into MusicBrainz edits"
    BINDINGS = [("q", "quit", "Quit"), ("l", "login", "Log in to MusicBrainz")]

    def __init__(self, start_path: Path | None = None) -> None:
        super().__init__()
        self.settings: Settings = load_settings()
        self.mb_client = MusicBrainzClient(
            user_agent=self.settings.user_agent,
            base_url=self.settings.api_base_url,
        )
        self.oauth = MusicBrainzOAuth(
            client_id=self.settings.oauth_client_id,
            client_secret=self.settings.oauth_client_secret,
        )
        self.oauth_username: str = ""
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

    def action_login(self) -> None:
        if not self.settings.has_oauth:
            self.notify(
                "Set MB_OAUTH_CLIENT_ID and MB_OAUTH_CLIENT_SECRET in .env to log in "
                "(see .env.example).",
                severity="warning",
            )
            return
        from .screens.login import LoginScreen

        self.push_screen(LoginScreen())

    async def on_unmount(self) -> None:
        await self.mb_client.aclose()
        await self.oauth.aclose()


def run() -> None:
    parser = argparse.ArgumentParser(
        prog="filestomb",
        description="A keyboard-driven TUI for turning local albums into MusicBrainz edits.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path.home()),
        help="directory to start browsing from (default: your home directory)",
    )
    parser.add_argument("--version", action="version", version=f"filestomb {version('filestomb')}")
    args = parser.parse_args()

    start_path = Path(args.path).expanduser()
    if not start_path.is_dir():
        parser.error(f"not a directory: {start_path}")

    FilesToMBApp(start_path).run()


if __name__ == "__main__":
    run()

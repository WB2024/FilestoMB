"""MusicBrainz OAuth2 login: open the authorize page, paste the code back."""

from __future__ import annotations

import secrets
import webbrowser

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from ..mb.oauth import build_authorize_url


class LoginScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
        ("o", "open_auth", "Open authorization page"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._state = secrets.token_urlsafe(16)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="login-body"):
            yield Static(
                "1. Press [b]o[/b] (or the button) to open MusicBrainz and authorize FilesToMB.\n"
                "2. Log in and approve access, then copy the code MusicBrainz shows you.\n"
                "3. Paste it below and press Enter.",
                id="login-hint",
            )
            yield Button("Open MusicBrainz authorization page [o]", id="open-auth-button")
            yield Input(placeholder="Paste the authorization code here", id="auth-code-input")
        yield Footer()

    def action_open_auth(self) -> None:
        client_id = self.app.settings.oauth_client_id
        if not client_id:
            self.notify(
                "Set MB_OAUTH_CLIENT_ID and MB_OAUTH_CLIENT_SECRET in .env first.",
                severity="error",
            )
            return
        webbrowser.open(build_authorize_url(client_id, state=self._state))
        self.query_one("#auth-code-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-auth-button":
            self.action_open_auth()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        code = event.value.strip()
        if code:
            self._exchange(code)

    @work(exclusive=True)
    async def _exchange(self, code: str) -> None:
        try:
            await self.app.oauth.exchange_code(code)
            username = await self.app.oauth.fetch_username()
        except Exception as error:
            self.notify(f"Login failed: {error}", severity="error")
            return

        self.app.oauth_username = username
        self.notify(f"Logged in to MusicBrainz as {username}." if username else "Logged in to MusicBrainz.")
        self.app.pop_screen()

"""A small always-visible indicator of MusicBrainz login status, so it
doesn't rely on the user noticing the "l" key in the footer."""

from __future__ import annotations

from textual.widgets import Static


class LoginStatus(Static):
    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(1.0, self._refresh)

    def _refresh(self) -> None:
        app = self.app
        if app.oauth.is_logged_in:
            name = app.oauth_username or "MusicBrainz"
            self.update(f"[green]●[/green] Logged in to MusicBrainz as {name}")
        elif app.settings.has_oauth:
            self.update("[red]●[/red] Not logged in to MusicBrainz -- press [b]l[/b] to log in")
        else:
            self.update(
                "[dim]●[/dim] MusicBrainz login not configured "
                "(set MB_OAUTH_CLIENT_ID/MB_OAUTH_CLIENT_SECRET in .env)"
            )

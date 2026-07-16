"""Collects the release fields MusicBrainz can seed beyond name, artist,
date, label, catalog number, and barcode (those are already editable on the
review screen): status, language, script, country, packaging, annotation,
disambiguation, external links, and an edit note.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, TextArea

from ..mb.seed import RELEASE_PACKAGINGS, RELEASE_STATUSES


class ReleaseDetailsScreen(Screen[dict]):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "continue", "Continue"),
    ]

    def __init__(self, title: str, artist: str) -> None:
        super().__init__()
        self._title = title
        self._artist = artist

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="details-body"):
            yield Static(f"Creating release [b]{self._title}[/b] by {self._artist}")

            yield Label("Status")
            yield Select([(name, name) for name in RELEASE_STATUSES], id="status", allow_blank=True)

            yield Label("Language (ISO 639-3 code, e.g. eng)")
            yield Input(placeholder="eng", id="language")

            yield Label("Script (ISO 15924 code, e.g. Latn)")
            yield Input(placeholder="Latn", id="script")

            yield Label("Country (ISO 3166-1 code, e.g. GB)")
            yield Input(placeholder="GB", id="country")

            yield Label("Packaging")
            yield Select([(name, name) for name in RELEASE_PACKAGINGS], id="packaging", allow_blank=True)

            yield Label("Disambiguation")
            yield Input(placeholder="e.g. Japanese edition", id="disambiguation")

            yield Label("Annotation")
            yield TextArea(id="annotation")

            yield Label("External links (one URL per line)")
            yield TextArea(id="external-links")

            yield Label("Edit note")
            yield TextArea(id="edit-note")

            with Horizontal(id="details-buttons"):
                yield Button("Continue [ctrl+s]", id="continue-button", variant="success")
                yield Button("Cancel [escape]", id="cancel-button")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue-button":
            self.action_continue()
        elif event.button.id == "cancel-button":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _select_value(self, widget_id: str) -> str | None:
        select = self.query_one(f"#{widget_id}", Select)
        return None if select.value is Select.NULL else select.value

    def action_continue(self) -> None:
        links_text = self.query_one("#external-links", TextArea).text
        external_links = [line.strip() for line in links_text.splitlines() if line.strip()]

        result = {
            "status": self._select_value("status"),
            "language": self.query_one("#language", Input).value.strip() or None,
            "script": self.query_one("#script", Input).value.strip() or None,
            "country": self.query_one("#country", Input).value.strip() or None,
            "packaging": self._select_value("packaging"),
            "disambiguation": self.query_one("#disambiguation", Input).value.strip() or None,
            "annotation": self.query_one("#annotation", TextArea).text.strip() or None,
            "external_links": external_links,
            "edit_note": self.query_one("#edit-note", TextArea).text.strip() or None,
        }
        self.dismiss(result)

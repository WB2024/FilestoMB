"""Collects the release-group fields MusicBrainz can seed beyond name and
artist: disambiguation, primary type, secondary types, and an edit note.

MusicBrainz's release-group create form has no seedable field for external
links (unlike the release form), so that's not offered here -- add those on
the page itself after it opens.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, SelectionList, Static, TextArea

from ..mb.seed import RELEASE_GROUP_PRIMARY_TYPES, RELEASE_GROUP_SECONDARY_TYPES


class ReleaseGroupDetailsScreen(Screen[dict]):
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
        with Vertical(id="details-body"):
            yield Static(f"Creating release group [b]{self._title}[/b] by {self._artist}")
            yield Label("Disambiguation")
            yield Input(placeholder="e.g. remastered edition", id="disambiguation")
            yield Label("Primary type")
            yield Select(
                [(name, name) for name in RELEASE_GROUP_PRIMARY_TYPES],
                id="primary-type",
                allow_blank=True,
            )
            yield Label("Secondary types")
            yield SelectionList(
                *[(name, name) for name in RELEASE_GROUP_SECONDARY_TYPES], id="secondary-types"
            )
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

    def action_continue(self) -> None:
        primary_type_select = self.query_one("#primary-type", Select)
        primary_type = None if primary_type_select.value is Select.NULL else primary_type_select.value
        result = {
            "disambiguation": self.query_one("#disambiguation", Input).value.strip() or None,
            "primary_type": primary_type,
            "secondary_types": list(self.query_one("#secondary-types", SelectionList).selected),
            "edit_note": self.query_one("#edit-note", TextArea).text.strip() or None,
        }
        self.dismiss(result)

"""Submit screen: open MusicBrainz's seeded edit forms for anything missing."""

from __future__ import annotations

import webbrowser

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..mb import seed
from ..models import Album, EntityType, MatchResult, MatchStatus

VIEW_URL = {
    EntityType.ARTIST: "https://musicbrainz.org/artist/{mbid}",
    EntityType.LABEL: "https://musicbrainz.org/label/{mbid}",
    EntityType.RELEASE_GROUP: "https://musicbrainz.org/release-group/{mbid}",
    EntityType.RELEASE: "https://musicbrainz.org/release/{mbid}",
}

ENTITY_LABELS = {
    EntityType.ARTIST: "Artist",
    EntityType.LABEL: "Label",
    EntityType.RELEASE_GROUP: "Release Group",
    EntityType.RELEASE: "Release",
}

# Dependency order: create parents before the entities that reference them.
SUBMIT_ORDER = [
    EntityType.LABEL,
    EntityType.ARTIST,
    EntityType.RELEASE_GROUP,
    EntityType.RELEASE,
]


class SubmitScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, album: Album, matches: dict[EntityType, MatchResult]) -> None:
        super().__init__()
        self.album = album
        self.matches = matches

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="submit-body"):
            yield Static(
                "MusicBrainz doesn't offer a direct write API for creating entities, so each "
                "button below opens a pre-filled ('seeded') MusicBrainz edit form in your browser "
                "for you to review and submit while logged in. Work top to bottom: create a missing "
                "label/artist first, then re-check MusicBrainz on the previous screen so the release "
                "group and release can reference it.",
                id="submit-hint",
            )
            for entity_type in SUBMIT_ORDER:
                result = self.matches.get(entity_type)
                yield Static(self._line(entity_type, result), id=f"submit-status-{entity_type.value}")
                if result is not None and result.status == MatchStatus.MISSING:
                    yield Button(
                        f"Create {ENTITY_LABELS[entity_type]} on MusicBrainz",
                        id=f"create-{entity_type.value}",
                    )
        yield Footer()

    def _line(self, entity_type: EntityType, result: MatchResult | None) -> str:
        label = ENTITY_LABELS[entity_type]
        if result is None:
            return f"[b]{label}[/b]: [dim]not applicable[/dim]"
        if result.status == MatchStatus.MATCHED or result.selected_mbid:
            url = VIEW_URL[entity_type].format(mbid=result.selected_mbid)
            return f"[b]{label}[/b]: [green]using existing[/green] {url}"
        if result.status == MatchStatus.AMBIGUOUS:
            return f"[b]{label}[/b]: [yellow]ambiguous -- go back and pick a match[/yellow]"
        return f"[b]{label}[/b]: [red]missing[/red]"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("create-"):
            return
        entity_type = EntityType(button_id.removeprefix("create-"))
        self._open_seed_form(entity_type)

    def _open_seed_form(self, entity_type: EntityType) -> None:
        album = self.album
        if entity_type == EntityType.ARTIST:
            webbrowser.open(seed.seed_artist_url(album.artist))
        elif entity_type == EntityType.LABEL:
            if not album.label:
                self.notify("This album has no label to create.", severity="warning")
                return
            webbrowser.open(seed.seed_label_url(album.label))
        elif entity_type == EntityType.RELEASE_GROUP:
            webbrowser.open(seed.seed_release_group_url(album.title, album.artist))
        elif entity_type == EntityType.RELEASE:
            release_group_mbid = self._selected_mbid(EntityType.RELEASE_GROUP)
            artist_mbid = self._selected_mbid(EntityType.ARTIST)
            label_mbid = self._selected_mbid(EntityType.LABEL)
            path = seed.build_release_seed_form(
                album,
                release_group_mbid=release_group_mbid,
                artist_mbid=artist_mbid,
                label_mbid=label_mbid,
            )
            webbrowser.open(f"file://{path}")
        self.notify(f"Opened the {ENTITY_LABELS[entity_type]} form in your browser.")

    def _selected_mbid(self, entity_type: EntityType) -> str | None:
        result = self.matches.get(entity_type)
        return result.selected_mbid if result else None

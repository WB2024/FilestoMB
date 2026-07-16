"""Review screen: edit album metadata and resolve MusicBrainz matches."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ..matching import match_album
from ..models import Album, EntityType, MatchResult, MatchStatus

ENTITY_ORDER = [
    EntityType.ARTIST,
    EntityType.LABEL,
    EntityType.RELEASE_GROUP,
    EntityType.RELEASE,
]

ENTITY_LABELS = {
    EntityType.ARTIST: "Artist",
    EntityType.LABEL: "Label",
    EntityType.RELEASE_GROUP: "Release Group",
    EntityType.RELEASE: "Release",
}

STATUS_MARKERS = {
    MatchStatus.UNCHECKED: "[dim]not checked yet[/dim]",
    MatchStatus.MATCHED: "[green]matched[/green]",
    MatchStatus.AMBIGUOUS: "[yellow]needs a pick[/yellow]",
    MatchStatus.MISSING: "[red]missing -- will be created[/red]",
}

FIELDS = [
    ("title", "Title"),
    ("artist", "Artist"),
    ("date", "Date"),
    ("label", "Label"),
    ("catalog_number", "Catalog #"),
    ("barcode", "Barcode"),
]


class ReviewScreen(Screen):
    BINDINGS = [
        ("m", "check_musicbrainz", "Check MusicBrainz"),
        ("c", "continue_to_submit", "Continue"),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, album: Album) -> None:
        super().__init__()
        self.album = album
        self.matches: dict[EntityType, MatchResult] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="review-body"):
            yield Static(f"[b]{self.album.directory}[/b] -- {len(self.album.tracks)} track(s)")
            for field_id, label in FIELDS:
                with Horizontal(classes="field-row"):
                    yield Label(label, classes="field-label")
                    yield Input(
                        value=getattr(self.album, field_id) or "",
                        id=f"field-{field_id}",
                        classes="field-input",
                    )
            yield Button("Check MusicBrainz [m]", id="check-button", variant="primary")
            for entity_type in ENTITY_ORDER:
                yield Static(self._status_line(entity_type), id=f"status-{entity_type.value}")
                yield OptionList(id=f"match-{entity_type.value}")
            yield Button("Continue to submit [c]", id="continue-button", variant="success")
        yield Footer()

    def _status_line(self, entity_type: EntityType) -> str:
        label = ENTITY_LABELS[entity_type]
        result = self.matches.get(entity_type)
        if result is None:
            return f"[b]{label}[/b]: {STATUS_MARKERS[MatchStatus.UNCHECKED]}"
        return f"[b]{label}[/b] ({result.query}): {STATUS_MARKERS[result.status]}"

    def _sync_album_from_inputs(self) -> None:
        for field_id, _ in FIELDS:
            value = self.query_one(f"#field-{field_id}", Input).value.strip()
            setattr(self.album, field_id, value or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check-button":
            self.action_check_musicbrainz()
        elif event.button.id == "continue-button":
            self.action_continue_to_submit()

    def action_check_musicbrainz(self) -> None:
        self._sync_album_from_inputs()
        self._run_matching()

    @work(exclusive=True, group="matching")
    async def _run_matching(self) -> None:
        self.notify("Searching MusicBrainz...")
        try:
            self.matches = await match_album(self.app.mb_client, self.album)
        except Exception as error:  # network/HTTP errors surface here
            self.notify(f"MusicBrainz search failed: {error}", severity="error")
            return

        for entity_type in ENTITY_ORDER:
            self.query_one(f"#status-{entity_type.value}", Static).update(self._status_line(entity_type))
            option_list = self.query_one(f"#match-{entity_type.value}", OptionList)
            option_list.clear_options()
            result = self.matches.get(entity_type)
            if result is None:
                continue
            for candidate in result.candidates:
                label = f"{candidate.name} ({candidate.score:.0f}%)"
                if candidate.disambiguation:
                    label += f" -- {candidate.disambiguation}"
                if candidate.extra:
                    label += f" [{candidate.extra}]"
                option_list.add_option(Option(label, id=candidate.mbid))
            if result.selected_mbid:
                for index, candidate in enumerate(result.candidates):
                    if candidate.mbid == result.selected_mbid:
                        option_list.highlighted = index
                        break

        self.notify("MusicBrainz search complete.")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_list_id = event.option_list.id or ""
        if not option_list_id.startswith("match-"):
            return
        entity_type = EntityType(option_list_id.removeprefix("match-"))
        result = self.matches.get(entity_type)
        if result is None:
            return
        result.selected_mbid = event.option_id
        self.query_one(f"#status-{entity_type.value}", Static).update(self._status_line(entity_type))

    def action_continue_to_submit(self) -> None:
        self._sync_album_from_inputs()
        if not self.matches:
            self.notify("Check MusicBrainz first (press m).", severity="warning")
            return

        from .submit import SubmitScreen

        self.app.push_screen(SubmitScreen(self.album, self.matches))

"""Submit screen: open MusicBrainz's seeded edit forms for anything missing."""

from __future__ import annotations

import webbrowser

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

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
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("a", "add_to_collection", "Add to collection"),
    ]

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
            yield Static(
                "Once the release has a MusicBrainz ID (matched above, or created and re-checked "
                "on the previous screen), you can file it in one of your personal collections.",
                id="collections-hint",
            )
            yield Button("Add release to a collection [a]", id="add-to-collection-button")
            yield OptionList(id="collections-list")
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
        if button_id == "add-to-collection-button":
            self.action_add_to_collection()
        elif button_id.startswith("create-"):
            entity_type = EntityType(button_id.removeprefix("create-"))
            self._open_seed_form(entity_type)

    def action_add_to_collection(self) -> None:
        release_mbid = self._selected_mbid(EntityType.RELEASE)
        if not release_mbid:
            self.notify(
                "This release has no MusicBrainz ID yet -- match or create it first.",
                severity="warning",
            )
            return
        if not self.app.oauth.is_logged_in:
            self.notify("Log in to MusicBrainz first (press l).", severity="warning")
            return
        self._load_collections()

    @work(exclusive=True, group="collections")
    async def _load_collections(self) -> None:
        try:
            access_token = await self.app.oauth.get_access_token()
            if not self.app.oauth_username:
                self.app.oauth_username = await self.app.oauth.fetch_username()
            collections = await self.app.mb_client.list_collections(
                access_token, username=self.app.oauth_username or None
            )
        except Exception as error:
            self.notify(f"Couldn't load your collections: {error}", severity="error")
            return

        release_collections = [c for c in collections if c.get("entity-type") == "release"]
        option_list = self.query_one("#collections-list", OptionList)
        option_list.clear_options()
        for collection in release_collections:
            option_list.add_option(Option(collection.get("name", collection["id"]), id=collection["id"]))

        if not release_collections:
            self.notify("No release collections found on your MusicBrainz account.", severity="warning")
        else:
            self.notify("Pick a collection below.")
            option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "collections-list" or event.option_id is None:
            return
        release_mbid = self._selected_mbid(EntityType.RELEASE)
        if release_mbid:
            self._add_release_to_collection(event.option_id, release_mbid)

    @work(exclusive=True, group="collections")
    async def _add_release_to_collection(self, collection_mbid: str, release_mbid: str) -> None:
        try:
            access_token = await self.app.oauth.get_access_token()
            await self.app.mb_client.add_release_to_collection(collection_mbid, release_mbid, access_token)
        except Exception as error:
            self.notify(f"Couldn't add release to collection: {error}", severity="error")
            return
        self.notify("Added to your collection.")

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

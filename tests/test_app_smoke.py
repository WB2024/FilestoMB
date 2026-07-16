"""End-to-end smoke tests driving the real Textual app headlessly."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response
from textual.widgets import Input, OptionList

from filestomb.app import FilesToMBApp
from filestomb.screens.browse import BrowseScreen
from filestomb.screens.review import ReviewScreen
from filestomb.screens.submit import SubmitScreen


@pytest.fixture(autouse=True)
def _mb_contact(monkeypatch):
    monkeypatch.setenv("MB_CONTACT", "test@example.com")


async def test_app_boots_to_browse_screen(tmp_path: Path) -> None:
    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test():
        assert isinstance(app.screen, BrowseScreen)
    await app.mb_client.aclose()


async def test_scanning_a_directory_pushes_review_screen(make_flac, tmp_path: Path) -> None:
    album_dir = tmp_path / "Album"
    make_flac({"title": "Song", "artist": "Artist", "album": "Album"}, directory=album_dir)

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        browse_screen = app.screen
        assert isinstance(browse_screen, BrowseScreen)

        worker = browse_screen._scan(album_dir)
        await worker.wait()
        await pilot.pause()

        assert isinstance(app.screen, ReviewScreen)
        title_input = app.screen.query_one("#field-title", Input)
        assert title_input.value == "Album"
    await app.mb_client.aclose()


@respx.mock
async def test_check_musicbrainz_then_continue_reaches_submit_screen(make_flac, tmp_path: Path) -> None:
    respx.get("https://musicbrainz.org/ws/2/artist").mock(
        return_value=Response(200, json={"artists": [{"id": "artist-1", "name": "Artist", "score": 100}]})
    )
    respx.get("https://musicbrainz.org/ws/2/release-group").mock(
        return_value=Response(200, json={"release-groups": []})
    )
    respx.get("https://musicbrainz.org/ws/2/release").mock(return_value=Response(200, json={"releases": []}))

    album_dir = tmp_path / "Album"
    make_flac({"title": "Song", "artist": "Artist", "album": "Album"}, directory=album_dir)

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        browse_screen = app.screen
        scan_worker = browse_screen._scan(album_dir)
        await scan_worker.wait()
        await pilot.pause()

        review_screen = app.screen
        assert isinstance(review_screen, ReviewScreen)

        match_worker = review_screen._run_matching()
        await match_worker.wait()
        await pilot.pause()

        from filestomb.models import EntityType, MatchStatus

        assert review_screen.matches[EntityType.ARTIST].status == MatchStatus.MATCHED
        assert review_screen.matches[EntityType.RELEASE_GROUP].status == MatchStatus.MISSING

        artist_options = review_screen.query_one("#match-artist", OptionList)
        assert artist_options.option_count == 1

        review_screen.action_continue_to_submit()
        await pilot.pause()

        assert isinstance(app.screen, SubmitScreen)
    await app.mb_client.aclose()

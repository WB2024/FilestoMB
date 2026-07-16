"""Headless end-to-end tests for the directory-browser navigation, the
login status widget, and the release-group/release "extra details" screens
that precede opening their seed forms."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, Select, SelectionList, Static, TextArea

from filestomb.app import FilesToMBApp
from filestomb.models import Album, EntityType, MatchResult, MatchStatus
from filestomb.screens.browse import AlbumDirectoryTree, BrowseScreen
from filestomb.screens.release_details import ReleaseDetailsScreen
from filestomb.screens.release_group_details import ReleaseGroupDetailsScreen
from filestomb.screens.submit import SubmitScreen
from filestomb.widgets.login_status import LoginStatus


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("MB_CONTACT", "test@example.com")
    monkeypatch.setenv("MB_APP_NAME", "FilesToMB-Test")
    monkeypatch.setenv("MB_APP_VERSION", "0.0.0")
    monkeypatch.setenv("MB_API_BASE_URL", "https://musicbrainz.org/ws/2")
    monkeypatch.setenv("MB_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("MB_OAUTH_CLIENT_SECRET", "")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


async def test_login_status_widget_reflects_unconfigured_oauth(tmp_path: Path) -> None:
    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app.screen.query_one(LoginStatus)
        status._refresh()
        assert "not configured" in str(status.content)
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_up_button_reroots_tree_to_parent(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    app = FilesToMBApp(start_path=nested)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, BrowseScreen)
        tree = screen.query_one(AlbumDirectoryTree)
        assert Path(tree.path) == nested

        screen.action_go_up()
        await pilot.pause()

        assert Path(tree.path) == nested.parent
        assert str(nested.parent) in str(screen.query_one("#current-path", Static).content)
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_jump_to_path_updates_tree_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, BrowseScreen)
        path_input = screen.query_one("#path-input", Input)
        path_input.value = str(target)
        screen.on_input_submitted(Input.Submitted(path_input, str(target)))
        await pilot.pause()

        tree = screen.query_one(AlbumDirectoryTree)
        assert Path(tree.path) == target
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_release_group_details_screen_returns_collected_fields(tmp_path: Path) -> None:
    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        result_holder: dict = {}

        def _capture(result):
            result_holder["value"] = result

        app.push_screen(ReleaseGroupDetailsScreen("Test Album", "Test Artist"), _capture)
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ReleaseGroupDetailsScreen)

        screen.query_one("#disambiguation", Input).value = "remaster"
        screen.query_one("#primary-type", Select).value = "Album"
        screen.query_one("#secondary-types", SelectionList).select("Live")
        screen.query_one("#edit-note", TextArea).text = "note"
        screen.action_continue()
        await pilot.pause()

        assert result_holder["value"] == {
            "disambiguation": "remaster",
            "primary_type": "Album",
            "secondary_types": ["Live"],
            "edit_note": "note",
        }
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_release_group_details_screen_cancel_returns_none(tmp_path: Path) -> None:
    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        result_holder: dict = {}
        app.push_screen(
            ReleaseGroupDetailsScreen("Test Album", "Test Artist"),
            lambda result: result_holder.update(value=result),
        )
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ReleaseGroupDetailsScreen)

        screen.action_cancel()
        await pilot.pause()

        assert result_holder["value"] is None
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_submit_screen_opens_release_group_details_then_seed_url(
    tmp_path: Path, monkeypatch
) -> None:
    opened_urls = []
    monkeypatch.setattr("filestomb.screens.submit.webbrowser.open", opened_urls.append)

    album = Album(directory=tmp_path, title="Test Album", artist="Test Artist")
    matches = {
        EntityType.RELEASE_GROUP: MatchResult(
            entity_type=EntityType.RELEASE_GROUP, query="Test Album", status=MatchStatus.MISSING
        ),
    }

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(SubmitScreen(album, matches))
        await pilot.pause()
        submit_screen = app.screen
        assert isinstance(submit_screen, SubmitScreen)

        submit_screen._open_seed_form(EntityType.RELEASE_GROUP)
        await pilot.pause()
        details_screen = app.screen
        assert isinstance(details_screen, ReleaseGroupDetailsScreen)

        details_screen.query_one("#primary-type", Select).value = "Album"
        details_screen.action_continue()
        await pilot.pause()

        assert isinstance(app.screen, SubmitScreen)
        assert len(opened_urls) == 1
        assert "edit-release-group.primary_type_id=1" in opened_urls[0]
    await app.mb_client.aclose()
    await app.oauth.aclose()


async def test_submit_screen_opens_release_details_then_seed_form(tmp_path: Path, monkeypatch) -> None:
    opened_urls = []
    monkeypatch.setattr("filestomb.screens.submit.webbrowser.open", opened_urls.append)

    album = Album(directory=tmp_path, title="Test Album", artist="Test Artist")
    matches = {
        EntityType.RELEASE: MatchResult(
            entity_type=EntityType.RELEASE, query="Test Album", status=MatchStatus.MISSING
        ),
    }

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(SubmitScreen(album, matches))
        await pilot.pause()
        submit_screen = app.screen
        assert isinstance(submit_screen, SubmitScreen)

        submit_screen._open_seed_form(EntityType.RELEASE)
        await pilot.pause()
        details_screen = app.screen
        assert isinstance(details_screen, ReleaseDetailsScreen)

        details_screen.query_one("#status", Select).value = "Official"
        details_screen.query_one("#country", Input).value = "gb"
        details_screen.action_continue()
        await pilot.pause()

        assert isinstance(app.screen, SubmitScreen)
        assert len(opened_urls) == 1
        assert opened_urls[0].startswith("file://")
        html = Path(opened_urls[0].removeprefix("file://")).read_text()
        assert 'name="status" value="Official"' in html
        assert 'name="events.0.country" value="GB"' in html
    await app.mb_client.aclose()
    await app.oauth.aclose()

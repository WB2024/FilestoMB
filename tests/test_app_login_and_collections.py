"""Headless end-to-end test of the OAuth2 login flow and adding a release
to a MusicBrainz collection, driving the real Textual app."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response
from textual.widgets import OptionList

from filestomb.app import FilesToMBApp
from filestomb.models import Album, EntityType, MatchResult, MatchStatus
from filestomb.screens.login import LoginScreen
from filestomb.screens.submit import SubmitScreen


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    # See tests/test_app_smoke.py -- without this, python-dotenv loads the
    # real (gitignored) .env and oauth.py's Token.load()/save() touch the
    # real ~/.config/filestomb/token.json instead of a sandboxed path.
    monkeypatch.setenv("MB_CONTACT", "test@example.com")
    monkeypatch.setenv("MB_APP_NAME", "FilesToMB-Test")
    monkeypatch.setenv("MB_APP_VERSION", "0.0.0")
    monkeypatch.setenv("MB_API_BASE_URL", "https://musicbrainz.org/ws/2")
    monkeypatch.setenv("MB_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("MB_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@respx.mock
async def test_login_then_add_release_to_collection(tmp_path: Path) -> None:
    respx.post("https://musicbrainz.org/oauth2/token").mock(
        return_value=Response(
            200, json={"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 3600}
        )
    )
    respx.get("https://musicbrainz.org/oauth2/userinfo").mock(
        return_value=Response(200, json={"sub": "test_user"})
    )
    respx.get("https://musicbrainz.org/ws/2/collection").mock(
        return_value=Response(
            200,
            json={"collections": [{"id": "col-1", "name": "My Albums", "entity-type": "release"}]},
        )
    )
    add_route = respx.put("https://musicbrainz.org/ws/2/collection/col-1/releases/release-1").mock(
        return_value=Response(200)
    )

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        assert not app.oauth.is_logged_in

        app.push_screen(LoginScreen())
        await pilot.pause()
        login_screen = app.screen
        assert isinstance(login_screen, LoginScreen)

        login_worker = login_screen._exchange("fake-auth-code")
        await login_worker.wait()
        await pilot.pause()

        assert app.oauth.is_logged_in
        assert app.oauth_username == "test_user"
        assert not isinstance(app.screen, LoginScreen)  # login pops itself off on success

        album = Album(directory=tmp_path, title="Test Album", artist="Test Artist")
        matches = {
            EntityType.RELEASE: MatchResult(
                entity_type=EntityType.RELEASE,
                query="Test Album",
                status=MatchStatus.MATCHED,
                selected_mbid="release-1",
            ),
        }
        app.push_screen(SubmitScreen(album, matches))
        await pilot.pause()
        submit_screen = app.screen
        assert isinstance(submit_screen, SubmitScreen)

        load_worker = submit_screen._load_collections()
        await load_worker.wait()
        await pilot.pause()

        option_list = submit_screen.query_one("#collections-list", OptionList)
        assert option_list.option_count == 1

        add_worker = submit_screen._add_release_to_collection("col-1", "release-1")
        await add_worker.wait()

        assert add_route.called

    await app.mb_client.aclose()
    await app.oauth.aclose()


@respx.mock
async def test_add_to_collection_without_login_warns(tmp_path: Path) -> None:
    album = Album(directory=tmp_path, title="Test Album", artist="Test Artist")
    matches = {
        EntityType.RELEASE: MatchResult(
            entity_type=EntityType.RELEASE,
            query="Test Album",
            status=MatchStatus.MATCHED,
            selected_mbid="release-1",
        ),
    }

    app = FilesToMBApp(start_path=tmp_path)
    async with app.run_test() as pilot:
        assert not app.oauth.is_logged_in
        app.push_screen(SubmitScreen(album, matches))
        await pilot.pause()
        submit_screen = app.screen
        assert isinstance(submit_screen, SubmitScreen)

        # Should warn and return without attempting any network call.
        submit_screen.action_add_to_collection()
        await pilot.pause()

        option_list = submit_screen.query_one("#collections-list", OptionList)
        assert option_list.option_count == 0

    await app.mb_client.aclose()
    await app.oauth.aclose()

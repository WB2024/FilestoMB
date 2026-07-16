from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from filestomb.mb import seed
from filestomb.models import Album, Track


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_seed_artist_url() -> None:
    url = seed.seed_artist_url("Test Artist")
    assert url.startswith("https://musicbrainz.org/artist/create?")
    assert _query(url)["edit-artist.name"] == ["Test Artist"]


def test_seed_label_url() -> None:
    url = seed.seed_label_url("Test Records")
    assert url.startswith("https://musicbrainz.org/label/create?")
    assert _query(url)["edit-label.name"] == ["Test Records"]


def test_seed_release_group_url_includes_artist_credit() -> None:
    url = seed.seed_release_group_url("Test Album", "Test Artist")
    query = _query(url)
    assert query["edit-release-group.name"] == ["Test Album"]
    assert query["edit-release-group.artist_credit.names.0.artist.name"] == ["Test Artist"]


def test_build_release_seed_form_writes_html_with_track_fields() -> None:
    album = Album(
        directory=Path("/tmp/album"),
        title="Test Album",
        artist="Test Artist",
        date="1999-03-01",
        barcode="0123456789012",
        label="Test Records",
        catalog_number="TR001",
        tracks=[
            Track(
                path=Path("/tmp/album/01.flac"),
                title="Opening",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Artist",
                track_number="1",
                disc_number="1",
            ),
            Track(
                path=Path("/tmp/album/02.flac"),
                title="Second Song",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Artist",
                track_number="2",
                disc_number="1",
            ),
        ],
    )

    path = seed.build_release_seed_form(album)
    try:
        html = path.read_text()
        assert 'action="https://musicbrainz.org/release/add"' in html
        assert 'name="name" value="Test Album"' in html
        assert 'name="artist_credit.names.0.name" value="Test Artist"' in html
        assert 'name="events.0.date.year" value="1999"' in html
        assert 'name="barcode" value="0123456789012"' in html
        assert 'name="labels.0.name" value="Test Records"' in html
        assert 'name="labels.0.catalog_number" value="TR001"' in html
        assert 'name="mediums.0.track.0.name" value="Opening"' in html
        assert 'name="mediums.0.track.1.name" value="Second Song"' in html
    finally:
        path.unlink(missing_ok=True)


def test_build_release_seed_form_uses_mbids_when_available() -> None:
    album = Album(directory=Path("/tmp/album"), title="Test Album", artist="Test Artist")

    path = seed.build_release_seed_form(
        album, release_group_mbid="rg-1", artist_mbid="artist-1", label_mbid="label-1"
    )
    try:
        html = path.read_text()
        assert 'name="release_group" value="rg-1"' in html
        assert 'name="artist_credit.names.0.mbid" value="artist-1"' in html
    finally:
        path.unlink(missing_ok=True)

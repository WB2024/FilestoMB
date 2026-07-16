from __future__ import annotations

from pathlib import Path

from filestomb import tags


def test_scan_directory_reads_album_from_tracks(make_flac, tmp_path: Path) -> None:
    album_dir = tmp_path / "Album"
    make_flac(
        {
            "title": "Opening",
            "artist": "Test Artist",
            "albumartist": "Test Artist",
            "album": "Test Album",
            "tracknumber": "1",
            "discnumber": "1",
            "date": "1999-03-01",
            "label": "Test Records",
            "catalognumber": "TR001",
            "barcode": "0123456789012",
        },
        directory=album_dir,
    )
    make_flac(
        {
            "title": "Second Song",
            "artist": "Test Artist",
            "albumartist": "Test Artist",
            "album": "Test Album",
            "tracknumber": "2",
            "discnumber": "1",
        },
        directory=album_dir,
    )

    album = tags.scan_directory(album_dir)

    assert album is not None
    assert album.title == "Test Album"
    assert album.artist == "Test Artist"
    assert album.date == "1999-03-01"
    assert album.label == "Test Records"
    assert album.catalog_number == "TR001"
    assert album.barcode == "0123456789012"
    assert len(album.tracks) == 2
    titles = sorted(track.title for track in album.tracks)
    assert titles == ["Opening", "Second Song"]

    # The fixture encodes a 0.1s (100ms) silent clip; allow generous slack
    # for container/encoder rounding rather than asserting an exact value.
    for track in album.tracks:
        assert track.length_ms is not None
        assert 0 < track.length_ms < 2000


def test_scan_directory_returns_none_when_no_audio(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "notes.txt").write_text("not audio")

    assert tags.scan_directory(empty_dir) is None


def test_scan_directory_falls_back_to_folder_name(make_flac, tmp_path: Path) -> None:
    album_dir = tmp_path / "Untagged Folder"
    make_flac({"artist": "Solo Artist"}, directory=album_dir)

    album = tags.scan_directory(album_dir)

    assert album is not None
    assert album.title == "Untagged Folder"
    assert album.artist == "Solo Artist"

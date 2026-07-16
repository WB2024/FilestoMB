"""Builders for MusicBrainz's "seeded" edit forms.

MusicBrainz has no public write API for creating artists, labels, release
groups, or releases. New entities are created through the ordinary edit
forms on musicbrainz.org, submitted by a logged-in human. What MusicBrainz
does support is *seeding*: pre-filling those forms via URL query parameters
(or, for the Release editor, a POSTed HTML form) so the only thing left to
do is review and click submit.

References:
- https://musicbrainz.org/doc/Development/Seeding
- https://musicbrainz.org/doc/Development/Seeding/Release_Editor

Nothing here submits an edit on its own. Every function returns either a
URL or a local HTML file that MusicBrainz will render as a pre-filled, not
yet submitted, edit form.
"""

from __future__ import annotations

import html
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from ..models import Album

BASE_URL = "https://musicbrainz.org"


def seed_artist_url(name: str) -> str:
    params = {"edit-artist.name": name}
    return f"{BASE_URL}/artist/create?{urlencode(params)}"


def seed_label_url(name: str) -> str:
    params = {"edit-label.name": name}
    return f"{BASE_URL}/label/create?{urlencode(params)}"


def seed_release_group_url(title: str, artist_name: str, primary_type: str | None = None) -> str:
    params = {
        "edit-release-group.name": title,
        "edit-release-group.artist_credit.names.0.artist.name": artist_name,
    }
    if primary_type:
        params["edit-release-group.primary_type_id"] = primary_type
    return f"{BASE_URL}/release-group/create?{urlencode(params)}"


def _release_form_fields(
    album: Album,
    release_group_mbid: str | None,
    artist_mbid: str | None,
    label_mbid: str | None,
) -> dict[str, str]:
    fields: dict[str, str] = {"name": album.title}

    if artist_mbid:
        fields["artist_credit.names.0.mbid"] = artist_mbid
    else:
        fields["artist_credit.names.0.name"] = album.artist

    if release_group_mbid:
        fields["release_group"] = release_group_mbid

    if album.date:
        parts = album.date.split("-")
        for index, part_name in enumerate(("year", "month", "day")):
            if index < len(parts) and parts[index]:
                fields[f"events.0.date.{part_name}"] = parts[index]

    if album.barcode:
        fields["barcode"] = album.barcode

    if album.label:
        if label_mbid:
            fields["labels.0.mbid"] = label_mbid
        else:
            fields["labels.0.name"] = album.label
    if album.catalog_number:
        fields["labels.0.catalog_number"] = album.catalog_number

    tracks_by_disc: dict[int, list] = {}
    for track in album.tracks:
        try:
            disc_index = int(track.disc_number or "1") - 1
        except ValueError:
            disc_index = 0
        tracks_by_disc.setdefault(max(disc_index, 0), []).append(track)

    for disc_index, disc_tracks in tracks_by_disc.items():
        def _track_number(track) -> int:
            try:
                return int(track.track_number or "0")
            except ValueError:
                return 0

        for track_index, track in enumerate(sorted(disc_tracks, key=_track_number)):
            prefix = f"mediums.{disc_index}.track.{track_index}"
            fields[f"{prefix}.name"] = track.title
            if track.track_number:
                fields[f"{prefix}.number"] = track.track_number

    return fields


def build_release_seed_form(
    album: Album,
    release_group_mbid: str | None = None,
    artist_mbid: str | None = None,
    label_mbid: str | None = None,
) -> Path:
    """Write a small, auto-submitting HTML page that opens MusicBrainz's
    "Add Release" editor pre-filled with this album's data, and return its
    local path. The release editor needs POSTed form data rather than a
    query string once a track listing is involved, so seeding it means
    generating a real HTML form rather than just a URL.
    """
    fields = _release_form_fields(album, release_group_mbid, artist_mbid, label_mbid)
    inputs = "\n".join(
        f'    <input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}">'
        for key, value in fields.items()
    )
    document = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Seeding MusicBrainz release&hellip;</title></head>
<body onload="document.forms[0].submit()">
  <p>Opening the MusicBrainz &ldquo;Add Release&rdquo; editor, pre-filled from
  &ldquo;{html.escape(album.title)}&rdquo;&hellip;</p>
  <form method="post" action="{BASE_URL}/release/add">
{inputs}
    <noscript><button type="submit">Continue to MusicBrainz</button></noscript>
  </form>
</body>
</html>
"""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", prefix="filestomb-seed-", delete=False, encoding="utf-8"
    )
    handle.write(document)
    handle.close()
    return Path(handle.name)

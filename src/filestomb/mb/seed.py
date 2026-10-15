"""Builders for MusicBrainz's "seeded" edit forms.

MusicBrainz has no public write API for creating artists, labels, release
groups, or releases. New entities are created through the ordinary edit
forms on musicbrainz.org, submitted by a logged-in human. What MusicBrainz
does support is *seeding*: pre-filling those forms via URL query parameters
(or, for the Release editor, a POSTed HTML form) so the only thing left to
do is review and click submit.

Field names here are verified against MusicBrainz's own server source
(metabrainz/musicbrainz-server), not just its docs, which turned out to
describe an older seeding format in places:
- Release form fields: lib/MusicBrainz/Server/Controller/ReleaseEditor.pm,
  sub _process_seeded_data and friends -- these are flat, unprefixed query
  params (name, comment, annotation, status, packaging, language, script,
  events.N.country, events.N.date.{year,month,day}, labels.N.*,
  mediums.N.track.M.*, urls.N.url, edit_note).
- Release group form fields: lib/MusicBrainz/Server/Form/ReleaseGroup.pm --
  a separate, older FormHandler-based form prefixed "edit-release-group.",
  where primary_type_id/secondary_type_ids are *numeric* database IDs, not
  the plain names the release form's "status"/"packaging" fields use. The
  IDs below are read from admin/sql and t/sql/initial.sql in that repo and
  are stable, long-lived reference data.
- The release group form has no external-link (urls.*) field at all, so
  external links can't be seeded there -- only for a release.

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

# release_group_primary_type table (admin/sql/InsertDefaultRows.sql /
# t/sql/initial.sql in metabrainz/musicbrainz-server).
RELEASE_GROUP_PRIMARY_TYPES: dict[str, int] = {
    "Album": 1,
    "Single": 2,
    "EP": 3,
    "Other": 11,
    "Broadcast": 12,
}

# release_group_secondary_type table, same source.
RELEASE_GROUP_SECONDARY_TYPES: dict[str, int] = {
    "Compilation": 1,
    "Soundtrack": 2,
    "Spokenword": 3,
    "Interview": 4,
    "Audiobook": 5,
    "Live": 6,
    "Remix": 7,
    "DJ-mix": 8,
    "Mixtape/Street": 9,
    "Demo": 10,
}

# The release form's "status" and "packaging" fields are matched by exact
# name server-side (ReleaseStatus->find_by_name / ReleasePackaging->find_by_name),
# not a numeric ID -- these lists are just the confirmed valid names.
RELEASE_STATUSES: list[str] = [
    "Official",
    "Promotion",
    "Bootleg",
    "Pseudo-Release",
    "Withdrawn",
    "Cancelled",
]

RELEASE_PACKAGINGS: list[str] = [
    "Jewel Case",
    "Slim Jewel Case",
    "Digipak",
    "Cardboard/Paper Sleeve",
    "Other",
    "None",
]


def seed_artist_url(name: str) -> str:
    params = {"edit-artist.name": name}
    return f"{BASE_URL}/artist/create?{urlencode(params)}"


def seed_label_url(name: str) -> str:
    params = {"edit-label.name": name}
    return f"{BASE_URL}/label/create?{urlencode(params)}"


def seed_release_group_url(
    title: str,
    artist_name: str,
    disambiguation: str | None = None,
    primary_type: str | None = None,
    secondary_types: list[str] | None = None,
    edit_note: str | None = None,
) -> str:
    params: dict[str, str] = {
        "edit-release-group.name": title,
        "edit-release-group.artist_credit.names.0.artist.name": artist_name,
    }
    if disambiguation:
        params["edit-release-group.comment"] = disambiguation
    if primary_type:
        type_id = RELEASE_GROUP_PRIMARY_TYPES.get(primary_type)
        if type_id is not None:
            params["edit-release-group.primary_type_id"] = str(type_id)
    for index, secondary_type in enumerate(secondary_types or []):
        type_id = RELEASE_GROUP_SECONDARY_TYPES.get(secondary_type)
        if type_id is not None:
            params[f"edit-release-group.secondary_type_ids.{index}"] = str(type_id)
    if edit_note:
        # Best-effort: not part of ReleaseGroup.pm's own field list, but
        # "edit_note" is a common unprefixed convention across MB's create
        # forms (confirmed for Release; harmless if ignored here).
        params["edit_note"] = edit_note
    return f"{BASE_URL}/release-group/create?{urlencode(params)}"


def _release_form_fields(
    album: Album,
    release_group_mbid: str | None,
    artist_mbid: str | None,
    label_mbid: str | None,
    status: str | None = None,
    language: str | None = None,
    script: str | None = None,
    country: str | None = None,
    packaging: str | None = None,
    annotation: str | None = None,
    disambiguation: str | None = None,
    external_links: list[str] | None = None,
    edit_note: str | None = None,
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

    if country:
        fields["events.0.country"] = country.upper()

    if album.barcode:
        fields["barcode"] = album.barcode

    if album.label:
        if label_mbid:
            fields["labels.0.mbid"] = label_mbid
        else:
            fields["labels.0.name"] = album.label
    if album.catalog_number:
        fields["labels.0.catalog_number"] = album.catalog_number

    if status:
        fields["status"] = status
    if language:
        fields["language"] = language
    if script:
        fields["script"] = script
    if packaging:
        fields["packaging"] = packaging
    if annotation:
        fields["annotation"] = annotation
    if disambiguation:
        fields["comment"] = disambiguation
    for index, url in enumerate(external_links or []):
        if url:
            fields[f"urls.{index}.url"] = url
    if edit_note:
        fields["edit_note"] = edit_note

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
            if track.length_ms:
                fields[f"{prefix}.length"] = str(track.length_ms)

    return fields


def build_release_seed_fields(album: Album, **kwargs) -> dict[str, str]:
    """The flat form fields for MusicBrainz's "Add Release" editor, for
    callers (the web UI) that POST them to ``{BASE_URL}/release/add`` from
    the user's own browser instead of writing a local HTML file.
    Accepts the same keyword arguments as `build_release_seed_form`.
    """
    return _release_form_fields(
        album,
        kwargs.pop("release_group_mbid", None),
        kwargs.pop("artist_mbid", None),
        kwargs.pop("label_mbid", None),
        **kwargs,
    )


def build_release_seed_form(
    album: Album,
    release_group_mbid: str | None = None,
    artist_mbid: str | None = None,
    label_mbid: str | None = None,
    status: str | None = None,
    language: str | None = None,
    script: str | None = None,
    country: str | None = None,
    packaging: str | None = None,
    annotation: str | None = None,
    disambiguation: str | None = None,
    external_links: list[str] | None = None,
    edit_note: str | None = None,
) -> Path:
    """Write a small, auto-submitting HTML page that opens MusicBrainz's
    "Add Release" editor pre-filled with this album's data, and return its
    local path. The release editor needs POSTed form data rather than a
    query string once a track listing is involved, so seeding it means
    generating a real HTML form rather than just a URL.
    """
    fields = _release_form_fields(
        album,
        release_group_mbid,
        artist_mbid,
        label_mbid,
        status=status,
        language=language,
        script=script,
        country=country,
        packaging=packaging,
        annotation=annotation,
        disambiguation=disambiguation,
        external_links=external_links,
        edit_note=edit_note,
    )
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

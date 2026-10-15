"""Batch foundations: album discovery, the store, and the strict matcher."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from filestomb.batch import discovery, store
from filestomb.batch.matcher import clean_title, evaluate_album
from filestomb.models import Album, Track


# ---------------------------------------------------------------- discovery


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_finds_albums_at_any_depth_without_descending_into_them(tmp_path):
    root = tmp_path / "Unmanaged"
    touch(root / "A" / "Artist One" / "Album One" / "01.flac")
    touch(root / "A" / "Artist One" / "Album One" / "Scans" / "01.flac")  # inside an album: not a new album
    touch(root / "A" / "Artist One" / "Album Two [FLAC]" / "01.mp3")
    touch(root / "B" / "Artist Two" / "Only Album" / "01.m4a")
    touch(root / "Flat Album" / "01.ogg")
    (root / "Empty Artist" / "Empty Album").mkdir(parents=True)
    touch(root / "Notes" / "readme.txt")
    found = [p.relative_to(root).as_posix() for p in discovery.find_album_dirs(root)]
    assert found == ["A/Artist One/Album One", "A/Artist One/Album Two [FLAC]", "B/Artist Two/Only Album", "Flat Album"]


def test_multi_disc_albums_are_one_album(tmp_path):
    root = tmp_path / "U"
    touch(root / "Artist" / "Big Box" / "CD1" / "01.flac")
    touch(root / "Artist" / "Big Box" / "CD2" / "01.flac")
    touch(root / "Artist" / "Big Box" / "Artwork" / "front.jpg")
    touch(root / "Artist" / "Other" / "Disc 1" / "01.flac")
    touch(root / "Artist" / "Other" / "Disc 2" / "01.flac")
    found = [p.relative_to(root).as_posix() for p in discovery.find_album_dirs(root)]
    assert found == ["Artist/Big Box", "Artist/Other"]


def test_skips_hidden_system_dirs_and_symlinks(tmp_path):
    root = tmp_path / "U"
    touch(root / ".hidden" / "Album" / "01.flac")
    touch(root / "$RECYCLE.BIN" / "Album" / "01.flac")
    touch(root / "Real" / "Album" / "01.flac")
    outside = tmp_path / "outside"
    touch(outside / "Album" / "01.flac")
    os.symlink(outside, root / "link")
    assert [p.relative_to(root).as_posix() for p in discovery.find_album_dirs(root)] == ["Real/Album"]


def test_fingerprint_changes_when_audio_changes_but_not_for_other_files(tmp_path):
    album = tmp_path / "Album"
    track = touch(album / "01.flac")
    before = discovery.fingerprint(album)
    (album / "cover.jpg").write_bytes(b"jpg")
    assert discovery.fingerprint(album) == before
    track.write_bytes(b"changed!")
    assert discovery.fingerprint(album) != before
    assert discovery.count_audio(album) == 1


def test_cancellation_stops_the_walk(tmp_path):
    root = tmp_path / "U"
    for n in range(5):
        touch(root / f"A{n}" / "Album" / "01.flac")
    assert discovery.find_album_dirs(root, cancelled=lambda: True) == []


# ---------------------------------------------------------------- store


def test_store_roundtrip_and_counts(tmp_path):
    s = store.BatchStore(tmp_path / "b.db")
    assert s.add_found("U", ["U/a", "U/b", "U/c"]) == (3, 0)
    assert s.add_found("U", ["U/a", "U/d"]) == (1, 1)  # existing rows are not reset
    s.update("U/a", status=store.READY, artist="X", title="Y", verdict={"reasons": ["ok"]})
    s.update("U/b", status=store.MISSING)
    assert s.get("U/a")["verdict"] == {"reasons": ["ok"]}
    counts = s.counts("U")
    assert counts[store.READY] == 1 and counts[store.MISSING] == 1 and counts[store.PENDING] == 2 and counts["total"] == 4
    assert [r["path"] for r in s.list("U", status=store.PENDING)] == ["U/c", "U/d"]
    assert [r["path"] for r in s.list("U", query="X")] == ["U/a"]
    assert s.add_found("U", ["U/a"]) == (0, 1)
    assert s.get("U/a")["status"] == store.READY


def test_forget_missing_keeps_history_and_interrupted_rows_are_flagged(tmp_path):
    s = store.BatchStore(tmp_path / "b.db")
    s.add_found("U", ["U/gone", "U/kept", "U/finished", "U/midway"])
    s.update("U/finished", status=store.DONE)
    s.update("U/midway", status=store.PROCESSING)
    assert s.forget_missing("U", {"U/kept"}) == 1  # only the untouched pending row
    assert s.get("U/finished")["status"] == store.DONE
    assert s.recover_interrupted() == 1
    assert s.get("U/midway")["status"] == store.PROBLEM and "interrupted" in s.get("U/midway")["message"]


# ---------------------------------------------------------------- matcher


class FakeMB:
    def __init__(self, hits, releases, groups=None, group_releases=None):
        self.hits, self.releases, self.searches, self.lookups = hits, releases, [], []
        self.groups, self.group_releases, self.group_searches, self.browses = groups or [], group_releases or {}, [], []

    async def search_release_groups_raw(self, title, artist, limit=5):
        self.group_searches.append((title, artist))
        return self.groups(title) if callable(self.groups) else self.groups

    async def browse_release_group_releases(self, rg_id, limit=100):
        self.browses.append(rg_id)
        if rg_id not in self.group_releases:
            raise httpx.HTTPStatusError("nope", request=httpx.Request("GET", "x"), response=httpx.Response(404))
        return self.group_releases[rg_id]

    async def search_releases_raw(self, title, artist, limit=10):
        self.searches.append((title, artist))
        return self.hits(title) if callable(self.hits) else self.hits

    async def lookup_release(self, mbid):
        self.lookups.append(mbid)
        if mbid not in self.releases:
            raise httpx.HTTPStatusError("nope", request=httpx.Request("GET", "x"), response=httpx.Response(404))
        return self.releases[mbid]


def release(mbid, title, tracks, date="2020-05-01", artist="Artist One", length=200_000):
    return {
        "id": mbid, "title": title, "date": date,
        "artist-credit": [{"name": artist, "joinphrase": "", "artist": {"id": "artist-1"}}],
        "release-group": {"id": "rg-1"},
        "media": [{"position": 1, "tracks": [
            {"id": f"{mbid}-t{i}", "position": i + 1, "title": t, "length": length,
             "artist-credit": [{"artist": {"id": "artist-1"}}], "recording": {"id": f"{mbid}-r{i}"}}
            for i, t in enumerate(tracks)]}],
    }


def hit(mbid, count, score=100, **extra):
    return {"id": mbid, "score": score, "track-count": count, **extra}


def local_album(titles, title="Great Album", artist="Artist One", date="2020", length=200_000, tagged_id=None):
    return Album(
        directory=Path("."), title=title, artist=artist, date=date,
        tracks=[Track(path=Path(f"{i + 1:02d}.flac"), title=t, artist=artist, album=title, album_artist=artist,
                      track_number=str(i + 1), length_ms=length, musicbrainz_release_id=tagged_id)
                for i, t in enumerate(titles)],
    )


TRACKS = ["Opener", "Middle Song", "Closer"]


async def test_exact_match_is_ready():
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS)})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status == "ready" and v.release_mbid == "r1" and v.candidates[0]["confident"]


async def test_deluxe_edition_is_review_not_ready():
    # The release has an extra bonus track: the local files are a standard edition. Never auto-process.
    mb = FakeMB([hit("deluxe", 4)], {"deluxe": release("deluxe", "Great Album (Deluxe)", [*TRACKS, "Bonus"])})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status == "review" and "no local file" in " ".join(v.candidates[0]["problems"])


async def test_unrelated_tracklist_is_missing():
    mb = FakeMB([hit("other", 3, score=70)], {"other": release("other", "Great Album", ["Foo", "Bar", "Baz"])})
    assert (await evaluate_album(mb, local_album(TRACKS))).status == "missing"


async def test_no_search_hits_is_missing():
    mb = FakeMB([], {})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status == "missing" and mb.lookups == []


async def test_wrong_durations_block_ready():
    # Same titles but the release's tracks are all ~3x longer: a different recording/edition.
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS, length=600_000)})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status != "ready" and any("lengths" in p for p in v.candidates[0]["problems"])


async def test_wrong_artist_blocks_ready():
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS, artist="Somebody Else Entirely")})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status != "ready" and any("artist differs" in p for p in v.candidates[0]["problems"])


async def test_identical_editions_need_a_human_unless_the_year_decides():
    editions = {"a": release("a", "Great Album", TRACKS, date="2019-01-01"), "b": release("b", "Great Album", TRACKS, date="2020-05-01"),
                "c": release("c", "Great Album", TRACKS, date="2020-09-09")}
    hits = [hit("a", 3), hit("b", 3), hit("c", 3)]
    two_in_year = await evaluate_album(FakeMB(hits, editions), local_album(TRACKS, date="2020"))
    assert two_in_year.status == "review" and "share this tracklist" in two_in_year.reasons[0]
    no_year = await evaluate_album(FakeMB(hits, editions), local_album(TRACKS, date=""))
    assert no_year.status == "review"
    one_in_year = await evaluate_album(FakeMB(hits, editions), local_album(TRACKS, date="2019"))
    assert one_in_year.status == "ready" and one_in_year.release_mbid == "a"


async def test_missing_tags_are_missing_without_hitting_musicbrainz():
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS)})
    assert (await evaluate_album(mb, local_album(TRACKS, title="", artist=""))).status == "missing"
    assert mb.searches == []


async def test_stale_tagged_id_is_ignored_and_a_good_tag_is_trusted():
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS)})
    v = await evaluate_album(mb, local_album(TRACKS, tagged_id="gone-id"))
    assert v.status == "ready" and v.release_mbid == "r1"
    # No search hit at all, but the files carry an ID that exists and matches.
    mb2 = FakeMB([], {"r9": release("r9", "Great Album", TRACKS)})
    v2 = await evaluate_album(mb2, local_album(TRACKS, tagged_id="r9"))
    assert v2.status == "ready" and v2.release_mbid == "r9"


async def test_edition_decorations_in_the_title_are_retried_without_them():
    hits = lambda title: [hit("r1", 3)] if "(" not in title else []
    mb = FakeMB(hits, {"r1": release("r1", "Great Album", TRACKS)})
    v = await evaluate_album(mb, local_album(TRACKS, title="Great Album (Special Edition) [FLAC]"))
    assert [q[0] for q in mb.searches] == ["Great Album (Special Edition) [FLAC]", "Great Album"]
    assert v.status == "ready"


async def test_transient_musicbrainz_errors_propagate_so_the_album_stays_pending():
    class Boom(FakeMB):
        async def search_releases_raw(self, *a, **k):
            raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        await evaluate_album(Boom([], {}), local_album(TRACKS))


def test_clean_title():
    assert clean_title("Let Go (Special Edition) [FLAC 24bit]") == "Let Go"
    assert clean_title("(Untitled)") == "(Untitled)"


# ---------------------------------------------------------------- release-group path


def group(gid, score=100):
    return {"id": gid, "score": score}


async def test_correct_release_hiding_in_a_second_release_group_is_found():
    # The real-world "Creep" case: a single group full of near-identical 4-track editions that do NOT
    # match, and an EP group holding the one that does. Sampling a few editions misses it.
    ep_tracks = ["Creep", "Lurgee", "Inside My Head", "Million Dollar Question"]
    single = {f"s{i}": release(f"s{i}", "Creep", ["Creep (album version)", "Yes I Am", "Blow Out", "Inside My Head"][: 4]) for i in range(8)}
    group_releases = {"g-single": list(single.values()), "g-ep": [release("ep-1", "Creep", ep_tracks, date="1992-09-21", length=200_000)]}
    mb = FakeMB([], {}, groups=[group("g-single"), group("g-ep")], group_releases=group_releases)
    v = await evaluate_album(mb, local_album(ep_tracks, title="Creep", date="1992"))
    assert v.status == "ready" and v.release_mbid == "ep-1"
    assert mb.browses == ["g-single", "g-ep"] and mb.searches == []  # one browse per group, no per-release lookups, no fallback


async def test_release_group_path_judges_every_edition_locally_with_one_request_per_group():
    editions = [release(f"e{i}", "Great Album", TRACKS, date=f"{2000 + i}-01-01") for i in range(10)]
    mb = FakeMB([], {}, groups=[group("g1")], group_releases={"g1": editions})
    v = await evaluate_album(mb, local_album(TRACKS, date="2004"))
    assert v.status == "ready" and v.release_mbid == "e4"  # the year picks among 10 identical editions
    assert mb.browses == ["g1"] and mb.lookups == []
    assert len(v.candidates) <= 6  # stored candidates are capped


async def test_falls_back_to_release_search_only_when_groups_yield_nothing_plausible():
    mb = FakeMB([hit("r1", 3)], {"r1": release("r1", "Great Album", TRACKS)}, groups=[group("g1")],
                group_releases={"g1": [release("x", "Great Album", ["Foo", "Bar", "Baz"])]})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status == "ready" and v.release_mbid == "r1" and mb.lookups == ["r1"]


async def test_a_failing_group_is_skipped_not_fatal():
    mb = FakeMB([], {}, groups=[group("gone"), group("g2")], group_releases={"g2": [release("r2", "Great Album", TRACKS)]})
    assert (await evaluate_album(mb, local_album(TRACKS))).release_mbid == "r2"


async def test_a_release_appearing_via_tag_and_via_group_is_judged_once():
    r = release("r1", "Great Album", TRACKS)
    mb = FakeMB([], {"r1": r}, groups=[group("g1")], group_releases={"g1": [r]})
    v = await evaluate_album(mb, local_album(TRACKS, tagged_id="r1"))
    assert v.status == "ready" and len(v.candidates) == 1


async def test_extra_words_in_the_artist_or_title_no_longer_count_as_a_match():
    # An identical tracklist credited to a different, longer artist/title must not be "ready".
    wrong_artist = release("a", "Great Album", TRACKS, artist="Artist One and The Backing Band Of Strangers")
    v = await evaluate_album(FakeMB([], {}, groups=[group("g")], group_releases={"g": [wrong_artist]}), local_album(TRACKS))
    assert v.status != "ready" and any("artist differs" in p for p in v.candidates[0]["problems"])
    wrong_title = release("t", "Great Album Live At The Apollo Theatre", TRACKS)
    v2 = await evaluate_album(FakeMB([], {}, groups=[group("g")], group_releases={"g": [wrong_title]}), local_album(TRACKS))
    assert v2.status != "ready"


# ---------------------------------------------------------------- regressions found on the real library


async def test_a_reissue_never_wins_just_because_the_original_has_a_decorated_title():
    # "Transmission" (2 tracks, no year in the tags): the 1979 original is titled "Transmission / Novelty"
    # and the 2020 reissue "Transmission". Both match the tracks exactly, so a human must choose.
    tracks = ["Transmission", "Novelty"]
    releases = [release("orig", "Transmission / Novelty", tracks, date="1979-10"), release("reissue", "Transmission", tracks, date="2020")]
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": releases})
    v = await evaluate_album(mb, local_album(tracks, title="Transmission", date=""))
    assert v.status == "review" and "share this tracklist" in v.reasons[0]
    assert {c["mbid"] for c in v.candidates} == {"orig", "reissue"}


async def test_exact_tracks_under_a_different_title_are_review_not_missing():
    # Never send something to the "create it" queue when an exact tracklist exists on MusicBrainz.
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": [release("r", "Completely Different Name", TRACKS)]})
    v = await evaluate_album(mb, local_album(TRACKS))
    assert v.status == "review" and v.release_mbid == "r" and "tracks match this release exactly" in v.reasons[0]
    assert v.candidates[0]["track_exact"] is True and v.candidates[0]["confident"] is False


async def test_coverage_outranks_a_perfect_partial_match():
    full_titles = [f"Song {i}" for i in range(1, 11)]
    near = release("near", "Great Album", full_titles[:9] + ["Something Else Entirely"])   # 9 of 10 files, 1 odd track
    tiny = release("tiny", "Great Album", full_titles[:4])                                  # 4 files matched perfectly
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": [tiny, near]})
    v = await evaluate_album(mb, local_album(full_titles))
    assert v.status == "review" and v.release_mbid == "near"


async def test_strong_tracklist_overlap_is_review_even_when_the_title_differs():
    tracks = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta"]
    live = release("live", "Warsaw: Live American Radio Broadcast", tracks)
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": [live]})
    v = await evaluate_album(mb, local_album(tracks, title="Warsaw (Live)"))
    assert v.status in ("review",) and v.release_mbid == "live"


async def test_a_subset_of_a_bigger_release_is_missing_not_review():
    # One local track that also appears on a 4-track release is not that release.
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": [release("big", "Ceremony / In a Lonely Place", ["Ceremony", "In a Lonely Place", "X", "Y"], artist="New Order / Joy Division")]})
    v = await evaluate_album(mb, local_album(["Ceremony"], title="Ceremony", artist="Joy Division"))
    assert v.status == "missing"


async def test_ampersand_apostrophes_and_punctuation_do_not_count_as_different_names():
    tracks = ["Don't Look Back", "Rock & Roll"]
    mb = FakeMB([], {}, groups=[group("g")], group_releases={"g": [release("r", "Heart and Soul", ["Dont Look Back", "Rock and Roll"])]})
    v = await evaluate_album(mb, local_album(tracks, title="Heart & Soul"))
    assert v.status == "ready", v.reasons

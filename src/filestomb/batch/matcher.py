"""Decide whether an album folder already exists on MusicBrainz, and how sure we are.

The bar for "ready" (eligible for unattended tagging and moving) is
deliberately high: a *specific release* must account for every local file and
every track on the release, with titles, durations and artist all agreeing.
Anything short of that is "review" (a human decides) or "missing"
(not on MusicBrainz as far as we can tell). Every verdict carries its reasons.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Protocol

import httpx
from rapidfuzz import fuzz

from ..models import Album
from ..releasetags import Plan, ReleaseInfo, match_tracks, parse_release

# --- thresholds (see module docstring) -------------------------------------
MIN_SEARCH_SCORE = 55          # ignore search hits weaker than this
MAX_LOOKUPS = 4                # releases fetched one by one (fallback path) per album
MAX_RELEASE_GROUPS = 3         # release groups whose every edition is browsed per album
MIN_GROUP_SCORE = 60
KEEP_CANDIDATES = 6            # candidates stored per album
DURATION_TOLERANCE_MS = 5000   # a track's length may differ from the release by this much
MIN_MEAN_TITLE = 90            # average title similarity over all matched tracks
MIN_DURATION_AGREEMENT = 0.9   # fraction of tracks whose lengths agree (when known)
MIN_ARTIST_SIM = 85
MIN_ALBUM_TITLE_SIM = 85
REVIEW_MIN_COVERAGE = 0.6      # below this a candidate isn't even worth a human's time
REVIEW_MIN_TITLE_SIM = 70


class MBLike(Protocol):
    async def search_releases_raw(self, title: str, artist: str, limit: int = 10) -> list[dict]: ...
    async def search_release_groups_raw(self, title: str, artist: str, limit: int = 5) -> list[dict]: ...
    async def browse_release_group_releases(self, release_group_mbid: str, limit: int = 100) -> list[dict]: ...
    async def lookup_release(self, mbid: str) -> dict: ...


@dataclass
class CandidateEval:
    mbid: str
    title: str
    artist: str
    date: str
    country: str
    status: str
    track_count: int
    search_score: float
    coverage_local: float
    coverage_release: float
    mean_title: float
    duration_agreement: float | None
    artist_sim: float
    title_sim: float
    year_match: bool | None
    track_exact: bool  # every file <-> every track, titles and lengths agree (names may still differ)
    confident: bool
    problems: list[str] = field(default_factory=list)
    rank: float = 0.0


@dataclass
class Verdict:
    status: str  # "ready" | "review" | "missing"
    release_mbid: str | None
    confidence: float
    reasons: list[str]
    candidates: list[dict]


def _norm(text: str) -> str:
    folded = (text or "").casefold().replace("&", " and ").replace("\u2019", "'")
    return re.sub(r"[^\w]+", " ", folded.replace("'", "")).strip()


def clean_title(text: str) -> str:
    """Drop edition/format decorations: "Let Go (Special Edition) [FLAC]" -> "Let Go"."""
    stripped = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text or "")
    return re.sub(r"\s+", " ", stripped).strip() or (text or "").strip()


def _sim(a: str, b: str) -> float:
    """Name similarity that, unlike a set comparison, penalises extra words:
    "Warsaw" vs "Warsaw Departament" is not a match."""
    return float(fuzz.token_sort_ratio(_norm(a), _norm(b)))


def _year(date: str | None) -> str | None:
    match = re.match(r"\s*(\d{4})", date or "")
    return match.group(1) if match else None


def evaluate_candidate(album: Album, release: ReleaseInfo, plan: Plan, search_score: float, raw: dict | None = None) -> CandidateEval:
    pairs = [p for p in plan.pairs if p.release_track]
    local_count = max(len(plan.pairs), 1)
    release_count = max(len(release.tracks), 1)
    coverage_local = len(pairs) / local_count
    coverage_release = len(pairs) / release_count
    mean_title = sum(p.score for p in pairs) / len(pairs) if pairs else 0.0

    known = [(p.track.length_ms, p.release_track.length_ms) for p in pairs if p.track.length_ms and p.release_track.length_ms]
    duration_agreement = None
    if len(known) >= max(1, round(0.7 * len(pairs))):
        duration_agreement = sum(1 for a, b in known if abs(a - b) <= DURATION_TOLERANCE_MS) / len(known)

    artist_sim = _sim(album.artist, release.artist)
    title_sim = max(_sim(album.title, release.title), _sim(clean_title(album.title), clean_title(release.title)))
    local_year, release_year = _year(album.date), _year(release.date)
    year_match = (local_year == release_year) if (local_year and release_year) else None

    problems: list[str] = []
    if coverage_local < 1:
        problems.append(f"{len(plan.pairs) - len(pairs)} local file(s) match no track on this release")
    if coverage_release < 1:
        problems.append(f"{len(plan.unmatched_release_tracks)} release track(s) have no local file")
    if pairs and mean_title < MIN_MEAN_TITLE:
        problems.append(f"track titles only {mean_title:.0f}% similar on average")
    if duration_agreement is not None and duration_agreement < MIN_DURATION_AGREEMENT:
        problems.append(f"only {duration_agreement * 100:.0f}% of track lengths agree")
    if duration_agreement is None and pairs and mean_title < 95:
        problems.append("track lengths unavailable to confirm the match")
    if artist_sim < MIN_ARTIST_SIM:
        problems.append(f"artist differs ({album.artist!r} vs {release.artist!r})")
    if title_sim < MIN_ALBUM_TITLE_SIM:
        problems.append(f"album title differs ({album.title!r} vs {release.title!r})")

    track_problems = [p for p in problems if not p.startswith(("artist differs", "album title differs"))]
    track_exact = not track_problems and bool(pairs)
    confident = not problems
    # Coverage multiplies everything: a release that accounts for 34 of 35 files must
    # outrank one that matches 8 files perfectly.
    quality = coverage_local * (0.5 + 0.5 * coverage_release)
    rank = quality * (
        0.35 * mean_title
        + 0.25 * (duration_agreement if duration_agreement is not None else 0.5) * 100
        + 0.15 * title_sim
        + 0.10 * artist_sim
        + 0.15 * (100 if year_match else 50 if year_match is None else 0)
    )
    raw = raw or {}
    return CandidateEval(
        mbid=release.mbid,
        title=release.title,
        artist=release.artist,
        date=release.date,
        country=raw.get("country", ""),
        status=raw.get("status", ""),
        track_count=len(release.tracks),
        search_score=search_score,
        coverage_local=round(coverage_local, 3),
        coverage_release=round(coverage_release, 3),
        mean_title=round(mean_title, 1),
        duration_agreement=None if duration_agreement is None else round(duration_agreement, 3),
        artist_sim=round(artist_sim, 1),
        title_sim=round(title_sim, 1),
        year_match=year_match,
        track_exact=track_exact,
        confident=confident,
        problems=problems,
        rank=round(rank, 1),
    )


async def _search(client: MBLike, album: Album) -> list[dict]:
    queries = [(album.title, album.artist)]
    cleaned = clean_title(album.title)
    if cleaned != album.title:
        queries.append((cleaned, album.artist))
    seen: dict[str, dict] = {}
    for title, artist in queries:
        for hit in await client.search_releases_raw(title, artist, limit=10):
            if float(hit.get("score", 0)) >= MIN_SEARCH_SCORE:
                seen.setdefault(hit["id"], hit)
        if seen:
            break
    return sorted(seen.values(), key=lambda h: -float(h.get("score", 0)))


def _choose_lookups(hits: list[dict], local_count: int, tagged_id: str | None) -> list[dict]:
    """Prefer releases whose track count equals ours; that is cheap to check and
    avoids fetching dozens of editions."""
    exact = [h for h in hits if h.get("track-count") == local_count]
    near = sorted((h for h in hits if h.get("track-count") != local_count),
                  key=lambda h: abs((h.get("track-count") or 0) - local_count))
    chosen = (exact[:MAX_LOOKUPS]) or near[:2]
    if tagged_id and not any(h["id"] == tagged_id for h in chosen):
        chosen = [{"id": tagged_id, "score": 100}, *chosen][:MAX_LOOKUPS]
    return chosen


def _evaluate_raw(album: Album, raw: dict, search_score: float) -> CandidateEval:
    release = parse_release(raw)
    plan = match_tracks(album.tracks, release)
    return evaluate_candidate(album, release, plan, search_score, raw)


async def _search_groups(client: MBLike, album: Album) -> list[dict]:
    queries = [(album.title, album.artist)]
    cleaned = clean_title(album.title)
    if cleaned != album.title:
        queries.append((cleaned, album.artist))
    seen: dict[str, dict] = {}
    for title, artist in queries:
        for group in await client.search_release_groups_raw(title, artist, limit=6):
            if float(group.get("score", 0)) >= MIN_GROUP_SCORE:
                seen.setdefault(group["id"], group)
        if seen:
            break
    return sorted(seen.values(), key=lambda g: -float(g.get("score", 0)))[:MAX_RELEASE_GROUPS]


def _viable(evals: list[CandidateEval]) -> bool:
    return any(e.coverage_local >= REVIEW_MIN_COVERAGE and e.title_sim >= REVIEW_MIN_TITLE_SIM for e in evals)


async def evaluate_album(client: MBLike, album: Album) -> Verdict:
    """Match one scanned album against MusicBrainz and triage it.

    Candidates come from (1) a release ID already in the tags, (2) every edition
    of the best-matching release groups, fetched in one browse request each, and
    only if those turn up nothing plausible, (3) individual releases from a
    plain release search. Fetching whole release groups matters: a title like
    "Creep" has dozens of near-identical editions across several groups, and
    sampling a few of them misses the right one."""
    if not album.title.strip() or not album.artist.strip():
        return Verdict("missing", None, 0.0, ["The files have no usable album/artist tags to search with."], [])

    by_id: dict[str, CandidateEval] = {}

    def add(candidate: CandidateEval) -> None:
        by_id.setdefault(candidate.mbid, candidate)

    tagged = {t.musicbrainz_release_id for t in album.tracks if t.musicbrainz_release_id}
    tagged_id = next(iter(tagged)) if len(tagged) == 1 else None
    if tagged_id:
        try:
            add(_evaluate_raw(album, await client.lookup_release(tagged_id), 100.0))
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404:  # a stale tagged id is simply ignored
                raise

    for group in await _search_groups(client, album):
        try:
            releases = await client.browse_release_group_releases(group["id"])
        except httpx.HTTPStatusError as error:
            if error.response.status_code in (400, 404):
                continue
            raise
        for raw in releases:
            add(_evaluate_raw(album, raw, float(group.get("score", 0))))

    if not _viable(list(by_id.values())):
        hits = await _search(client, album)
        for hit in _choose_lookups(hits, len(album.tracks), None):
            if hit["id"] in by_id:
                continue
            try:
                add(_evaluate_raw(album, await client.lookup_release(hit["id"]), float(hit.get("score", 0))))
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    raise

    if not by_id:
        return Verdict("missing", None, 0.0, ["No release with this title and artist was found on MusicBrainz."], [])

    evals = sorted(by_id.values(), key=lambda e: -e.rank)
    exact = [e for e in evals if e.track_exact]
    kept = exact[:KEEP_CANDIDATES] + [e for e in evals if not e.track_exact][: max(0, KEEP_CANDIDATES - len(exact))]
    candidates = [asdict(e) for e in sorted(kept, key=lambda e: -e.rank)]

    if len(exact) == 1:
        e = exact[0]
        if e.confident:
            return Verdict("ready", e.mbid, e.rank, ["Every file matches a track on this release and every track has a file."], candidates)
        names = [p for p in e.problems if p.startswith(("artist differs", "album title differs"))]
        return Verdict("review", e.mbid, e.rank,
                       ["The tracks match this release exactly, but " + "; ".join(names) + ". Confirm it's the right one."], candidates)

    if len(exact) > 1:
        # Several releases share this tracklist. Names that differ are not a reason to drop one:
        # that is how a reissue ends up chosen over the original. Only the tagged year may decide.
        local_year = _year(album.date)
        by_year = [e for e in exact if local_year and _year(e.date) == local_year]
        if len(by_year) == 1 and by_year[0].confident:
            e = by_year[0]
            return Verdict("ready", e.mbid, e.rank,
                           [f"{len(exact)} releases share this tracklist; picked the one released in {local_year} to match the tags."], candidates)
        return Verdict("review", exact[0].mbid, exact[0].rank,
                       [f"{len(exact)} releases on MusicBrainz share this tracklist. Pick the one you want."], candidates)

    best = evals[0]
    strong_tracks = best.mean_title >= MIN_MEAN_TITLE and best.coverage_release >= REVIEW_MIN_COVERAGE
    if best.coverage_local >= REVIEW_MIN_COVERAGE and (best.title_sim >= REVIEW_MIN_TITLE_SIM or strong_tracks):
        return Verdict("review", best.mbid, best.rank, ["Closest release isn't an exact match: " + "; ".join(best.problems) + "."], candidates)
    return Verdict("missing", None, 0.0, ["No release on MusicBrainz matches these tracks."], candidates)

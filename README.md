# FilesToMB

**A beautiful, keyboard-driven TUI for turning your local music collection into MusicBrainz edits.**

> Status: early development. The core flow — browse, read tags, match against MusicBrainz, review, and open seeded edit forms — is implemented and tested; see [Roadmap](#roadmap) for what's next.

---

## The problem

You have a shelf (or a drive) full of albums with pristine, hand-checked metadata — correct artist names, correct release titles, correct track lists, correct dates, sometimes even correct barcodes and label info. MusicBrainz just doesn't know about them yet.

Maybe the release doesn't exist. Maybe the release *group* doesn't exist. Maybe the artist isn't in MusicBrainz at all. Usually it's some combination of all three, buried under several trips through different "Add" forms on the website.

FilesToMB exists to close that gap: point it at a folder, and let it figure out what's missing on MusicBrainz and submit the edits to create it — artist, label, release group, release, and all — while keeping you in control of every field before anything goes out the door.

## How it works

1. **Browse** — launch the TUI and navigate to a directory of albums (or a single album) using the file browser.
2. **Read** — FilesToMB reads the embedded tags from the audio files in that directory to build a picture of the release: artist(s), album/release title, track list, dates, disc/media info, label, catalog number, barcode, and anything else usable.
3. **Resolve** — for each entity involved (artist, label, release group, release), FilesToMB searches the MusicBrainz API to see what already exists. Confident matches are linked automatically; ambiguous or missing entities are flagged for your attention.
4. **Review & edit** — everything is presented in the TUI before submission. Fix a mis-tagged field, pick the right match out of several candidates, or fill in something your tags didn't have. Nothing goes to MusicBrainz without passing through this screen.
5. **Submit** — for whatever's missing, FilesToMB opens a pre-filled ("seeded") MusicBrainz edit form in your browser, in the right dependency order (label and artist before release group, release group before release), so you just review and click submit while logged in yourself.

The result: albums that exist perfectly on your disk end up existing perfectly on MusicBrainz too, with a fraction of the manual form-filling.

A deliberate note on that last step: MusicBrainz doesn't expose a public write API for creating artists, labels, release groups, or releases — new entities are only ever created through the ordinary edit forms, submitted by a logged-in human. FilesToMB embraces that rather than fighting it, using MusicBrainz's own documented [seeding mechanism](https://musicbrainz.org/doc/Development/Seeding) to pre-fill those forms instead of pretending there's a one-click API to create them.

## Features

- **Fast, keyboard-only TUI** — no mouse required, built for people who live in a terminal.
- **Directory-first workflow** — point at a folder, not a spreadsheet.
- **Entity-aware matching** — artists, labels, release groups, and releases are resolved independently, so a partial match (e.g. artist exists, release doesn't) is handled correctly instead of creating duplicates.
- **In-TUI editing** — correct or complete metadata before it's submitted, without leaving the app.
- **Review-before-submit** — a clear status (matched / ambiguous / missing) for every entity, before anything opens in a browser.
- **Batch-friendly** — work through a backlog of albums without re-navigating each time.
- **No credentials to protect** — searching MusicBrainz needs no login at all; creating things happens in your own already-authenticated browser session, so there's nothing sensitive in `.env`.

## Tech stack

| Concern | Choice |
|---|---|
| TUI framework | [Textual](https://github.com/Textualize/textual) — modern, styleable, keyboard-first Python TUI |
| Audio tag reading | [Mutagen](https://github.com/quodlibet/mutagen) |
| MusicBrainz search | Async `httpx` client against `musicbrainz.org/ws/2`, rate-limited to MusicBrainz's requested 1 req/sec |
| MusicBrainz creation | Browser-opened, pre-filled ("seeded") edit forms — see the note above |
| Config | `python-dotenv` for local `.env` loading |
| Packaging | `hatchling`, installable as a CLI entry point (`filestomb`) |

## Getting started

```bash
git clone git@github.com:WB2024/FilesToMB.git
cd FilesToMB
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env with a real contact email — MusicBrainz requires this on every request
```

## Configuration

Searching MusicBrainz needs no authentication — just a descriptive, contactable `User-Agent`, which MusicBrainz requires on every request:

```env
# .env
MB_APP_NAME=FilesToMB
MB_APP_VERSION=0.1.0
MB_CONTACT=you@example.com
```

`.env` is git-ignored by default. There's no API key to leak, since creating entities happens through your browser, logged into MusicBrainz as yourself.

## Usage

```bash
filestomb /path/to/music/library
```

This opens the TUI with the directory browser focused on the given path (or your home directory if omitted).

- Navigate the tree and press **Enter** on an album folder to scan its tags.
- On the review screen, edit any field, press **m** to check MusicBrainz, then use the option lists to pick between ambiguous candidates.
- Press **c** to continue — for anything still missing, a button opens the matching MusicBrainz "create" form in your browser, pre-filled and ready to submit.
- **Escape** goes back a screen; **q** quits.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests generate real (silent) audio fixtures with `ffmpeg` to exercise actual tag reading, mock MusicBrainz's HTTP API with `respx`, and drive the real Textual app headlessly through Textual's own test harness — not just unit tests of isolated functions.

## Roadmap

- [x] Directory browser + tag reading
- [x] MusicBrainz search/match for artist, label, release group, release
- [x] Review screen with in-TUI editing and match selection
- [x] Seeded-form submission (open missing entities' create forms, in dependency order)
- [ ] Per-track editing (track titles/numbers) in the review screen
- [ ] Batch mode across multiple albums in one session
- [ ] Remember recently-used directories

## Contributing

This is currently a personal tool being built in the open. Issues and ideas are welcome once the initial version is up.

## License

MIT — see [LICENSE](LICENSE).

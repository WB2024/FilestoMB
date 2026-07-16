# FilesToMB

**A beautiful, keyboard-driven TUI for turning your local music collection into MusicBrainz edits.**

> Status: early development. This README describes the project as designed; the codebase is being built out from here.

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
5. **Submit** — FilesToMB creates whatever is missing, in the right order (artist and label before release group, release group before release), and submits it as edits under your MusicBrainz account.

The result: albums that exist perfectly on your disk end up existing perfectly on MusicBrainz too, with a fraction of the manual form-filling.

## Features

- **Fast, keyboard-only TUI** — no mouse required, built for people who live in a terminal.
- **Directory-first workflow** — point at a folder, not a spreadsheet.
- **Entity-aware matching** — artists, labels, release groups, and releases are resolved independently, so a partial match (e.g. artist exists, release doesn't) is handled correctly instead of creating duplicates.
- **In-TUI editing** — correct or complete metadata before it's submitted, without leaving the app.
- **Review-before-submit** — a clear diff/preview of exactly what will be created or changed.
- **Batch-friendly** — work through a backlog of albums without re-authenticating or re-navigating each time.
- **Bring your own credentials** — MusicBrainz API/OAuth credentials live in a local `.env` file, never in code or config committed to the repo.

## Tech stack (planned)

| Concern | Choice |
|---|---|
| TUI framework | [Textual](https://github.com/Textualize/textual) — modern, styleable, keyboard-first Python TUI |
| Audio tag reading | [Mutagen](https://github.com/quodlibet/mutagen) |
| MusicBrainz API | Direct HTTP against `musicbrainz.org/ws/2`, OAuth2 for authenticated edits |
| Config | `python-dotenv` for local `.env` credential loading |
| Packaging | Python, installable as a CLI entry point |

This may evolve as the project takes shape, but the TUI layer is settled: Textual is the right tool for a "beautiful, keyboard-driven" terminal experience in Python.

## Getting started

> Not yet published. Once the first working version lands, this section will cover installation via `pip`/`pipx`.

```bash
git clone https://github.com/<you>/FilesToMB.git
cd FilesToMB
# setup instructions coming soon
```

## Configuration

MusicBrainz authenticates edits via OAuth2 under your own account rather than a static API key — FilesToMB will guide you through obtaining these once, then stores them locally:

```env
# .env
MB_CLIENT_ID=your_musicbrainz_application_client_id
MB_CLIENT_SECRET=your_musicbrainz_application_client_secret
MB_APP_NAME=FilesToMB
MB_APP_VERSION=0.1.0
MB_CONTACT=you@example.com
```

`.env` is git-ignored by default — your credentials never leave your machine.

## Usage

```bash
filestomb /path/to/music/library
```

This opens the TUI with the file browser focused on the given path (or your home directory if omitted). From there, keyboard shortcuts drive everything: navigating the browser, inspecting a candidate album, reviewing matches, editing fields, and confirming submission.

## Roadmap

- [ ] Directory browser + tag reading
- [ ] MusicBrainz search/match for artist, label, release group, release
- [ ] Review/diff screen with in-TUI editing
- [ ] OAuth2 flow + `.env`-based credential storage
- [ ] Edit submission (create missing entities in dependency order)
- [ ] Batch mode across multiple albums

## Contributing

This is currently a personal tool being built in the open. Issues and ideas are welcome once the initial version is up.

## License

MIT — see [LICENSE](LICENSE).

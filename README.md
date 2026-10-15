<p align="center">
  <img src="logo.png" alt="FilesToMB logo: a bandage-wrapped mummy clutching a music file, framed in a hieroglyph-carved tomb archway" width="280">
</p>

<h1 align="center">FilesToMB</h1>

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

A deliberate note on that last step: MusicBrainz doesn't expose a public write API for creating artists, labels, release groups, or releases — new entities are only ever created through the ordinary edit forms, submitted by a logged-in human. FilesToMB embraces that rather than fighting it, using MusicBrainz's own documented [seeding mechanism](https://musicbrainz.org/doc/Development/Seeding) to pre-fill those forms instead of pretending there's a one-click API to create them. Every seed field name (and, for release groups, the numeric type IDs) is verified against MusicBrainz's own server source rather than guessed, since the docs turned out to describe an older format in places.

Cover art works the same way, one level further: the Cover Art Archive has *no* upload API at all, public or otherwise — even MusicBrainz's own upload page requires a real logged-in browser session (not OAuth2) and then talks to the Internet Archive behind the scenes. So FilesToMB does what it honestly can: find the right image locally (a `cover.jpg`/`folder.png`-style file, or whatever's embedded in the tags), then, once a release has a MusicBrainz ID, open the real upload page and tell you exactly which file to drag in.

## Features

- **Fast, keyboard-only TUI** — no mouse required, built for people who live in a terminal.
- **Directory-first workflow** — point at a folder, not a spreadsheet.
- **Entity-aware matching** — artists, labels, release groups, and releases are resolved independently, so a partial match (e.g. artist exists, release doesn't) is handled correctly instead of creating duplicates.
- **In-TUI editing** — correct or complete metadata before it's submitted, without leaving the app.
- **Review-before-submit** — a clear status (matched / ambiguous / missing) for every entity, before anything opens in a browser.
- **Batch-friendly** — work through a backlog of albums without re-navigating each time.
- **No credentials needed for the core flow** — searching MusicBrainz and opening seeded "create" forms need no login at all.
- **Optional MusicBrainz login** — log in with OAuth2 (press `l`) to use the handful of actions MusicBrainz's API *does* support as real authenticated writes, like filing a resolved release into one of your personal collections.
- **Cover art assistance** — finds a standalone cover file or extracts what's embedded in the tags, then opens MusicBrainz's real upload page with the exact file called out for you to drag in.
- **Remembers where you left off** — the last directory you browsed to persists between runs, instead of always starting at your home directory.

## Tech stack

| Concern | Choice |
|---|---|
| TUI framework | [Textual](https://github.com/Textualize/textual) — modern, styleable, keyboard-first Python TUI |
| Audio tag reading | [Mutagen](https://github.com/quodlibet/mutagen) |
| MusicBrainz search | Async `httpx` client against `musicbrainz.org/ws/2`, rate-limited to MusicBrainz's requested 1 req/sec |
| MusicBrainz creation | Browser-opened, pre-filled ("seeded") edit forms — see the note above |
| MusicBrainz login | OAuth2 authorization-code flow for an "Installed application", tokens cached locally in `~/.config/filestomb/token.json` |
| Config | `python-dotenv` for local `.env` loading |
| Packaging | `hatchling`, installable as a CLI entry point (`filestomb`) |

## Getting started

For everyday use, install it with [pipx](https://pypa.github.io/pipx/) so a `filestomb` command is available from any directory, without activating a venv:

```bash
git clone git@github.com:WB2024/FilesToMB.git
cd FilesToMB
pipx install -e .
cp .env.example .env
# edit .env with a real contact email — MusicBrainz requires this on every request
filestomb
```

Being an editable (`-e`) install, it picks up any code changes immediately — no reinstalling needed.

For development, or if you'd rather not install anything globally:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python3 main.py   # or: filestomb, once the venv is activated
```

## Web UI (Docker)

The same engine is available as a self-hosted web app: browse your library, review matches, edit tracks, and open seeded MusicBrainz forms from any browser on your network.

```bash
cp .env.example .env     # set MB_CONTACT, PUBLIC_URL, optionally the OAuth client
docker compose up -d     # serves on :8097
```

`compose.yaml` mounts the music library **read-only** at `/music` and keeps the OAuth token and last-browsed folder in `./config`. Image: `wb20244/filestomb`.

**Optional userscript.** The header's *Userscript* button installs a Tampermonkey/Violentmonkey script served by your own instance. On MusicBrainz's add-cover-art page it attaches the album's cover and ticks "Front"; on any artist/label/release-group/release page, *Use in FilesToMB* sends the ID back to the app so you don't have to re-check. Form fields themselves are still pre-filled by MusicBrainz's own seeding, and the script never submits an edit.

Run it without Docker with `pip install -e ".[web]"` then `MUSIC_ROOT=/path/to/music filestomb-web`.

## Configuration

Searching MusicBrainz needs no authentication — just a descriptive, contactable `User-Agent`, which MusicBrainz requires on every request:

```env
# .env
MB_APP_NAME=FilesToMB
MB_APP_VERSION=0.1.0
MB_CONTACT=you@example.com
```

`.env` is git-ignored by default. There's no API key to leak for the core flow, since creating entities happens through your browser, logged into MusicBrainz as yourself.

Logging in (for collections, ratings, tags, etc.) is optional, and needs an OAuth2 "Installed application" registered at [musicbrainz.org/account/applications](https://musicbrainz.org/account/applications):

```env
# .env
MB_OAUTH_CLIENT_ID=your_client_id
MB_OAUTH_CLIENT_SECRET=your_client_secret
```

**Important:** when registering the application, set its redirect URI to exactly `urn:ietf:wg:oauth:2.0:oob` — that's the out-of-band redirect MusicBrainz reserves for apps with no callback server (like this one), where the authorization code is shown on a page for you to copy rather than redirected anywhere. If the registered redirect URI doesn't match, MusicBrainz will refuse the login.

## Usage

```bash
filestomb /path/to/music/library
```

This opens the TUI with the directory browser focused on the given path (or the last directory you browsed to, or your home directory the first time).

- Navigate the tree and press **Enter** on an album folder to scan its tags. Press **u** to go up a directory, or **g** to jump straight to a typed path.
- On the review screen, edit any field, press **m** to check MusicBrainz, then use the option lists to pick between ambiguous candidates.
- Press **c** to continue — for anything still missing, a button opens the matching MusicBrainz "create" form in your browser (release group and release creation first ask for the extra fields MusicBrainz can seed: type, disambiguation, status, language, and so on).
- Press **l** anywhere to log in: it opens MusicBrainz's authorization page in your browser, and you paste the code it shows you back into the app. A status line on every screen shows whether you're logged in.
- On the submit screen, once a release has a MusicBrainz ID: press **a** to file it into one of your personal collections (requires login), or **c** to open the cover art upload page — if FilesToMB found a local image, it'll tell you exactly which file to drag in and reveal it in your file manager.
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
- [x] OAuth2 login and adding resolved releases to a personal collection
- [x] Remember recently-used directories, with Up/jump-to-path navigation
- [x] Cover art detection and upload-page assistance
- [x] Web UI (Docker) with per-track editing and a companion userscript
- [ ] Per-track editing in the TUI
- [ ] Batch mode across multiple albums in one session

## Contributing

This is currently a personal tool being built in the open. Issues and ideas are welcome once the initial version is up.

## License

MIT — see [LICENSE](LICENSE).

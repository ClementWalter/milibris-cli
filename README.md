# milibris-cli

**Visibility: public.**

Read any **miLibris** digital kiosk (liseuse / e-paper reader) from the
terminal, as the logged-in subscriber.

miLibris hosts the digital edition of many titles. Each publisher gets its own
host (`digital.<publisher>.fr` and friends), but they all run the same two
pieces:

1. a server-rendered **kiosk** — catalogue, issue pages, `/library`, search —
   whose only credential is an Express session cookie named
   `<name>WebKioskSessionKey`;
2. the shared **HTML5 reader**, which pulls a `material.json` manifest, page
   images and per-article JSON from `content.milibris.com` under a ~30-minute
   ticket JWT minted by the kiosk.

So this CLI is host-agnostic: it discovers kiosks by scanning the local browser
cookie stores, then speaks both protocols.

## Install

A single [PEP 723](https://peps.python.org/pep-0723/) `uv` script — dependencies
resolve on first run, nothing to install:

```bash
git clone https://github.com/ClementWalter/milibris-cli.git
ln -sfn "$PWD/milibris-cli/bin/milibris" ~/.local/bin/milibris
```

Requires [uv](https://docs.astral.sh/uv/) and macOS (the cookie decryption uses
the system keychain).

The symlink points at this checkout, so a `git pull` or an uncommitted edit
takes effect immediately.

## Authentication

Nothing to paste. The CLI decrypts the local Chromium cookie store (Chrome,
Arc, Brave, Edge) with the browser's macOS keychain key and reuses the kiosk
session cookie. Sign into the kiosk in the browser once:

```bash
milibris kiosks     # → digital.franc-tireur.fr  chrome  franctireurWebKioskSessionKey
```

The kiosk is picked from `--host`, then `$MILIBRIS_HOST`, then
`~/.config/milibris-cli/config.json`, then the only kiosk you are logged into.

## Usage

```bash
milibris kiosks                              # kiosks your browsers know
milibris whoami                              # is the session still valid
milibris titles
milibris issues -n 20                        # newest first
milibris issue n249-2026 --json
milibris toc --json                          # id, page, rubric, words, abstract
milibris read <article-id> --issue n249-2026 # Markdown to stdout
milibris pdf                                 # readable PDF, typeset from the text
milibris pdf --facsimile                     # the page scans instead
milibris dump -o ./out                       # pages + both PDFs + Markdown
milibris search "ukraine" --issue n250-2026 --json
milibris material                            # the raw decrypted manifest
milibris set-host digital.example.fr
```

An issue is named by `latest` (the default), a slug (`n250-2026`), a
`title/version/slug` path, a mid UUID, or a full kiosk/reader URL. An unknown
slug is an error, never a silent fallback to the latest issue.

`dump` writes to `~/Downloads/milibris/<title>/<date>/`:

```
pages/page-NNN.jpg              HD stitched page renders (--ld for the small ones)
<title>-<date>-facsimile.pdf    the page renders assembled
<title>-<date>-texte.pdf        readable PDF typeset from the article text
pNNN-<slug>.md                  one Markdown file per article, frontmatter included
resources/<mid>.jpg             article images, saved so the files outlive the ticket
```

## Claude Desktop extension

`mcpb.json` customizes the extension `mcp-bridge pack milibris-cli` builds, so
someone without a terminal can install it by double-click. Its setup steps:
sign in to the kiosk in Chrome, then ask Claude to list the kiosks and click
Always Allow on the keychain prompt. Files land in `~/Downloads/milibris/`.
Without WeasyPrint's native libs or a PDF binary on PATH, the readable PDF is
printed by the installed Chrome running headless.

## Resolution

The liseuse caps page rasters at about **1400×2050 pixels per printed sheet** and
exposes nothing larger: `hd` is the manifest maximum, the tiles measure exactly
that, and the kiosk has no PDF download. On a broadsheet, where one "page" is a
sheet carrying two newspaper pages, body text lands around 11px — legible at 1:1
on screen, mushy in print.

`milibris pdf` therefore typesets the article text into an A4 document instead:
sharp at any zoom, searchable, selectable, and roughly 15× smaller than the
facsimile. Use `--facsimile` when you want the printed layout rather than a
readable text.

## Notes on the protocol

- **Tickets** live ~30 minutes and are minted per issue from `/reader/<mid>`.
  Asset fetches re-mint once on a 401.
- **The manifest** is served either as plain JSON or as a CryptoJS-AES envelope
  keyed on `<request session id>_<local day>_<ticket>`, stretched through
  PBKDF2-SHA256 over a salt the reader bundle obfuscates. Both paths are
  implemented; the encrypted one is exercised by a round-trip test.
- **HD pages** are tilesets addressed `…/tile0CxR.jpeg` (column-major), stitched
  locally with Pillow. A 1×1 tileset is the image itself, and HD is the ceiling —
  see *Resolution* above.

## As a library

[franc-tireur-cli](https://github.com/ClementWalter/franc-tireur-cli) imports this module for the liseuse half of its work:

```python
from milibris_cli import Kiosk
issue = Kiosk("digital.franc-tireur.fr").resolve("latest")
issue.toc()
issue.page_image(issue.material["pages"][0], hd=True)
```

## Tests

```bash
uv run --script tests/test_milibris.py
```

55 tests over the pure layers — ref parsing, the manifest key derivation,
catalogue scraping and Markdown rendering. No network.

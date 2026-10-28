---
name: milibris-cli
description:
  "Read any miLibris digital kiosk (liseuse / e-paper reader) from the terminal
  with the bundled `milibris` command — the platform behind the digital editions
  of many French newspapers and magazines (digital.<publisher>.fr and friends).
  Use to list a kiosk's titles and issues, print an issue's table of contents,
  render one article as Markdown, build a readable PDF of a whole issue, archive
  an issue (page JPEGs + PDFs + per-article Markdown), or full-text search the
  archive. Authenticates by
  reading the kiosk session out of the user's browser — no login to run. Every
  read supports --json."
allowed-tools:
  - Bash
  - Read
---

# miLibris kiosk CLI

Terminal access to any miLibris-powered liseuse, as the logged-in subscriber.

## How to invoke

Invoke it as **`milibris`**, on `$PATH` via `uv run claudine/scripts/link_clis.py`
(it links this repo's `bin/milibris` into `~/.local/bin`, so a `git pull` or an
uncommitted edit takes effect at once). If `milibris` is missing from `$PATH`,
run `<skill-dir>/bin/milibris` directly. It is a PEP 723 `uv` script; deps
resolve on first run.

## Authentication

Nothing to paste. The CLI decrypts the local Chromium cookie store (Chrome,
Arc, Brave, Edge) with the browser's macOS keychain key and reuses the kiosk
session cookie. **Start with `milibris kiosks`** — it lists exactly which hosts
the user is logged into. If it comes back empty, tell them to open the kiosk in
their browser and sign in; there is no login flow to automate here.

## Output conventions

- **`--json` on every read.** Human output is plain aligned text with no ANSI,
  so it pipes; never parse it — use `--json` for chaining.
- **Markdown** carries YAML frontmatter (title, publication, issue, date, page,
  rubrics, authors, words, reading time).
- **No silent fallbacks.** Failures exit non-zero with a one-line reason;
  surface it to the user.

## Commands

```bash
milibris kiosks                              # hosts the browsers are logged into
milibris whoami                              # is this kiosk's session still valid
milibris titles                              # titles carried by the kiosk
milibris issues -n 20                        # issues, newest first
milibris issues <title> --json               # {path, slug, mid, date, number, available}
milibris issue n249-2026 --json              # metadata + page/article counts
milibris toc --json                          # articles: id, page, rubric, words, abstract
milibris toc n249-2026 --rubric dossier
milibris read <article-id> --issue n249-2026 # one article as Markdown
milibris read <article-id> -o out/a.md
milibris read <article-id> --json            # the raw reader article JSON
milibris pdf                                 # readable PDF, typeset from the text
milibris pdf n249-2026 -o /tmp/issue.pdf
milibris pdf --facsimile                     # the page scans instead
milibris dump                                # pages + both PDFs + Markdown
milibris dump n248-2026 -o /tmp/out
milibris dump --page 5 --no-articles         # just one page
milibris dump --ld                           # quarter-resolution pages
milibris search "ukraine" --json
milibris search "ukraine" --issue n250-2026 --page 1
milibris material                            # the raw decrypted manifest (JSON)
milibris set-host digital.example.fr
```

`dump` writes to `~/Downloads/milibris/<title>/<date>/` unless `-o`:

```
pages/page-NNN.jpg              HD stitched page renders (--ld for the small ones)
<title>-<date>-facsimile.pdf    the page renders assembled
<title>-<date>-texte.pdf        readable PDF typeset from the article text
pNNN-<slug>.md                  one Markdown file per article, frontmatter included
resources/<mid>.jpg             article images, saved so the files outlive the ticket
```

## Recipes

**Give the user something they can actually read:**
```bash
milibris pdf                  # → ~/Downloads/milibris/<title>/<title>-<date>-texte.pdf, typeset and searchable
```

**Archive the current issue completely:**
```bash
milibris dump                 # → ~/Downloads/milibris/<title>/<date>/ (HD pages, both PDFs, Markdown)
```

**Find an article in the archive, then read it:**
```bash
milibris search "boualem sansal" --json | jq -r '.results[0] | .mid, .issue_mid'
milibris read <mid> --issue <issue_mid>
```

**Read every article of one rubric:**
```bash
milibris toc --rubric "dossier" --json | jq -r '.[].id' \
  | xargs -I{} milibris read {} -o "out/{}.md"
```

**Page count and article count of the last 5 issues:**
```bash
milibris issues -n 5 --json | jq -r '.[].slug' \
  | xargs -I{} milibris issue {} --json | jq -c '{issue_number, pages, articles}'
```

## Gotchas

- **Don't** invent slugs — run `milibris issues` first.
- **Don't** hit the kiosk or `content.milibris.com` with plain `curl`: the
  kiosks sit behind CloudFront and reject non-browser TLS handshakes. The CLI
  impersonates Chrome.
- **Don't** cache a ticket: it expires in ~30 minutes. The CLI re-mints it on a
  401 and every command mints its own.
- **Don't** parse the human output; use `--json`.
- **Don't** offer the facsimile when the user wants to *read* — hand them
  `milibris pdf`. The scans cannot be made sharper; the text can.
- **Don't** reach for `--ld` unless thumbnails are genuinely what is wanted.

## What miLibris is

miLibris hosts the digital edition ("liseuse") of many titles. Each publisher
gets its own host, but they all run the same two pieces:

1. a server-rendered **kiosk** (catalogue, issue pages, `/library`, search)
   whose only credential is an Express session cookie named
   `<name>WebKioskSessionKey`;
2. the shared **HTML5 reader**, which pulls a `material.json` manifest, page
   images and per-article JSON from `content.milibris.com` under a ~30-minute
   ticket JWT minted by the kiosk.

So this CLI is host-agnostic: it discovers kiosks by scanning the browser's
cookie stores, then speaks both protocols. It is also importable as a Python
module (`Kiosk`, `Issue`), which is how `franc-tireur-cli` reuses it.

## Picking the kiosk

Every command resolves the host in this order: `--host`, `$MILIBRIS_HOST`,
`~/.config/milibris-cli/config.json`, then the only kiosk found in the browser.
With several kiosks logged in, an unqualified command errors rather than
guessing — pass `--host` or run `milibris set-host <host>` once.

## Identifying an issue

Every issue-taking command accepts, in any of these forms (default: the latest
issue):

- `latest` or nothing
- an issue slug — `n250-2026`
- a `title/version/slug` path — `franc-tireur/franc-tireur/n250-2026`
- an issue mid (UUID) — from `issues --json` or `search --json`
- a full kiosk or `/reader/<mid>` URL

An unknown slug is an **error**, never a silent fallback to the latest issue.

## Resolution — read this before promising a readable scan

**The liseuse caps page rasters at roughly 1400×2050 pixels per printed sheet,
and there is no higher-resolution source.** `hd` is the maximum the manifest
exposes, the tiles measure exactly that, and the web kiosk has no PDF download.
On a broadsheet — where one "page" is a whole printed sheet carrying two
newspaper pages — that leaves body text around 11px tall: legible at 1:1 on
screen, mushy once printed or zoomed, and never selectable.

So:

- **For reading or printing an issue, use `milibris pdf`** — it typesets the
  article JSON into an A4 document that is sharp at any zoom, searchable, and
  ~15× smaller. This is the right answer to "the PDF is not readable".
- **`--facsimile` / `dump`'s facsimile PDF is for the layout**, not for reading:
  the page as it was printed, at the only resolution available.
- `--ld` exists for thumbnails and quick looks. It is a quarter of the pixels
  and is *not* readable. It used to be the default; it no longer is.

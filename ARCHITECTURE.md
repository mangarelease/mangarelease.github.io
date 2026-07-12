# Repo Map & Architecture

How this repository is laid out and how data flows through it. This file is
**hand-maintained** — unlike `README.md` and most data files, nothing
regenerates it, so it is the safe place for developer-facing notes.

> Forked from [LNRelease](https://github.com/LNRelease/lnrelease.github.io),
> the automated light-novel release calendar. This fork retargets the engine
> at licensed English **manga / manhwa / manhua / webtoons**.

## The one thing to know

Almost every file in the repo root is **load-bearing**, for one of two reasons:

1. **The scrape hardcodes root-relative paths** — `parse.py` opens
   `Path('books.csv')`, `scrape.py` opens `Path('info.csv')`, etc. The
   pipeline runs with the repo root as its working directory.
2. **GitHub Pages / Jekyll serves the site from the root** — `index.html`,
   `data.json`, the `*.md` pages, and `year/` are the published website.

So the flat root is not disorganization you can freely tidy — moving a file
means editing the code constant that points at it **and** checking the Jekyll
site still resolves it. Treat the layout below as the contract.

## Pipeline (runs daily via GitHub Actions)

`.github/workflows/python.yml` runs `python lnrelease/lnrelease.py`, which is
five stages in order:

```
scrape → tag → parse → write → pages
```

| Stage | Module | Reads | Writes |
|-------|--------|-------|--------|
| **scrape** | `scrape.py` + `source/*.py` | source sites, per-source caches | `series.csv`, `info.csv` |
| **tag**    | `tag.py`   | `origins.csv` (overrides) | taxonomy applied in-memory |
| **parse**  | `parse.py` + `publisher/*.py` | `series.csv`, `info.csv` | `books.csv`, `artbooks.csv` |
| **write**  | `write.py` | `books.csv` | `README.md` |
| **pages**  | `pages.py` | `books.csv`, `series.csv` | `data.json`, `physical.md`, `digital.md`, `html.md`, `audiobook.md`, `year/*.md` |

The workflow then commits changed files as `github-actions[bot]` and, if
`books.csv` changed, calls `pages.yml` to deploy the site.

The commit step stages tracked modifications (`git add -u`) plus `year/`
explicitly, because `pages.py` can mint a brand-new `year/<n>.md` at a year
boundary that a tracked-only add would miss.

## Site pages (`pages.py`)

`pages.py` generates the interactive-site data (`data.json`, consumed by
`index.html`) and the per-format / per-year Markdown pages. It runs as the
final pipeline stage, so these outputs track the scrape day-to-day alongside
the `README.md` calendar. You can also run it standalone
(`python lnrelease/pages.py`) to regenerate the site pages from the current
`books.csv`/`series.csv` without re-scraping.

## File map by role

### Generated output — never hand-edit (rewritten by the pipeline)
| File | Written by | Notes |
|------|-----------|-------|
| `README.md` | `write.py` | GitHub landing page **and** current/upcoming calendar. Opened in `'w'` mode → fully truncated and rebuilt every run. Static prose must live in `write.py`'s header/footer constants (see [Editing the README](#editing-the-readme)). |
| `books.csv` | `parse.py` | Every book release row (the main dataset). |
| `artbooks.csv` | `parse.py` | Art books, tracked separately. |
| `series.csv` | `scrape.py` | Series index. |
| `info.csv` | `scrape.py` | Per-product info. |

### Generated output — site pages (from `pages.py`, final pipeline stage)
| File | Notes |
|------|-------|
| `data.json` | Consumed by `index.html` for the interactive table. |
| `physical.md`, `digital.md`, `html.md`, `audiobook.md` | Per-format pages linked from `index.html`. |
| `year/*.md` | One page per calendar year (41 files). |

### Hand-maintained input — safe to edit
| File | Read by | Notes |
|------|---------|-------|
| `origins.csv` | `tag.py` | Taxonomy overrides: `slug,origin,category`. This is where you correct a mis-classified series (e.g. `daybreak,other,webtoon`). **Primary human-contribution surface.** |

### Per-source data/cache — owned by one source module
| File | Owner |
|------|-------|
| `viz.csv` | `source/viz.py` |
| `yen_press.csv` | `source/yen_press.py` |
| `one_peace.csv` | `source/one_peace.py` (currently empty) |
| `bookwalker.csv` | `source/bookwalker.py` (currently empty) |

### Code
| Path | Purpose |
|------|---------|
| `lnrelease/lnrelease.py` | Pipeline entry point (scrape→tag→parse→write). |
| `lnrelease/scrape.py`, `parse.py`, `tag.py`, `write.py`, `pages.py` | Pipeline stages. |
| `lnrelease/source/*.py` | One module per **release source** (publisher storefronts, aggregators). |
| `lnrelease/publisher/*.py` | One module per **publisher**, used by `parse.py` to normalize series. |
| `lnrelease/store/*.py` | One module per **storefront** (Amazon, Kobo, Apple, …) for product/price lookup. |
| `lnrelease/session.py`, `utils.py` | HTTP session (robots-aware) and shared types/helpers. |

### Site infrastructure (Jekyll)
| Path | Purpose |
|------|---------|
| `index.html` | Interactive site homepage; loads `data.json`. |
| `_layouts/`, `_sass/`, `assets/` | Jekyll theme, styles, static assets. |

### Project docs
| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | This file. |
| `AUDIT.md` | Running engineering audit / decision record. |
| `LICENSE`, `requirements.txt` | Standard. |

## Editing the README

`README.md` is regenerated top-to-bottom every scrape, so **do not edit it
directly** — changes are wiped within a day. To add or change static prose,
edit the constants in `lnrelease/write.py`:

- **Title / tagline** — the `title` string in `main()` (top of the file).
- **Taxonomy legend** — the `TAXONOMY` constant.
- **Footer** — the append block at the end of `main()` (fork note + link to
  this file).

The release tables in between are generated from `books.csv` and cannot be
hand-authored.

# Devlog

Dated, narrative progress notes. This is the human-readable companion to
`task.md` and the git history — what worked, what didn't, and why.

## 2026-07-13 — Phase 0: repo and process setup

Bootstrapped the repo: README with architecture diagram, MIT license,
`docs/ARCHITECTURE.md` (the original build plan), `docs/adr/` for decision
records, and this devlog.

Closed out the rest of Phase 0:

- **Branching convention** — documented in `CONTRIBUTING.md`: `main`
  protected, `feat/xxx` / `fix/xxx` branches, PRs even solo. Not overkill for
  a one-person project — it's what makes the commit history worth showing
  to anyone reviewing the repo later.
- **Python environment** — `pyproject.toml` as the single source of truth
  for dependencies (FastAPI/uvicorn for the web app, `requests` for
  Discogs/MusicBrainz, `pyacoustid` for the Chromaprint/AcoustID pipeline,
  `pytest` + `ruff` for dev tooling), plus a local `.venv`.
- **CI** — a GitHub Actions workflow that runs `ruff` and `pytest` on every
  push/PR. There's no application code yet, so it's currently a no-op that
  just proves the pipeline is wired up correctly before Phase 1 gives it
  something real to check.

Next up: Phase 1, the catalog MVP.

## 2026-07-14 — Phase 1: catalog MVP

Built the barcode-to-collection pipeline: a FastAPI app with server-rendered
(Jinja2) pages. `/add` takes a barcode, looks it up against Discogs first,
falls back to MusicBrainz if Discogs has no match, and either shows a
confirm-and-save screen for a hit or a manual-entry form (artist/album/format)
if nothing matched. Confirmed items land in `collection` and show up on
`/collection` as a cover-art grid.

**What worked:** every real CD I scanned — Tyler, The Creator's *Cherry Bomb*,
Jimi Hendrix's *Electric Ladyland*, The Beatles' *Abbey Road* — matched on
the first try via Discogs, cover art included. Never had to exercise the
MusicBrainz fallback for real; only tested it by making Discogs return no
results. A garbage/fake barcode correctly fell through to the manual-entry
form instead of erroring.

**What broke:** the first real run through the UI, Save and `/collection`
both failed. Root cause was dumber than expected — `sqlite3.connect()`
happily creates an empty `.db` file if one doesn't exist, but nothing was
applying `schema.sql` to it, so every write hit "no such table: collection."
It only worked in my own testing because I'd run `scripts/init_db.py` by
hand first. Fixed by moving schema application into a function the app
calls on startup (`CREATE TABLE IF NOT EXISTS`, so it's a harmless no-op
once the tables already exist) — the app can no longer boot into a state
where its own DB is missing tables.

Seed data is now the 3 real CDs above; a couple of throwaway test rows
(a garbage manual-entry and a made-up "Disco Pirata" example) got scanned
in along the way and were cleaned out before counting this as real seed
data.

Still open on Phase 1: cataloging the rest of the shelf, and tests for the
lookup/fallback logic are in (`tests/test_catalog.py`) but everything above
was verified by hand against the live app and live APIs, not just mocks.

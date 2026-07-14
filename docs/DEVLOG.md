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

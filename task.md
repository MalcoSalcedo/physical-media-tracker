# Physical Media Tracker — Task List

Ordered task checklist for building the project and documenting it for a portfolio. Mirrors `physical-media-tracker-build-plan.md`. Copy each top-level item into a GitHub Issue as you go (see Phase 0) so the repo's Issues/Projects tab becomes your visible project history.

## Phase 0 — Project & process setup

- [/] Create GitHub repo (`physical-media-tracker`), public, with a `.gitignore` for Python
- [/] Add MIT (or similar) license
- [/] Write initial `README.md`: one-paragraph pitch, architecture diagram, current status badge
- [/] Copy `physical-media-tracker-build-plan.md` into repo as `docs/ARCHITECTURE.md`
- [/] Create `docs/adr/` folder for Architecture Decision Records; write ADR-001: "Manual barcode entry instead of scanner for v1"
- [/] Create `DEVLOG.md` for dated, narrative progress entries (this is what recruiters actually read)
- [/] Set up GitHub Projects board (Kanban: Backlog / In Progress / Done), linked to the repo
- [x] Turn each Phase below into a GitHub Issue, add to the Projects board
- [x] Decide branching convention (e.g., `main` protected, feature branches `feat/xxx`, PRs even solo — gives you a reviewable commit history for recruiters)
- [x] Set up a Python virtual environment and `requirements.txt` / `pyproject.toml`
- [x] Add a basic GitHub Actions workflow that runs lint + tests on push (can be a no-op until Phase 2, but scaffold it now)

## Phase 1 — Catalog MVP (manual entry, no scanner)

- [x] Design SQLite schema: `collection`, `now_playing`, `history` tables (see ARCHITECTURE.md §5)
- [x] Write `schema.sql`, commit it to repo, add a script to initialize the DB (`scripts/init_db.py`)
- [x] Build catalog API endpoint(s) (FastAPI): `POST /collection` to add an item by barcode
- [x] On barcode submit, look up via Discogs `/database/search?barcode=...`; fall back to MusicBrainz barcode search
- [x] If no match found, show a manual-entry form (title/artist/format) instead of failing
- [x] Build a simple web form: text input for barcode → submit → confirms match → saves to `collection`
- [x] Build `GET /collection` page: grid/list view with cover art
- [x] Manually catalog your shelf using the form — this is your seed data
- [x] Write tests for the lookup + fallback logic
- [x] DEVLOG entry: what worked, what barcodes didn't match, how you handled it

## Phase 2 — Now-playing / audio ID MVP

- [x] Wire up USB mic, confirm capture works
- [x] Install Chromaprint / `fpcalc`, test fingerprinting a known track manually
- [x] Get an AcoustID API key, test a lookup call end-to-end from the command line

See `docs/adr/ADR-002` for why the plan below is more layered than originally
scoped: empirical testing showed short clips (<90s) are unreliable for
AcoustID lookups regardless of signal quality, so identification is built
around album pre-selection + several complementary techniques rather than a
single blind fingerprint-and-poll loop.

- [x] Data model: add a `tracks` table (collection_id, track_number, title,
      duration_seconds); fetch tracklist from MusicBrainz/Discogs release
      detail endpoints when an album is selected
- [x] Build "select album to listen to" UI + endpoint; stores the active
      album context for the listener to use
- [x] Build a silence/gap detector (RMS-based), standalone and unit-tested
      against synthetic signals, independent of fingerprinting
- [ ] Build album-constrained fuzzy matching: capture a ~30s clip → fpcalc →
      AcoustID lookup → accept a lower-confidence match if its title
      fuzzy-matches a track on the active album
- [ ] Build a local fingerprint cache: store a confirmed track's own-mic
      fingerprint; compare against the cache before calling AcoustID on
      repeat plays of the same album
- [ ] Build progressive/adaptive clip length fallback (30s → 60s → 90s) for
      when a short clip returns no usable candidate
- [ ] Write `listener.py`: orchestrates gap detection → local cache lookup →
      album-constrained fuzzy AcoustID match → duration-timer advance
      between checks
- [ ] On match, update `now_playing` row and append to `history`
- [ ] Turn `listener.py` into a `systemd` service (`listener.service`) so it
      runs headless on boot
- [ ] Add `GET /now-playing` endpoint + banner on the web page
- [ ] Test with real CD player audio via line-in (Focusrite) at normal
      listening volume; tune clip length/interval/thresholds
- [ ] Write tests for the matching logic (gap detector, fuzzy matcher,
      duration timer — mock AcoustID responses)
- [ ] DEVLOG entry: fingerprinting accuracy, false positives/negatives,
      tuning notes

## Phase 3 — Web UI polish

- [ ] Clean up collection grid (cover art, sort/filter by artist/format)
- [ ] Now-playing banner with cover art + "last updated"
- [ ] Recently-played history list
- [ ] Basic responsive styling (doesn't need to be fancy — functional and clean)
- [ ] Screenshot or short screen recording for the README

## Phase 4 — Public sharing

- [ ] Register/point a domain at Cloudflare (or use a free subdomain if applicable)
- [ ] Install and configure `cloudflared` on the Pi
- [ ] Create named tunnel, map public hostname to local `webapp.service` port
- [ ] Set `cloudflared` up as a `systemd` service for boot persistence
- [ ] Test access from outside your home network
- [ ] Share the link with a friend, get real feedback
- [ ] DEVLOG entry: tunnel setup, any gotchas

## Phase 5 — Vinyl support

- [ ] Add turntable to the setup
- [ ] Test mic-based fingerprinting accuracy on vinyl (expect it to be worse than CD)
- [ ] If unreliable, add USB audio interface for line-in capture instead of mic
- [ ] Update ADR log with the decision and why
- [ ] Re-test end to end with both source types

## Phase 6 — Documentation & portfolio packaging

- [ ] Finalize `README.md`: problem statement, architecture diagram, tech stack, setup instructions, screenshots/GIF
- [ ] Write a retrospective section in `DEVLOG.md` or a separate `RETROSPECTIVE.md`: what you'd do differently, what you learned
- [ ] Make sure ADRs cover the real decisions made (fingerprinting approach, hosting/sharing approach, manual vs. scanner entry, SQLite choice, vinyl handling)
- [ ] Confirm GitHub Projects board reflects real history (close out completed items, don't delete — it's evidence of process)
- [ ] Record a short demo video/GIF of the whole flow: scan → catalog → play a CD → see it show up live
- [ ] Write a short blog-style writeup (can double as a LinkedIn post) summarizing the project end-to-end
- [ ] Add project to resume/portfolio with a link to the repo, live demo URL, and writeup

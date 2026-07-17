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

## 2026-07-14 — Phase 2 kickoff: the short-clip assumption was wrong

Got the hardware/API prerequisites working fast: a Blue Snowball mic
recording real audio, Chromaprint (`fpcalc`) installed and fingerprinting,
and an AcoustID lookup running end-to-end from the command line. First real
mic recording of Gorillaz - "Feel Good Inc." played from a laptop speaker
was clearly recognizable on playback, which made it all the more surprising
when AcoustID returned zero matches for it.

Root-caused this properly instead of guessing: fingerprinted a clean MP3 of
the same track (no mic, no room, isolates signal quality as a variable) and
swept clip length/offset against the live API. Short clips (<90s) came back
empty even from perfectly clean audio; a ~120s+ clip matched instantly at
0.97 confidence. So the original Phase 2 plan's assumption — a 10-15s clip
is enough — was just wrong for this track, and duration turned out to be
the dominant variable, not mic/room signal quality like I initially
suspected.

That's a real problem for the actual goal (catching a track skip
responsively), since waiting 90+ seconds per identification attempt is far
too slow. Landed on a layered design instead of a single blind
fingerprint-and-poll loop — album pre-selection (user tells the app what's
about to play, shrinking the candidate set from "all recorded music" to
"~12 known tracks"), silence-gap detection for fast skip detection,
duration-based timer advancement between checks, fuzzy-matching short clips
against the known album tracklist, and a local fingerprint cache to make
repeat plays of the same disc nearly free. Full reasoning and the test data
behind it are in `docs/adr/ADR-002`.

Next up: build the pieces in `task.md`'s revised Phase 2 list, then
validate against real CD player audio via the Focusrite line-in instead of
the mic — the mic path is a reasonable fallback but the line-in should be
materially more reliable, and it's hardware I already own.

## 2026-07-16 — Phase 2 built out: all five ADR-002 layers, plus a real timezone bug

Built every piece from ADR-002's layered design, each as its own PR: album
selection + tracklist fetching (`/listen`, `/now-playing`, Discogs/
MusicBrainz release-detail lookups), the RMS-based gap detector, album-
constrained fuzzy matching (`track_matcher.match_against_album`), a local
fingerprint cache, progressive cache-first/fuzzy-match identification with
escalating clip length, and finally `listener.py` tying all of it into an
actual polling loop with duration-timer track advancement.

**Two real bugs worth remembering:**

- Comparing two Chromaprint fingerprints for the local cache needs
  `libchromaprint`'s decode function, which needs the shared library - not
  just the standalone `fpcalc.exe` this project already had installed.
  Rather than chase down a separate DLL, `fpcalc -raw` turned out to give
  the same raw integer fingerprint directly, so `app/local_match.py`
  reimplements Chromaprint's own alignment-based comparison in pure Python
  against that. Verified against real `fpcalc` output: a fingerprint
  compared against itself scores 1.0, two different segments of the same
  real song score near zero (0.03).
- `listener.py`'s duration-timer logic compares `now` against `started_at`,
  which comes from SQLite's `datetime('now')` - which is UTC. My first pass
  used Python's local `datetime.now()` for the comparison. On this machine
  that's a 7-hour offset, which would have made track-advancement timing
  silently wrong in a way that's easy to miss by eye and easy to introduce
  again elsewhere. A test comparing "same track, 5 minutes later" against
  "same track, 10 seconds later" caught it immediately - concrete evidence
  for why the escalating/timer logic got real unit tests instead of only
  being checked by hand.
- Also hit a CI-only failure: `sounddevice` needs the system PortAudio
  library, which isn't on the GitHub Actions runner by default. Every
  earlier PR happened to avoid importing `app.fingerprint` from any test
  file, so this didn't surface until the first test that did. Fixed with
  an `apt-get install libportaudio2` step in the CI workflow.

Still open: real CD player audio via the Focusrite line-in hasn't happened
yet - everything so far is verified against the mic and against clean
files, which is a different (probably easier) case than a physical CD
player at real listening volume. That's the next real test, and it's the
one that'll actually tell us whether the similarity/confidence thresholds
picked so far (gap detector's silence threshold, the fuzzy matcher's
score floors, the local cache's similarity floor) are anywhere close to
right.

## 2026-07-16 (cont.) — First real line-in test: one clean miss, one clean hit

Wired the CD player into the Focusrite for real. First attempt used the
wrong port entirely - the obvious-looking "R/L" terminals on the back are
speaker-level output (this is an all-in-one micro system with the amp
built in), not line-level, and would have fed way too hot a signal into
the interface's line input. Found the actual "PHONES" jack on the side
panel instead - a proper line-level output with its own volume control,
the safe and correct way to do this. Worth remembering for anyone doing
this with a similar compact system: check for a headphone jack before
assuming the visible rear terminals are usable.

Signal quality through the real connection was excellent - 45-50% peak
level, zero clipping, clean full-bandwidth spectrum, no DC offset. Much
stronger and cleaner than any mic recording so far.

**The miss:** a 90-second recording of "Come Together" (Abbey Road, track
1) - confirmed by ear to be a clean, correct, fully audible recording of
the right song - returned **zero** results from AcoustID's raw lookup.
Not a low-confidence miss, not a title-mismatch, an empty result set.
Swept every window from 15s to 90s, at multiple offsets, all zero. Ruled
out a technical capture problem first (0% clipping, negligible DC offset,
33% of energy above 5kHz - a healthy, unfiltered signal), so this wasn't
our recording chain's fault. Most likely explanation: this specific CD's
mix/mastering (the Beatles catalog has several distinct official
remasters with real mixing differences) doesn't line up with whatever
fingerprints exist in AcoustID's database for this recording. A genuinely
humbling result - even one of the most famous recordings ever made isn't
guaranteed to match, because fingerprint matching cares about the exact
mix, not just "is this a well-known song."

**The hit:** swapped to Electric Ladyland and got a clean match on the
first try - "...And the Gods Made Love" (correctly, track 1) at 0.78-0.79
confidence, through the *entire* real pipeline end to end: line-in
recording → fpcalc → AcoustID → `track_matcher.match_against_album`
against the real stored tracklist → `now_playing` updated with
`source='fingerprint'` → local fingerprint cache populated for next time.

**Tuning conclusion for now:** the Abbey Road miss isn't a threshold
problem to tune away - no duration or offset produced any result at all,
so there was nothing to fuzzy-match against in the first place. The
Electric Ladyland hit validates the pipeline and thresholds as currently
configured need no immediate change. The practical implication: some
specific discs may just never match via AcoustID regardless of tuning,
and the local fingerprint cache (once a track is identified by any means)
is what makes repeat plays of exactly those discs reliable going forward
- this is a real, not just theoretical, reason that layer exists.

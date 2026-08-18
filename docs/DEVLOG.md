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

## 2026-07-20 — Second real-world test: a new miss, and a real cataloging bug

Cataloged a new CD (Deftones - *White Pony*) live and ran it through the
full flow: `/add` → `/listen` → `listener.py` running against the
Focusrite line-in. Let it run for ~8 minutes across two full
identification cycles. No match, ever - `now_playing.track_title` stayed
`None` the whole time.

Same diagnostic approach as the Abbey Road miss: recorded a fresh 90s
clip directly, confirmed by ear it was clean and correctly "Feiticeira,"
checked for clipping/DC offset/spectral anomalies (all clean, same as
before), then hit the raw AcoustID API directly. Zero results, across
every window length from 15-90s. Second miss out of three real CDs
tried so far - one real hit (Electric Ladyland), two misses (Abbey Road,
White Pony), both on otherwise very famous, heavily-covered songs.

**A genuinely different, fixable bug surfaced along the way:** the user
noticed their physical disc's tracklist (opens with "Back To School
(Mini Maggit)") didn't match what was cataloged (opened with
"Feiticeira"). Traced it: Discogs returns **16 different release
entries** for this exact barcode - reissues/represses commonly reuse the
same printed UPC as the original pressing. `discogs.search_by_barcode()`
just takes `results[0]`, so it grabbed the original 2000 pressing
instead of the reissue the barcode actually came from. Fixed the
specific catalog entry by hand (found the right release ID by checking
which of the 16 candidates had the right first track, then re-fetched
its tracklist) - but the underlying `search_by_barcode` behavior (no
disambiguation when a barcode maps to multiple releases) is still there
for future scans. Worth revisiting if it comes up again, though there's
no obviously correct heuristic to prefer one release over another
without more signal than the API gives.

Worth noting for accuracy: initially guessed the tracklist mismatch
itself might explain the zero AcoustID results (different mix on the
reissue). Checked and ruled that out - the reissue's "Feiticeira" has
the *exact same duration* (3:09) as the original pressing's, so it's
very likely the same master, just with a bonus track prepended. The
fuzzy matcher is title-based anyway, not position-based, so a tracklist
mismatch wouldn't have blocked a match if AcoustID had found one. The
zero-result cause here remains the same open question as Abbey Road.

## 2026-07-20/21 (cont.) — A full real-world testing round: 1 hit, 5 misses

Kept going with more CDs in the same session, cataloging and testing each
one live through the Focusrite line-in: Jeff Buckley's *Grace* (tested
twice - once mid-song, once from a clean track-1 start), Kendrick Lamar's
*GNX*, and A Tribe Called Quest's *The Low End Theory*. Every one of them
missed - zero AcoustID results, every duration tried.

That's **1 hit / 5 misses** total across every album tested so far
(Electric Ladyland the lone success; Abbey Road, White Pony, Grace, GNX,
The Low End Theory all missed). Before accepting that as the real
baseline, spent this round specifically trying to rule out anything
systemic rather than track-specific:

- **API/account health** - re-ran the exact recording that succeeded on
  day one (the clean Gorillaz MP3) through the same API key. Still a
  clean 0.97-confidence match. Rules out a broken or rate-limited account.
- **Recording quality** - every single clip across all five misses came
  back clean on inspection: no clipping, negligible DC offset, healthy
  signal levels (44-50% peak, consistent with the one clip that *did*
  match). This was checked, not assumed, for each one.
- **Track-boundary contamination** - the CD naturally crosses track
  boundaries sometimes when a recording starts at an arbitrary point
  mid-album. Caught this happening twice (a Grace clip that spanned
  Mojo Pin into the title track, a GNX clip with ~3s of Squabble Up
  bleeding into Luther) and retested trimmed, single-track-only clips
  in both cases. Still zero. Ruled out as the cause, at least for the
  clips tested.

What's left, having eliminated the above, is a genuinely uncomfortable but
honest conclusion: AcoustID's crowdsourced fingerprint database has real,
uneven coverage gaps for CD-sourced audio, and they show up more often
than the one early success suggested. This isn't a pipeline bug - every
piece (recording, fingerprinting, the API call, the matching logic) is
verified working correctly. It's a real limitation of depending on a
community fingerprint database for this specific use case (identifying
audio from a spinning physical disc via line-in, as opposed to say a
clean digital rip), and it's worth being upfront about in anything
written about this project rather than only showcasing the one success.

Given a ~20% real hit rate (1/5) so far, this is worth keeping in mind
for how the project gets described going forward - not as "identifies
what's playing" unconditionally, but as "attempts to identify, with real
limits tied to AcoustID's actual coverage." The local fingerprint cache
still matters for the discs that do get identified at least once, but it
doesn't help the discs that never get a first hit at all.

## 2026-07-31 — The "coverage gap" conclusion was wrong. Found the real bug.

The three albums that failed during physical testing (GNX, Grace, The Low
End Theory) got ripped to digital files, which made possible the one test
that should have happened before concluding anything about AcoustID's
coverage: fingerprint the *exact same tracks*, clean, no analog signal path
at all, and see what happens.

They all matched immediately, at 0.96-0.99 confidence. AcoustID has these
recordings well-fingerprinted. The 2026-07-20/21 conclusion - that this was
a real, uneven coverage gap in AcoustID's database - was flatly wrong.

Tracked down the actual cause instead of accepting the first plausible
theory a second time. `app/identify.py`'s pipeline was still failing on
these exact files even though the raw digital-file lookups worked, which
ruled out a decode-path issue and pointed at something in how the pipeline
itself constructs the AcoustID query. Isolated it with one fixed
fingerprint (same bytes, a genuinely 60-second real clip of "Luther") and
varying only the declared `duration` parameter sent to AcoustID:

- Honest duration (60s, matching the actual clip) → 0 results
- Other guesses (90, 120, 240, 300s) → 0 results
- The track's *true* length (178s - which was already sitting in our own
  `tracks` table from the original Discogs lookup) → **0.99 confidence**

Not "any large duration works" - specifically, the declared duration has to
be close to the true reference recording's length. Confirmed the same
pattern on Mojo Pin and Rap Promoter using their own stored durations, and
confirmed clips as short as 15-20 seconds work fine once the duration guess
is right (10s still fails). The entire "duration is the bottleneck" framing
from 2026-07-14 had been *accidentally correct for the wrong reason* the
whole time: an uncapped fpcalc call reports a file's full metadata
duration, not the analyzed window, so a long test clip was incidentally
also sending a better duration guess. Nobody had isolated declared-duration
as its own variable until now.

The fix (full reasoning in `docs/adr/ADR-003`): `identify_current_track`
now fingerprints a clip once, then queries AcoustID **once per each of the
album's known track durations** - data that was already being fetched and
stored back in Phase 2's first PR, just never used in the query itself,
only for fuzzy-matching titles afterward. Verified against the real
pipeline: all three previously-failing tracks now identify correctly using
20-second clips.

Worth being honest about the process here, not just the result: the
2026-07-20/21 devlog entry stated a wrong conclusion with real confidence,
because "ruled out everything else, therefore it must be X" is a weaker
argument than it feels like in the moment - it stops looking the instant a
remaining plausible explanation is found, not when the explanation is
actually confirmed. The thing that actually resolved it was a new kind of
evidence (a clean-signal control test on the literal failing tracks), not
more reasoning about the evidence already in hand.

Still open: this fix is verified against digital files, not yet against
real CD player line-in audio again. That's the next real test - expecting
it to now work, but "expecting" isn't "verified," and that distinction is
exactly what this entry is about.

## 2026-08-01 — Real line-in re-test: the duration fix works, skip tracking didn't

Re-hooked up the CD player and re-ran the exact setup that failed on
2026-07-20/21 (The Low End Theory, via the Focusrite line-in). The
duration fix held up on real hardware, not just digital files: "Excursions"
identified almost immediately, and sequential timer-based advancement to
"Buggin' Out" landed within seconds of the predicted track boundary. Good
confirmation that ADR-003 wasn't a digital-file-only fix.

Skip detection was a different story. Manually skipped the CD forward
mid-track (twice, in fairly quick succession) to test whether the gap
detector would catch it and trigger a re-identify. It didn't - `now_playing`
sat on the stale track for several minutes across both skips, while the
album kept playing for real. Root cause: `tick()`'s gap-check only records
a ~2 second clip once every ~5-7 second cycle (the old `POLL_INTERVAL_SECONDS
= 5`), so there's a real dead zone between samples where nothing is being
monitored at all. A CD's inter-track silence is often only 1-3 seconds -
short enough that it had a real chance of falling entirely inside that gap
and never being observed. Confirmed by manually forcing a fresh
identification, which correctly caught up once run directly.

Fixed by dropping `POLL_INTERVAL_SECONDS` to near-zero instead of adding a
background monitoring thread - simpler, and closes most of the blind spot
with a one-line change (full reasoning in the comment at that constant).
Re-tested live: the tightened loop caught a real skip cleanly this time
(track 6 to 7, landing correctly on "Vibes And Stuff"). But a second round
of rapid back-to-back skips (through tracks 8 and 9) still got missed
before the system caught up on its own a few tracks later - real
improvement (one skip caught this time, versus zero all of last session),
not a complete fix. Documenting that honestly rather than overclaiming.

That led to a good question: what about skipping backward, or a random
back-and-forth sequence, not just forward skips? Walked through the logic
and found re-identification is already position-independent (it searches
the whole album, not "the next track"), so direction was never the issue.
But there was a real, separate bug in `decide_next_action`: it only
treated a detected gap as "definitely a skip, re-identify" if the gap
fired *before* the current track's stored duration would have naturally
elapsed; a gap landing at or after that point was treated as a normal
transition and just advanced to the next track in sequence without
re-checking. A skip whose timing happened to coincide with that boundary
would've been silently misclassified. Simplified `decide_next_action` so
any detected gap always triggers a full re-identify, full reasoning in
`app/timer.py` - the original "save an AcoustID call when it's probably
just a normal transition" logic mattered a lot more before the duration
fix made identification fast; now it's a small, worthwhile trade for
correctness.

Net for today: the duration-hinting fix (ADR-003) is now confirmed on real
hardware, not just files. Gap detection is meaningfully more reliable than
before but not yet bulletproof against rapid successive skips - worth
another real test now that both fixes are in, but not yet re-verified as
of this entry.

**Update, same session:** re-tested live with the "always re-identify on
gap" fix deployed. The listener caught up entirely on its own from where
it had lagged - no manual intervention - eventually landing correctly on
"Skypager" (track 12) as the album played out to its end. Good sign the
combination of both fixes (tighter polling + no more gap-timing
misclassification) is meaningfully more self-correcting than either fix
alone, even if it doesn't catch literally every individual skip in a rapid
sequence.

One gap noticed at the very end of the session, not yet fixed: once the
CD physically stops, the system has no concept of "the album ended." It'll
just keep trying to re-identify against silence indefinitely (wasted
AcoustID calls) rather than recognizing "nothing is playing" as its own
state. Worth addressing whenever now-playing work picks back up, but not
urgent - low real cost (a background loop making occasional fruitless API
calls), just an honest known gap in the current design.

## 2026-08-03 — A "stopped" state, and a live-refreshing page

Closed the gap noted at the end of the last session and made the web page
actually feel real-time rather than requiring a manual reload.

**"Stopped" state:** `now_playing` gained a `status` column
(`waiting` / `playing` / `stopped`) alongside the existing `track_title`.
`listener.py` now runs a second `GapDetector` instance alongside the
existing gap detector - same gap-check clips, no extra recording - but
with a much longer threshold (30s) tuned to catch "the CD actually
stopped" rather than a normal 1-3s inter-track gap. When it fires while a
track is playing, `catalog.mark_stopped()` flips the status but
deliberately *keeps* the last-known `track_title` around, so the UI can
show "Stopped - last playing: X" instead of just going blank.

Wiring this in surfaced a real latent bug in `decide_next_action` while
reasoning through the has_signal/status interaction: a track that stopped
playing mid-track (not at a clean boundary) would eventually have its
stored duration "expire" and get silently, wrongly ADVANCEd to whatever's
next in album order, even though nothing was actually playing. Fixed by
gating ADVANCE on `has_signal` - the same cheap RMS check already used
elsewhere - so a genuinely silent input just waits instead of guessing.

**Live refresh:** added a small `GET /api/now-playing` JSON endpoint and a
plain `<script>` block in `base.html` that polls it every 5 seconds and
updates the banner's title/subtitle/time-ago text in place - no framework,
matching the rest of the project's server-rendered, no-build-step
approach. On `/now-playing` specifically, a change in track or status also
triggers a full page reload, so the tracklist highlight and recently-played
table (which the banner alone can't update) stay in sync too.

Verified locally against the running dev server (not yet against live CD
player audio) by directly flipping `now_playing.status` in the DB and
confirming both the JSON endpoint and the rendered `/now-playing` /
banner correctly show the stopped state, then flipping it back. Added
test coverage for all of the above: `decide_next_action`'s new `status`
parameter and the has_signal-gated ADVANCE fix, `listener.tick()`'s
wiring of the new stopped detector (fires while playing → marks stopped;
signal resumes while stopped → re-identifies), and `catalog.mark_stopped`.
82 tests passing.

Next real test: confirm the stopped detector's 30-second threshold is
sane against an actual CD player (does the player itself go silent for
that long between tracks or at end-of-disc in a way that could false-
trigger it?) - not yet checked against real hardware, only reasoned about.

## 2026-08-05 — Real-hardware test of the stopped state, and a real bug it found

Went back to the CD player to verify the previous session's stopped-state
work, which had only been checked by hand-editing the DB. Found a genuine
bug the same day, fixed it, and re-verified live.

**First real signal: natural end-of-album silence works correctly.** The
album under test (Radiohead, *OK Computer OKNOTOK*, 23 tracks) had
finished playing on its own a couple minutes before the listener even
started. Once running, it took ~30 seconds of its *own* measured silence
to flip `status` to `stopped` - matching `STOPPED_SILENCE_SECONDS`
almost exactly, confirmed against both the DB and the live
`/api/now-playing` endpoint. Side finding, not a bug: a 23-track album
means up to ~24 sequential AcoustID duration-guesses per identify
attempt (per ADR-003), which made the very first identify on this album
take several minutes and miss - a real scaling cost of that fix worth
remembering when picking a test album; short-tracklist albums (10-14
tracks) stay fast.

**Second real signal, this one exposed an actual bug.** Switched to *The
Low End Theory* (already a proven real-hardware match today) to test the
resume-from-stopped path: paused mid-track for about a minute, then
resumed from the same point. Expected `stopped` to appear cleanly; instead
the listener went silent (no log output at all) for nearly 3 minutes.
Root cause: `decide_next_action`'s `if gap_detected: return IDENTIFY`
branch doesn't check `has_signal` - and a gap fires *precisely because*
the current chunk is silent. So the instant the short gap detector crossed
its 1.5s threshold, the listener immediately started recording into the
pause and running a full escalating AcoustID sweep (20s + 45s + 90s clips)
against what was, for a chunk of that span, literal silence. That single
blocking call ate up wall-clock time the stopped-detector needed to reach
its own 30s threshold from ticks that never got to run - a 60-second real
pause never actually surfaced as `stopped` in the UI, because measuring it
got interrupted by a doomed identify call.

**The fix:** stopped gating the re-identify on "a gap just fired" and
started gating it on "a gap fired *and* signal has since resumed."
Implemented as a small `pending_gap` flag threaded through `listener.py`'s
`tick()`/`run()` (deliberately not baked into `GapDetector` itself, since
`stopped_detector` reuses that same class and needs its original "fire
while still silent" semantics to keep working). `decide_next_action`
itself needed no logic changes - only its caller's contract for what
`gap_detected` means, documented in its docstring. Added two new
`listener.py` tests: a gap firing during silence stays `WAIT` (and
remembers the gap instead of acting on it), and re-identify only fires
once signal actually returns. 84 tests passing.

**Re-tested live from scratch, and it fully validated the fix:** paused
Excursions ~40s in, waited a minute, resumed - the log went from a clean,
continuous stream of cheap `wait` ticks straight into `stopped`, with zero
wasted identify calls during the pause itself (compare to the ~176s wasted
on the pre-fix run). Once resumed, the system correctly retried
identification (the first attempt missed - a known, separate AcoustID
reliability question, not a bug; the second succeeded) and landed on
"Buggin' Out." That looked like a wrong match at first glance since the
CD had only been paused at Excursions' 40s mark - but it was actually
correct: because the resume-side identification took a couple of minutes
of real AcoustID lookups to resolve, the CD had genuinely kept playing in
the background and had already moved past Excursions for real by the time
either identify attempt recorded its clip. Each attempt fingerprints
whatever's *actually* playing at that moment, not the state from when the
gap first fired - the position-independent design (from the 2026-08-01
skip-detection fix) doing exactly what it was built to do, just visible
here in a case that wasn't a deliberate skip.

**One process-hygiene bug caught along the way, unrelated to the app
itself:** `taskkill //F //PID $!` (bash's last-background-PID) repeatedly
killed the wrong process on this Windows/git-bash setup, silently leaving
old `listener.py` instances running against the same DB while new ones
started - at one point two were running concurrently. Fixed the testing
workflow (not the app) by verifying real PIDs via
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object
{ $_.CommandLine -like '*listener.py*' }` before every kill, rather than
trusting `$!`.

Net for today: the stopped-state feature from 2026-08-03 is now verified
against real CD player audio in both directions (entering *and* leaving
`stopped`), and a real bug in how it interacted with the existing
skip-detection logic is fixed and re-verified live, not just by unit
tests. The album-picking lesson (favor short tracklists for fast
iteration) and the PID-verification habit are both worth remembering for
the next live session.

## 2026-08-05 (cont.) — Closing the duplicate-instance gap for real

The stray-process incident earlier today was fixed as a testing-workflow
problem (verify real PIDs before killing), but the underlying risk is an
app-level gap, not just a today's-session annoyance: nothing stops two
real `listener.py` instances from running against the same DB
concurrently - a systemd restart racing a manual debug run, for instance -
and two writers polling and updating `now_playing`/`history` at once is a
real correctness risk, not just wasted resources.

Added a pidfile lock (`data/listener.pid`, gitignored alongside the DB
itself): `run()` refuses to start if the file names a PID that's still
alive, and cleans up its own lock file on exit via `try`/`finally`. A
stale lock (process killed forcefully, e.g. `taskkill -F` or a Pi power
loss - neither runs Python's `finally`) is detected and silently
overwritten rather than blocking legitimate restarts. The liveness check
(`_pid_is_running`) needed a small platform branch: `os.kill(pid, 0)`
works correctly on Linux (the real Pi target) but not on Windows (used
for local dev), so Windows goes through `OpenProcess`/`CloseHandle` via
`ctypes` instead.

Verified live, not just via the 5 new unit tests: started a real instance,
attempted a second in parallel - refused immediately with a clear message
naming the holding PID, no traceback. Force-killed the first (simulating
a crash) and confirmed a fresh instance correctly detected the stale lock
and started anyway, overwriting it with its own PID. No leaked processes
in either case.

## 2026-08-18 — Full-album soak test, a stale device index, and a clean run

First real session back after a break, picking Phase 3.5's checklist back
up. Cataloged a new CD live (Billy Joel, *The Stranger* - 9 tracks,
~40 min) specifically to exercise the full pipeline end to end (barcode
scan → catalog → select → play), not just replay an already-proven album.

**Immediate real bug, unrelated to anything fixed so far:** the listener
sat on `wait` indefinitely with no signal detected at all, despite the CD
audibly playing. Root cause: the Focusrite's device index had shifted from
`2` to `3` since the last session - Windows re-enumerated it (likely after
a reboot or USB reconnect between sessions), and `listener.py` was quietly
recording from index 2, which now resolves to an unrelated mic. Worth
remembering for next time: device indices aren't guaranteed stable across
reboots on this Windows dev setup, so a "no signal at all" symptom should
prompt a `sounddevice.query_devices()` check before assuming a software
regression. (The Pi deployment uses a fixed physical USB port, which is
more stable in practice, but not something to take for granted there
either.)

**The soak test itself, once the device was fixed:** rewound to track 1
for a clean run. The first three identify attempts (all on "Movin' Out")
missed - each a real ~2m50s escalating AcoustID sweep that came back
empty, a new coverage-gap data point for this pressing, not a pipeline
bug. The fourth attempt caught up correctly once real playback had reached
track 3 ("Just The Way You Are") - a good demonstration of the
position-independent design self-correcting rather than getting stuck.
From there: **6 consecutive clean transitions** through the rest of the
album, each landing within a couple seconds of the track's actual stored
duration. The album's natural end correctly triggered `stopped`, with one
small wrinkle worth noting: a stray `identify` fired a couple minutes
after the last track's expected end, most likely a brief mechanical noise
from the CD player's transport settling (confirmed with the user that this
player fully stops rather than looping) crossing the RMS threshold for a
single tick. It correctly found no match and the system settled into
`stopped` shortly after - a small wasted AcoustID call, self-corrected,
not worth chasing further given how rare and low-cost it is.

Net: this is the first true start-to-finish validation of normal,
non-adversarial playback since the 2026-08-05 fixes landed, and it held up
cleanly. Phase 3.5's soak-test item is checked off; the initial three
misses on "Movin' Out" are logged as a real AcoustID coverage data point,
separate from anything today's testing was meant to fix.

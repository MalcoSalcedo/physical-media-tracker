import sqlite3

from app import catalog, fingerprint, track_matcher
from app.gap_detector import find_first_gap_offset

DEFAULT_DURATIONS = (20, 45, 90)
SAMPLE_RATE = 44100


def identify_current_track(
    conn: sqlite3.Connection,
    collection_id: int,
    api_key: str,
    record_fn=None,
    durations: tuple[int, ...] = DEFAULT_DURATIONS,
    sample_rate: int = SAMPLE_RATE,
) -> str | None:
    """Identify the currently playing track on the given album.

    Tries the local fingerprint cache first (fast, no network) at each
    escalating clip length. If nothing is cached yet, falls back to an
    album-constrained fuzzy AcoustID match - but critically, the lookup is
    tried once per each of the album's *known* track durations (from our
    own tracklist), not the clip's own recorded length. AcoustID's matching
    turns out to be sensitive to how close the declared duration is to the
    true reference recording's length; a short, honestly-declared clip
    duration gets rejected even when the fingerprint content itself would
    otherwise match cleanly. See ADR-003 for the investigation and
    evidence. This is also why clips can now be much shorter than
    originally planned - a 15-20s clip matches fine once the duration
    guess is right, so a longer clip is only recorded if every duration
    guess fails at the current length.

    Each recorded clip is checked for a real track transition *within* it
    (reusing the same sub-window silence detection as GapDetector) and
    trimmed to just the audio before that point if one is found - a long
    clip recorded without knowing our exact position in the current track
    can otherwise run past a short track's end and into the next one,
    producing a fingerprint that's a blend of two songs and matches
    neither. Found live (2026-08-19), first tried capping every clip's
    length by the album's shortest track instead - that broke matching for
    a long track ("Excursions") that genuinely needed the full 90s clip to
    match confidently, since the cap applied to every attempt on the
    album, not just the ones actually at risk. Trimming only when a
    transition is actually detected fixes the short-track contamination
    case without degrading long tracks that never had the problem.
    """
    if record_fn is None:
        record_fn = fingerprint.record_clip

    tracks = catalog.get_tracks(conn, collection_id)
    known_titles = [t["title"] for t in tracks]
    known_durations = sorted({t["duration_seconds"] for t in tracks if t["duration_seconds"]})

    for clip_duration in durations:
        samples = record_fn(clip_duration)
        gap_offset = find_first_gap_offset(samples, sample_rate)
        if gap_offset is not None:
            samples = samples[:gap_offset]
        actual_duration = len(samples) / sample_rate

        raw_fp = fingerprint.raw_fingerprint(samples, sample_rate)

        cached_match = catalog.find_cached_match(conn, collection_id, raw_fp)
        if cached_match:
            return cached_match

        compressed_fp = fingerprint.compressed_fingerprint(samples, sample_rate)
        for duration_guess in (*known_durations, actual_duration):
            results = fingerprint.lookup_with_duration(compressed_fp, duration_guess, api_key)
            fuzzy_match = track_matcher.match_against_album(results, known_titles)
            if fuzzy_match:
                catalog.save_track_fingerprint(conn, collection_id, fuzzy_match, raw_fp)
                return fuzzy_match

    return None

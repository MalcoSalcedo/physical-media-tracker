import sqlite3

from app import catalog, fingerprint, track_matcher

DEFAULT_DURATIONS = (30, 60, 90)
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
    escalating clip length, falling back to an album-constrained fuzzy
    AcoustID match if nothing is cached yet for that clip (see ADR-002).
    A longer clip is only recorded if the previous, shorter one came back
    with no usable candidate - most plays should resolve at the shortest
    length once a few tracks have been cached locally.
    """
    if record_fn is None:
        record_fn = fingerprint.record_clip

    known_titles = [t["title"] for t in catalog.get_tracks(conn, collection_id)]

    for duration in durations:
        samples = record_fn(duration)
        raw_fp = fingerprint.raw_fingerprint(samples, sample_rate)

        cached_match = catalog.find_cached_match(conn, collection_id, raw_fp)
        if cached_match:
            return cached_match

        results = fingerprint.identify_clip(samples, sample_rate, api_key)
        fuzzy_match = track_matcher.match_against_album(results, known_titles)
        if fuzzy_match:
            catalog.save_track_fingerprint(conn, collection_id, fuzzy_match, raw_fp)
            return fuzzy_match

    return None

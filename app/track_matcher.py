import difflib


def fuzzy_title_score(a: str, b: str) -> float:
    """Similarity ratio (0-1) between two track titles, tolerant of casing/punctuation."""
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def match_against_album(
    acoustid_results,
    known_track_titles: list[str],
    min_acoustid_score: float = 0.4,
    min_fuzzy_score: float = 0.6,
) -> str | None:
    """Pick the best-matching known track title from a set of AcoustID results.

    Unlike a blind AcoustID lookup, this doesn't need a single dominant
    high-confidence result - it accepts a lower-confidence candidate as
    long as its title fuzzy-matches one of the tracks on the currently
    selected album (see ADR-002). `acoustid_results` is an iterable of
    (score, recording_id, title, artist) tuples, as returned by
    `acoustid.match()`.
    """
    best: tuple[float, str] | None = None
    for score, _recording_id, title, _artist in acoustid_results:
        if not title or score < min_acoustid_score:
            continue
        for known_title in known_track_titles:
            fuzzy = fuzzy_title_score(title, known_title)
            if fuzzy >= min_fuzzy_score and (best is None or score > best[0]):
                best = (score, known_title)
    return best[1] if best else None

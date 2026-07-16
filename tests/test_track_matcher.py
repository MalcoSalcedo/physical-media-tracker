from app.track_matcher import fuzzy_title_score, match_against_album

ALBUM_TRACKS = ["Come Together", "Something", "Maxwell's Silver Hammer", "Oh! Darling"]


def test_fuzzy_title_score_exact_match_is_one():
    assert fuzzy_title_score("Come Together", "Come Together") == 1.0


def test_fuzzy_title_score_ignores_case_and_whitespace():
    assert fuzzy_title_score("  COME TOGETHER  ", "come together") == 1.0


def test_fuzzy_title_score_of_unrelated_titles_is_low():
    assert fuzzy_title_score("Come Together", "Octopus's Garden") < 0.5


def test_high_confidence_exact_match_is_accepted():
    results = [(0.97, "rid-1", "Come Together", "The Beatles")]
    assert match_against_album(results, ALBUM_TRACKS) == "Come Together"


def test_low_confidence_result_accepted_if_title_matches_album_track():
    # This is the whole point of album-constrained matching: a score that
    # would be worthless against the full AcoustID universe is trustworthy
    # once we know the answer has to be one of a handful of known tracks.
    results = [(0.45, "rid-1", "Something", "The Beatles")]
    assert match_against_album(results, ALBUM_TRACKS) == "Something"


def test_result_below_min_acoustid_score_is_rejected_even_with_exact_title():
    results = [(0.1, "rid-1", "Something", "The Beatles")]
    assert match_against_album(results, ALBUM_TRACKS) is None


def test_result_above_threshold_but_not_on_album_is_rejected():
    results = [(0.9, "rid-1", "Bohemian Rhapsody", "Queen")]
    assert match_against_album(results, ALBUM_TRACKS) is None


def test_picks_highest_scoring_candidate_among_multiple_album_matches():
    results = [
        (0.5, "rid-1", "Something", "The Beatles"),
        (0.8, "rid-2", "Oh! Darling", "The Beatles"),
    ]
    assert match_against_album(results, ALBUM_TRACKS) == "Oh! Darling"


def test_ignores_candidates_with_missing_title():
    results = [(0.9, "rid-1", None, None)]
    assert match_against_album(results, ALBUM_TRACKS) is None


def test_empty_results_returns_none():
    assert match_against_album([], ALBUM_TRACKS) is None


def test_minor_title_formatting_differences_still_match():
    results = [(0.5, "rid-1", "maxwell's silver hammer", "The Beatles")]
    assert match_against_album(results, ALBUM_TRACKS) == "Maxwell's Silver Hammer"

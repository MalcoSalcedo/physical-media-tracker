import random

from app.local_match import decode_fingerprint, encode_fingerprint, similarity

random.seed(42)


def _random_fingerprint(length: int) -> list[int]:
    return [random.getrandbits(32) for _ in range(length)]


def test_identical_fingerprints_score_one():
    fp = _random_fingerprint(200)
    assert similarity(fp, fp) == 1.0


def test_unrelated_random_fingerprints_score_low():
    a = _random_fingerprint(200)
    b = _random_fingerprint(200)
    assert similarity(a, b) < 0.1


def test_shifted_fingerprint_still_matches_via_alignment():
    a = _random_fingerprint(300)
    # b is a's tail, shifted by 5 - simulates two recordings starting at
    # slightly different points but overlapping in content.
    b = a[5:] + _random_fingerprint(5)
    assert similarity(a, b) > 0.8


def test_minor_bit_differences_still_match():
    a = _random_fingerprint(200)
    # Flip exactly one bit per element - within the tolerated bit-error
    # margin, simulating small acoustic differences between two recordings
    # of the same track.
    b = [x ^ 1 for x in a]
    assert similarity(a, b) > 0.9


def test_empty_fingerprint_scores_zero():
    assert similarity([], _random_fingerprint(50)) == 0.0
    assert similarity(_random_fingerprint(50), []) == 0.0
    assert similarity([], []) == 0.0


def test_encode_decode_roundtrip():
    fp = _random_fingerprint(50)
    assert decode_fingerprint(encode_fingerprint(fp)) == fp

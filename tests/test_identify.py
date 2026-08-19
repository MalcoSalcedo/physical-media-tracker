import sqlite3
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from app import catalog, identify

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


@pytest.fixture
def album(conn):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(
        conn,
        item_id,
        [
            {"title": "15 Step", "duration_seconds": 237},
            {"title": "Bodysnatchers", "duration_seconds": 242},
        ],
    )
    return item_id


def _recorder(calls):
    """A fake record_fn that records which clip durations it was asked
    for, and returns loud (non-silent) real audio long enough to match
    that duration - so gap-trim detection sees nothing to trim unless a
    test deliberately builds a clip with an internal transition."""

    def record(duration):
        calls.append(duration)
        return np.full(int(duration * identify.SAMPLE_RATE), 1000, dtype=np.int16)

    return record


def test_returns_cached_match_without_calling_acoustid(conn, album):
    catalog.save_track_fingerprint(conn, album, "15 Step", [1, 2, 3])
    calls = []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[1, 2, 3]),
        patch("app.identify.fingerprint.compressed_fingerprint") as compressed_mock,
        patch("app.identify.fingerprint.lookup_with_duration") as lookup_mock,
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "15 Step"
    compressed_mock.assert_not_called()
    lookup_mock.assert_not_called()
    assert calls == [20]  # only tried the shortest clip length


def test_tries_each_known_track_duration_until_one_matches(conn, album):
    """The core new behavior: AcoustID needs a duration close to the true
    track length, so we try each of the album's known durations (see
    ADR-003), not just the clip's own recorded length."""
    calls = []
    tried_durations = []

    def fake_lookup(compressed_fp, duration, api_key):
        tried_durations.append(duration)
        if duration == 242:  # Bodysnatchers' real duration
            return [(0.9, "rid-1", "Bodysnatchers", "Radiohead")]
        return []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[9, 9, 9]),
        patch("app.identify.fingerprint.compressed_fingerprint", return_value="fp-data"),
        patch("app.identify.fingerprint.lookup_with_duration", side_effect=fake_lookup),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "Bodysnatchers"
    assert calls == [20]
    # tried 15 Step's duration (237) first (no match), then Bodysnatchers' (242)
    assert tried_durations == [237, 242]
    assert catalog.find_cached_match(conn, album, [9, 9, 9]) == "Bodysnatchers"


def test_falls_back_to_clips_own_duration_after_known_durations_fail(conn, album):
    calls = []
    tried_durations = []

    def fake_lookup(compressed_fp, duration, api_key):
        tried_durations.append(duration)
        if duration == 20:  # the clip's own honest duration, tried last
            return [(0.5, "rid-1", "15 Step", "Radiohead")]
        return []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[0, 0, 0]),
        patch("app.identify.fingerprint.compressed_fingerprint", return_value="fp-data"),
        patch("app.identify.fingerprint.lookup_with_duration", side_effect=fake_lookup),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "15 Step"
    assert tried_durations == [237, 242, 20]


def test_escalates_to_longer_clip_when_every_duration_guess_fails(conn, album):
    calls = []

    def fake_lookup(compressed_fp, duration, api_key):
        return []  # nothing ever matches at the short clip length

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[0, 0, 0]),
        patch("app.identify.fingerprint.compressed_fingerprint", return_value="fp-data"),
        patch("app.identify.fingerprint.lookup_with_duration", side_effect=fake_lookup),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result is None
    assert calls == [20, 45, 90]  # tried every configured clip length


def _clip_with_internal_transition(loud_seconds, silent_seconds, more_loud_seconds):
    """Builds a clip shaped like a recording that ran past a track's end:
    loud audio, a real silent gap, then more loud audio (the next track)."""
    sr = identify.SAMPLE_RATE
    loud = np.full(int(loud_seconds * sr), 1000, dtype=np.int16)
    silent = np.zeros(int(silent_seconds * sr), dtype=np.int16)
    more_loud = np.full(int(more_loud_seconds * sr), 1000, dtype=np.int16)
    return np.concatenate([loud, silent, more_loud])


def test_trims_clip_at_an_internal_track_transition(conn, album):
    # A clip that runs past the current track's end into a real silent gap
    # and then the next track must be trimmed to just the clean leading
    # portion before fingerprinting - otherwise the fingerprint blends two
    # songs and matches neither. Mirrors the real failure (2026-08-19): a
    # 90s clip recorded partway into a 133s track running past its end.
    clip = _clip_with_internal_transition(loud_seconds=5, silent_seconds=1.5, more_loud_seconds=3)
    tried_durations = []

    def fake_lookup(compressed_fp, duration, api_key):
        tried_durations.append(duration)
        return []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[0, 0, 0]) as raw_fp_mock,
        patch("app.identify.fingerprint.compressed_fingerprint", return_value="fp-data"),
        patch("app.identify.fingerprint.lookup_with_duration", side_effect=fake_lookup),
    ):
        identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=lambda duration: clip, durations=(20,)
        )

    trimmed_samples = raw_fp_mock.call_args[0][0]
    assert len(trimmed_samples) == 5 * identify.SAMPLE_RATE  # only the leading 5s, not the full 9.5s
    assert tried_durations[-1] == pytest.approx(5.0)  # the trimmed length, not the requested 20s


def test_does_not_trim_a_clip_with_no_internal_transition(conn, album):
    # A long track with no boundary crossing (e.g. a fresh cold-start
    # identify on track 1) must get the *full* clip - this regressed once
    # already (2026-08-19) when a blanket per-album duration cap broke
    # matching for a track that genuinely needed the full-length clip.
    calls = []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[1, 2, 3]) as raw_fp_mock,
        patch("app.identify.fingerprint.compressed_fingerprint", return_value="fp-data"),
        patch(
            "app.identify.fingerprint.lookup_with_duration",
            return_value=[(0.9, "rid-1", "Bodysnatchers", "Radiohead")],
        ),
    ):
        identify.identify_current_track(conn, album, "fake-api-key", record_fn=_recorder(calls))

    untouched_samples = raw_fp_mock.call_args[0][0]
    assert len(untouched_samples) == 20 * identify.SAMPLE_RATE  # nothing trimmed off

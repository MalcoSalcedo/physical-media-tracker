import sqlite3
from pathlib import Path
from unittest.mock import patch

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
    """A fake record_fn that records which clip durations it was asked for."""

    def record(duration):
        calls.append(duration)
        return f"samples-for-{duration}s"

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

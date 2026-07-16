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
    catalog.save_tracks(conn, item_id, [{"title": "15 Step"}, {"title": "Bodysnatchers"}])
    return item_id


def _recorder(calls):
    """A fake record_fn that records which durations it was asked for."""

    def record(duration):
        calls.append(duration)
        return f"samples-for-{duration}s"

    return record


def test_returns_cached_match_without_calling_acoustid(conn, album):
    catalog.save_track_fingerprint(conn, album, "15 Step", [1, 2, 3])
    calls = []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[1, 2, 3]),
        patch("app.identify.fingerprint.identify_clip") as identify_clip_mock,
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "15 Step"
    identify_clip_mock.assert_not_called()
    assert calls == [30]  # only tried the shortest duration


def test_falls_back_to_fuzzy_acoustid_match_when_nothing_cached(conn, album):
    calls = []
    acoustid_results = [(0.5, "rid-1", "Bodysnatchers", "Radiohead")]

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[9, 9, 9]),
        patch("app.identify.fingerprint.identify_clip", return_value=acoustid_results),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "Bodysnatchers"
    assert calls == [30]
    # the match should now be cached for next time
    assert catalog.find_cached_match(conn, album, [9, 9, 9]) == "Bodysnatchers"


def test_escalates_to_longer_clip_when_shorter_one_fails(conn, album):
    calls = []

    def fake_identify_clip(samples, sample_rate, api_key):
        if samples == "samples-for-30s":
            return []  # no usable candidate at the short length
        return [(0.6, "rid-1", "15 Step", "Radiohead")]

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[0, 0, 0]),
        patch("app.identify.fingerprint.identify_clip", side_effect=fake_identify_clip),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result == "15 Step"
    assert calls == [30, 60]  # stopped as soon as it got a match


def test_returns_none_when_no_duration_yields_a_match(conn, album):
    calls = []

    with (
        patch("app.identify.fingerprint.raw_fingerprint", return_value=[0, 0, 0]),
        patch("app.identify.fingerprint.identify_clip", return_value=[]),
    ):
        result = identify.identify_current_track(
            conn, album, "fake-api-key", record_fn=_recorder(calls)
        )

    assert result is None
    assert calls == [30, 60, 90]  # tried every configured duration

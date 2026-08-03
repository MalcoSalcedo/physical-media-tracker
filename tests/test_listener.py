import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import listener
from app import catalog
from app.gap_detector import GapDetector

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


@pytest.fixture
def detector():
    return GapDetector(sample_rate=44100)


@pytest.fixture
def stopped_detector():
    # Tiny threshold so a single silent gap-check clip is enough to fire it
    # in tests, instead of needing ~30s worth of real STOPPED_SILENCE_SECONDS
    # chunks like production uses.
    return GapDetector(sample_rate=44100, min_gap_seconds=0.001)


def _quiet_gap_check():
    """A gap_check_fn with real signal that never reports a gap (below
    GapDetector's min duration) - "quiet" from the gap detector's
    perspective (no transitions), not literally silent."""
    import numpy as np

    return np.full(100, 1000, dtype="int16")


def _silent_gap_check():
    """A gap_check_fn simulating actual silence - e.g. the CD player hasn't
    started playing yet."""
    import numpy as np

    return np.zeros(100, dtype="int16")


def test_tick_does_nothing_when_no_album_selected(conn, detector):
    action = listener.tick(conn, "fake-key", detector, gap_check_fn=_quiet_gap_check)
    assert action is None


def test_tick_identifies_when_no_track_known_yet(conn, detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)

    with patch("listener.identify.identify_current_track", return_value="15 Step") as identify_mock:
        action = listener.tick(conn, "fake-key", detector, gap_check_fn=_quiet_gap_check)

    assert action == listener.timer.IDENTIFY
    identify_mock.assert_called_once()
    assert catalog.get_now_playing(conn)["track_title"] == "15 Step"


def test_tick_waits_instead_of_identifying_when_no_track_known_and_silent(conn, detector):
    # This is the "selected the album but haven't pressed play yet" case -
    # don't burn a full identify attempt recording silence.
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)

    with patch("listener.identify.identify_current_track") as identify_mock:
        action = listener.tick(conn, "fake-key", detector, gap_check_fn=_silent_gap_check)

    assert action == listener.timer.WAIT
    identify_mock.assert_not_called()
    assert catalog.get_now_playing(conn)["track_title"] is None


def test_tick_does_not_update_now_playing_when_identify_finds_nothing(conn, detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)

    with patch("listener.identify.identify_current_track", return_value=None):
        listener.tick(conn, "fake-key", detector, gap_check_fn=_quiet_gap_check)

    assert catalog.get_now_playing(conn)["track_title"] is None


def test_tick_advances_to_next_track_once_duration_elapses(conn, detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(
        conn,
        item_id,
        [
            {"title": "15 Step", "duration_seconds": 237},
            {"title": "Bodysnatchers", "duration_seconds": 242},
        ],
    )
    catalog.set_active_album(conn, item_id)
    catalog.update_current_track(conn, item_id, "15 Step", "fingerprint")

    far_future = datetime.utcnow() + timedelta(seconds=300)
    with patch("listener.identify.identify_current_track") as identify_mock:
        action = listener.tick(
            conn, "fake-key", detector, gap_check_fn=_quiet_gap_check, now=far_future
        )

    assert action == listener.timer.ADVANCE
    identify_mock.assert_not_called()
    assert catalog.get_now_playing(conn)["track_title"] == "Bodysnatchers"


def test_tick_waits_when_track_still_within_its_duration(conn, detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)
    catalog.update_current_track(conn, item_id, "15 Step", "fingerprint")

    soon = datetime.utcnow() + timedelta(seconds=10)
    with patch("listener.identify.identify_current_track") as identify_mock:
        action = listener.tick(
            conn, "fake-key", detector, gap_check_fn=_quiet_gap_check, now=soon
        )

    assert action == listener.timer.WAIT
    identify_mock.assert_not_called()
    assert catalog.get_now_playing(conn)["track_title"] == "15 Step"


def test_tick_marks_stopped_when_stopped_detector_fires_while_playing(conn, detector, stopped_detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)
    catalog.update_current_track(conn, item_id, "15 Step", "fingerprint")

    with patch("listener.identify.identify_current_track") as identify_mock:
        action = listener.tick(
            conn,
            "fake-key",
            detector,
            stopped_detector=stopped_detector,
            gap_check_fn=_silent_gap_check,
        )

    assert action == listener.timer.WAIT
    identify_mock.assert_not_called()
    current = catalog.get_now_playing(conn)
    assert current["status"] == "stopped"
    assert current["track_title"] == "15 Step"  # last-known title kept for display


def test_tick_reidentifies_when_stopped_and_signal_resumes(conn, detector, stopped_detector):
    item_id = catalog.save_item(conn, artist="Radiohead", album="In Rainbows", format="Vinyl")
    catalog.save_tracks(conn, item_id, [{"title": "15 Step", "duration_seconds": 237}])
    catalog.set_active_album(conn, item_id)
    catalog.update_current_track(conn, item_id, "15 Step", "fingerprint")
    catalog.mark_stopped(conn, item_id)

    with patch("listener.identify.identify_current_track", return_value="Bodysnatchers") as identify_mock:
        action = listener.tick(
            conn,
            "fake-key",
            detector,
            stopped_detector=stopped_detector,
            gap_check_fn=_quiet_gap_check,
        )

    assert action == listener.timer.IDENTIFY
    identify_mock.assert_called_once()
    current = catalog.get_now_playing(conn)
    assert current["status"] == "playing"
    assert current["track_title"] == "Bodysnatchers"

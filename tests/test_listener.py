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


def _quiet_gap_check():
    """A gap_check_fn that never reports a gap (below GapDetector's min duration)."""
    import numpy as np

    return np.full(100, 1000, dtype="int16")


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

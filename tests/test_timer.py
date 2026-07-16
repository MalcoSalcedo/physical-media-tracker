from datetime import datetime, timedelta

from app.timer import ADVANCE, IDENTIFY, WAIT, decide_next_action, next_track_title

TRACKS = [
    {"title": "15 Step", "duration_seconds": 237},
    {"title": "Bodysnatchers", "duration_seconds": 242},
    {"title": "Nude", "duration_seconds": 255},
]


def test_next_track_title_returns_the_following_track():
    assert next_track_title(TRACKS, "15 Step") == "Bodysnatchers"


def test_next_track_title_returns_none_at_end_of_album():
    assert next_track_title(TRACKS, "Nude") is None


def test_next_track_title_returns_none_for_unknown_title():
    assert next_track_title(TRACKS, "Some Other Song") is None


def test_decide_next_action_identifies_when_no_track_known_yet():
    action = decide_next_action(
        current_track_title=None,
        started_at=None,
        tracks=TRACKS,
        gap_detected=False,
        now=datetime(2026, 1, 1, 12, 0, 0),
    )
    assert action == IDENTIFY


def test_decide_next_action_waits_before_track_duration_elapses():
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=started_at,
        tracks=TRACKS,
        gap_detected=False,
        now=started_at + timedelta(seconds=100),
    )
    assert action == WAIT


def test_decide_next_action_advances_once_track_duration_elapses_with_no_gap():
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=started_at,
        tracks=TRACKS,
        gap_detected=False,
        now=started_at + timedelta(seconds=300),
    )
    assert action == ADVANCE


def test_decide_next_action_advances_on_gap_at_expected_track_boundary():
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=started_at,
        tracks=TRACKS,
        gap_detected=True,
        now=started_at + timedelta(seconds=237),
    )
    assert action == ADVANCE


def test_decide_next_action_identifies_on_gap_before_expected_boundary():
    # A gap firing well before the track should have ended means a skip -
    # trust neither the timer nor track order, re-identify from scratch.
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=started_at,
        tracks=TRACKS,
        gap_detected=True,
        now=started_at + timedelta(seconds=30),
    )
    assert action == IDENTIFY


def test_decide_next_action_identifies_on_gap_when_duration_unknown():
    tracks_no_duration = [{"title": "15 Step", "duration_seconds": None}]
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        tracks=tracks_no_duration,
        gap_detected=True,
        now=datetime(2026, 1, 1, 12, 5, 0),
    )
    assert action == IDENTIFY


def test_decide_next_action_waits_when_duration_unknown_and_no_gap():
    tracks_no_duration = [{"title": "15 Step", "duration_seconds": None}]
    action = decide_next_action(
        current_track_title="15 Step",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        tracks=tracks_no_duration,
        gap_detected=False,
        now=datetime(2026, 1, 1, 12, 5, 0),
    )
    assert action == WAIT

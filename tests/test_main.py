from datetime import datetime, timedelta

from app.main import _timeago


def _sqlite_format(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def test_timeago_none_returns_empty_string():
    assert _timeago(None) == ""


def test_timeago_just_now():
    now = _sqlite_format(datetime.utcnow())
    assert _timeago(now) == "just now"


def test_timeago_minutes():
    five_min_ago = _sqlite_format(datetime.utcnow() - timedelta(minutes=5))
    assert _timeago(five_min_ago) == "5m ago"


def test_timeago_hours():
    two_hours_ago = _sqlite_format(datetime.utcnow() - timedelta(hours=2))
    assert _timeago(two_hours_ago) == "2h ago"


def test_timeago_days():
    three_days_ago = _sqlite_format(datetime.utcnow() - timedelta(days=3))
    assert _timeago(three_days_ago) == "3d ago"

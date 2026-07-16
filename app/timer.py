from datetime import datetime, timedelta

IDENTIFY = "identify"
ADVANCE = "advance"
WAIT = "wait"


def next_track_title(tracks: list[dict], current_title: str) -> str | None:
    """The track after `current_title` in album order, or None at the end."""
    titles = [t["title"] for t in tracks]
    if current_title not in titles:
        return None
    idx = titles.index(current_title)
    if idx + 1 < len(titles):
        return titles[idx + 1]
    return None


def decide_next_action(
    *,
    current_track_title: str | None,
    started_at: datetime | None,
    tracks: list[dict],
    gap_detected: bool,
    now: datetime,
) -> str:
    """Decide what the listener should do on this tick.

    IDENTIFY: no track is known yet, or a gap fired earlier than the
    current track's known runtime would predict - that means a skip, so
    trust neither the timer nor track order and re-identify from scratch.
    ADVANCE: the current track's known duration has elapsed with no early
    gap - safe to just move to the next track in album order, no
    recording/API call needed.
    WAIT: nothing to do yet.
    """
    if current_track_title is None:
        return IDENTIFY

    track = next((t for t in tracks if t["title"] == current_track_title), None)
    duration = track["duration_seconds"] if track else None

    if gap_detected:
        if duration and started_at and now < started_at + timedelta(seconds=duration):
            # Gap fired before the track was expected to end - a skip.
            return IDENTIFY
        # Gap fired at roughly the expected boundary - a normal track change.
        return ADVANCE if duration else IDENTIFY

    if duration and started_at and now >= started_at + timedelta(seconds=duration):
        return ADVANCE

    return WAIT

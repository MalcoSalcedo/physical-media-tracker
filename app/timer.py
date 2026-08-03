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
    status: str,
    started_at: datetime | None,
    tracks: list[dict],
    gap_detected: bool,
    has_signal: bool,
    now: datetime,
) -> str:
    """Decide what the listener should do on this tick.

    IDENTIFY: no track is known yet (or playback is believed stopped)
    *and* audio is actually playing, or a gap fired at all. Any detected
    gap always triggers a full re-identification rather than guessing
    whether it "looks like" a normal transition vs. a skip -
    re-identification is position-independent (it searches the whole
    album, not just "the next track"), so it handles forward skips,
    backward skips, and rapid back-and-forth sequences the same way. This
    used to try to distinguish an "early" gap (a skip) from an "on-time"
    one (a normal transition, safe to just advance without a fresh
    AcoustID call), but that created a real edge case: a skip whose gap
    happened to land right around when the current track's stored
    duration was also about to naturally elapse would get misclassified
    as a normal advance and show the wrong track. Not worth it now that
    identification is fast (usually resolves on the first ~20s clip - see
    ADR-003) - a few extra AcoustID calls on ordinary track changes is a
    small price for never mis-tracking a skip.
    ADVANCE: the current track's known duration has elapsed with no gap
    at all, *and* the input currently has signal (e.g. a seamless mix
    with no silence between tracks) - safe to just move to the next
    track in album order, no recording/API call needed. Requiring
    has_signal here matters: without it, a track that stops playing
    partway through (not at a clean boundary) would eventually have its
    stored duration "expire" and get silently, wrongly advanced to
    whatever's next in track order even though nothing is actually
    playing.
    WAIT: nothing to do yet. Also covers the gap between selecting an
    album and actually pressing play - there's no signal linking the CD
    player to this software, so `has_signal` (a cheap energy check) is
    what keeps the listener from burning a full identify attempt on
    silence before playback has even started. The same has_signal gate
    is what lets a `status == "stopped"` track sit quietly instead of
    repeatedly retrying identification against silence.
    """
    if current_track_title is None or status == "stopped":
        return IDENTIFY if has_signal else WAIT

    if gap_detected:
        return IDENTIFY

    if not has_signal:
        return WAIT

    track = next((t for t in tracks if t["title"] == current_track_title), None)
    duration = track["duration_seconds"] if track else None
    if duration and started_at and now >= started_at + timedelta(seconds=duration):
        return ADVANCE

    return WAIT

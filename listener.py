#!/usr/bin/env python
"""Long-running listener: identifies what's currently playing and keeps
`now_playing`/`history` up to date.

See docs/adr/ADR-002 for the overall design (album pre-selection, gap
detection, duration-timer advancement, album-constrained fuzzy matching,
local fingerprint cache). Run directly for local testing; on the Pi this
is what `listener.service` runs headless.
"""

import argparse
import os
import sqlite3
import time
from datetime import datetime

from dotenv import load_dotenv

from app import catalog, fingerprint, identify, timer
from app.db import get_connection
from app.gap_detector import GapDetector, rms

GAP_CHECK_CLIP_SECONDS = 2
# Deliberately short: gap-check recording (~2s) plus this sleep is the
# listener's *entire* window of awareness between samples. A 5s gap here
# meant real inter-track silence (often only 1-3s long) had a good chance
# of falling entirely in the dead zone and never being seen at all -
# confirmed happening in real testing (see DEVLOG, 2026-08-01). Keeping
# this near-zero instead of adding a background thread trades a bit of
# CPU/device churn for closing that blind spot with a one-line change.
POLL_INTERVAL_SECONDS = 0.5
SAMPLE_RATE = 44100
# How long the input has to be continuously silent before we consider
# playback actually stopped (vs. just a normal 1-3s inter-track gap).
# Reuses GapDetector with a much longer threshold, fed the same gap-check
# clips - no separate recording needed.
STOPPED_SILENCE_SECONDS = 30


def _parse_started_at(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def tick(
    conn: sqlite3.Connection,
    api_key: str,
    detector: GapDetector,
    *,
    stopped_detector: GapDetector | None = None,
    pending_gap: dict | None = None,
    gap_check_fn=None,
    record_fn=None,
    sample_rate: int = SAMPLE_RATE,
    now: datetime | None = None,
) -> str | None:
    """Run one iteration of the listener loop. Returns the action taken, if any."""
    current = catalog.get_now_playing(conn)
    if current is None:
        return None

    if pending_gap is None:
        pending_gap = {}

    collection_id = current["collection_id"]
    tracks = [dict(t) for t in catalog.get_tracks(conn, collection_id)]
    started_at = _parse_started_at(current["started_at"]) if current["track_title"] else None
    status = current["status"]

    gap_clip = gap_check_fn() if gap_check_fn else fingerprint.record_clip(GAP_CHECK_CLIP_SECONDS)
    gap_fired = detector.process_chunk(gap_clip)
    has_signal = rms(gap_clip) >= detector.silence_threshold

    # A gap firing means silence just crossed the threshold - which, by
    # construction, is exactly when there's nothing to fingerprint yet.
    # Recording and querying AcoustID right then wastes the whole escalating
    # clip-length sweep on silence (confirmed live: ~176s burned on nothing
    # during a real pause) and, worse, eats the exact window the stopped-
    # detector needs to reach its own threshold. So a gap only arms a
    # "waiting to re-identify" flag; the actual re-identify is deferred
    # until audio is actually present again, which is also the only moment
    # it could possibly succeed.
    if gap_fired:
        pending_gap["waiting_for_signal"] = True
    gap_detected = pending_gap.get("waiting_for_signal", False) and has_signal
    if gap_detected:
        pending_gap["waiting_for_signal"] = False

    if stopped_detector is not None:
        stopped_fired = stopped_detector.process_chunk(gap_clip)
        if stopped_fired and status == "playing":
            catalog.mark_stopped(conn, collection_id)
            status = "stopped"

    action = timer.decide_next_action(
        current_track_title=current["track_title"],
        status=status,
        started_at=started_at,
        tracks=tracks,
        gap_detected=gap_detected,
        has_signal=has_signal,
        # SQLite's datetime('now') (used for started_at) is UTC, not local time.
        now=now or datetime.utcnow(),
    )

    if action == timer.IDENTIFY:
        match = identify.identify_current_track(
            conn, collection_id, api_key, record_fn=record_fn, sample_rate=sample_rate
        )
        if match:
            catalog.update_current_track(conn, collection_id, match, "fingerprint")
    elif action == timer.ADVANCE:
        next_title = timer.next_track_title(tracks, current["track_title"])
        if next_title:
            catalog.update_current_track(conn, collection_id, next_title, "fingerprint")

    return action


def run(api_key: str, device: int | None = None, poll_interval: float = POLL_INTERVAL_SECONDS) -> None:
    conn = get_connection()
    detector = GapDetector(SAMPLE_RATE)
    stopped_detector = GapDetector(SAMPLE_RATE, min_gap_seconds=STOPPED_SILENCE_SECONDS)
    pending_gap: dict = {}

    def record_fn(duration):
        return fingerprint.record_clip(duration, sample_rate=SAMPLE_RATE, device=device)

    def gap_check_fn():
        return record_fn(GAP_CHECK_CLIP_SECONDS)

    print("Listener running. Waiting for an album to be selected...")
    while True:
        try:
            action = tick(
                conn,
                api_key,
                detector,
                stopped_detector=stopped_detector,
                pending_gap=pending_gap,
                gap_check_fn=gap_check_fn,
                record_fn=record_fn,
            )
            if action:
                print(f"[{datetime.now()}] {action}")
        except Exception as exc:  # keep the daemon alive on transient errors (network, mic, etc.)
            print(f"[{datetime.now()}] tick failed: {exc!r}")
        time.sleep(poll_interval)


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device", type=int, default=None, help="Input device index (see sounddevice.query_devices())"
    )
    parser.add_argument("--poll-interval", type=float, default=POLL_INTERVAL_SECONDS)
    args = parser.parse_args()

    run(os.environ["ACOUSTID_API_KEY"], device=args.device, poll_interval=args.poll_interval)

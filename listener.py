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
from app.gap_detector import GapDetector

GAP_CHECK_CLIP_SECONDS = 2
POLL_INTERVAL_SECONDS = 5
SAMPLE_RATE = 44100


def _parse_started_at(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def tick(
    conn: sqlite3.Connection,
    api_key: str,
    detector: GapDetector,
    *,
    gap_check_fn=None,
    record_fn=None,
    sample_rate: int = SAMPLE_RATE,
    now: datetime | None = None,
) -> str | None:
    """Run one iteration of the listener loop. Returns the action taken, if any."""
    current = catalog.get_now_playing(conn)
    if current is None:
        return None

    collection_id = current["collection_id"]
    tracks = [dict(t) for t in catalog.get_tracks(conn, collection_id)]
    started_at = _parse_started_at(current["started_at"]) if current["track_title"] else None

    gap_clip = gap_check_fn() if gap_check_fn else fingerprint.record_clip(GAP_CHECK_CLIP_SECONDS)
    gap_detected = detector.process_chunk(gap_clip)

    action = timer.decide_next_action(
        current_track_title=current["track_title"],
        started_at=started_at,
        tracks=tracks,
        gap_detected=gap_detected,
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


def run(api_key: str, device: int | None = None, poll_interval: int = POLL_INTERVAL_SECONDS) -> None:
    conn = get_connection()
    detector = GapDetector(SAMPLE_RATE)

    def record_fn(duration):
        return fingerprint.record_clip(duration, sample_rate=SAMPLE_RATE, device=device)

    def gap_check_fn():
        return record_fn(GAP_CHECK_CLIP_SECONDS)

    print("Listener running. Waiting for an album to be selected...")
    while True:
        try:
            action = tick(conn, api_key, detector, gap_check_fn=gap_check_fn, record_fn=record_fn)
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
    parser.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_SECONDS)
    args = parser.parse_args()

    run(os.environ["ACOUSTID_API_KEY"], device=args.device, poll_interval=args.poll_interval)

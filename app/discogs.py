import os

import requests

DISCOGS_SEARCH_URL = "https://api.discogs.com/database/search"
DISCOGS_RELEASE_URL = "https://api.discogs.com/releases/{id}"
USER_AGENT = "PhysicalMediaTracker/0.1 (+https://github.com/MalcoSalcedo/physical-media-tracker)"


def _auth_params() -> dict:
    token = os.environ.get("DISCOGS_TOKEN")
    return {"token": token} if token else {}


def search_by_barcode(barcode: str) -> dict | None:
    """Look up a release by barcode via the Discogs API. Returns None on no match."""
    params = {"barcode": barcode, **_auth_params()}

    response = requests.get(
        DISCOGS_SEARCH_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None

    release = results[0]
    artist, _, album = release.get("title", "").partition(" - ")
    formats = release.get("format", [])

    return {
        "artist": artist or "Unknown",
        "album": album or release.get("title", "Unknown"),
        "format": formats[0] if formats else "Unknown",
        "cover_art_url": release.get("cover_image") or None,
        "musicbrainz_id": None,
        "discogs_id": release.get("id"),
    }


def _parse_duration(duration: str) -> int | None:
    """Parse a Discogs "mm:ss" duration string into seconds."""
    if not duration or ":" not in duration:
        return None
    minutes, _, seconds = duration.partition(":")
    try:
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return None


def get_tracklist(discogs_id: str) -> list[dict]:
    """Fetch a release's tracklist from Discogs. Returns [] if unavailable."""
    response = requests.get(
        DISCOGS_RELEASE_URL.format(id=discogs_id),
        params=_auth_params(),
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    tracklist = response.json().get("tracklist", [])

    return [
        {
            "position": t.get("position"),
            "title": t.get("title") or "Unknown",
            "duration_seconds": _parse_duration(t.get("duration")),
        }
        for t in tracklist
        if t.get("type_") == "track" and t.get("title")
    ]

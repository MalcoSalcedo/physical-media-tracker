import os

import requests

DISCOGS_SEARCH_URL = "https://api.discogs.com/database/search"
USER_AGENT = "PhysicalMediaTracker/0.1 (+https://github.com/MalcoSalcedo/physical-media-tracker)"


def search_by_barcode(barcode: str) -> dict | None:
    """Look up a release by barcode via the Discogs API. Returns None on no match."""
    params = {"barcode": barcode}
    token = os.environ.get("DISCOGS_TOKEN")
    if token:
        params["token"] = token

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
    }

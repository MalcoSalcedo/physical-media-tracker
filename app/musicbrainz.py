import requests

MUSICBRAINZ_SEARCH_URL = "https://musicbrainz.org/ws/2/release/"
MUSICBRAINZ_RELEASE_URL = "https://musicbrainz.org/ws/2/release/{id}"
USER_AGENT = "PhysicalMediaTracker/0.1 (+https://github.com/MalcoSalcedo/physical-media-tracker)"


def search_by_barcode(barcode: str) -> dict | None:
    """Look up a release by barcode via the MusicBrainz API. Returns None on no match."""
    response = requests.get(
        MUSICBRAINZ_SEARCH_URL,
        params={"query": f"barcode:{barcode}", "fmt": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    releases = response.json().get("releases", [])
    if not releases:
        return None

    release = releases[0]
    artist_credits = release.get("artist-credit", [])
    artist = artist_credits[0]["name"] if artist_credits else "Unknown"
    media = release.get("media", [])
    mb_id = release.get("id")

    return {
        "artist": artist,
        "album": release.get("title", "Unknown"),
        "format": media[0]["format"] if media and media[0].get("format") else "Unknown",
        "cover_art_url": f"https://coverartarchive.org/release/{mb_id}/front" if mb_id else None,
        "musicbrainz_id": mb_id,
        "discogs_id": None,
    }


def get_tracklist(musicbrainz_id: str) -> list[dict]:
    """Fetch a release's tracklist from MusicBrainz. Returns [] if unavailable."""
    response = requests.get(
        MUSICBRAINZ_RELEASE_URL.format(id=musicbrainz_id),
        params={"inc": "recordings", "fmt": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    media = response.json().get("media", [])

    tracks = []
    for medium in media:
        for t in medium.get("tracks", []):
            length_ms = t.get("length")
            tracks.append(
                {
                    "position": t.get("number"),
                    "title": t.get("title") or "Unknown",
                    "duration_seconds": length_ms // 1000 if length_ms else None,
                }
            )
    return tracks

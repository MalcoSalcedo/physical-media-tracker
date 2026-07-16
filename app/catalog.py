import sqlite3

from app import discogs, local_match, musicbrainz


def lookup_barcode(barcode: str) -> dict | None:
    """Look up a barcode via Discogs, falling back to MusicBrainz."""
    match = discogs.search_by_barcode(barcode)
    if match is None:
        match = musicbrainz.search_by_barcode(barcode)
    return match


def save_item(
    conn: sqlite3.Connection,
    *,
    artist: str,
    album: str,
    format: str,
    barcode: str | None = None,
    cover_art_url: str | None = None,
    musicbrainz_id: str | None = None,
    discogs_id: str | None = None,
) -> int:
    """Insert a collection row and return its id."""
    cursor = conn.execute(
        """
        INSERT INTO collection (artist, album, format, barcode, cover_art_url, musicbrainz_id, discogs_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (artist, album, format, barcode, cover_art_url, musicbrainz_id, discogs_id),
    )
    conn.commit()
    return cursor.lastrowid


def list_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM collection ORDER BY date_added DESC").fetchall()


def get_item(conn: sqlite3.Connection, collection_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM collection WHERE id = ?", (collection_id,)).fetchone()


def fetch_tracklist(item: sqlite3.Row) -> list[dict]:
    """Fetch a release's tracklist from whichever source we matched it via."""
    if item["discogs_id"]:
        return discogs.get_tracklist(item["discogs_id"])
    if item["musicbrainz_id"]:
        return musicbrainz.get_tracklist(item["musicbrainz_id"])
    return []


def save_tracks(conn: sqlite3.Connection, collection_id: int, tracks: list[dict]) -> None:
    """Replace the stored tracklist for an album with a freshly fetched one."""
    conn.execute("DELETE FROM tracks WHERE collection_id = ?", (collection_id,))
    conn.executemany(
        """
        INSERT INTO tracks (collection_id, sort_order, position, title, duration_seconds)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (collection_id, i, t.get("position"), t["title"], t.get("duration_seconds"))
            for i, t in enumerate(tracks)
        ],
    )
    conn.commit()


def get_tracks(conn: sqlite3.Connection, collection_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tracks WHERE collection_id = ? ORDER BY sort_order", (collection_id,)
    ).fetchall()


def set_active_album(conn: sqlite3.Connection, collection_id: int) -> None:
    """Mark an album as selected/"now listening", pending track identification."""
    conn.execute(
        """
        INSERT INTO now_playing (id, collection_id, track_title, source)
        VALUES (1, ?, NULL, 'manual')
        ON CONFLICT (id) DO UPDATE SET
            collection_id = excluded.collection_id,
            track_title = NULL,
            started_at = datetime('now'),
            source = 'manual'
        """,
        (collection_id,),
    )
    conn.commit()


def save_track_fingerprint(
    conn: sqlite3.Connection, collection_id: int, track_title: str, raw_fingerprint: list[int]
) -> None:
    """Cache a confirmed track's own-mic fingerprint for fast local re-matching."""
    conn.execute(
        "UPDATE tracks SET cached_fingerprint = ? WHERE collection_id = ? AND title = ?",
        (local_match.encode_fingerprint(raw_fingerprint), collection_id, track_title),
    )
    conn.commit()


def find_cached_match(
    conn: sqlite3.Connection,
    collection_id: int,
    raw_fingerprint: list[int],
    min_similarity: float = 0.5,
) -> str | None:
    """Compare a freshly recorded clip against this album's cached fingerprints.

    Avoids AcoustID entirely when it hits: both sides of the comparison
    went through the same mic/room, so repeat plays of the same disc
    should score far more similar to each other than a mic recording ever
    would against a clean studio master.
    """
    rows = conn.execute(
        "SELECT title, cached_fingerprint FROM tracks "
        "WHERE collection_id = ? AND cached_fingerprint IS NOT NULL",
        (collection_id,),
    ).fetchall()

    best: tuple[float, str] | None = None
    for row in rows:
        cached = local_match.decode_fingerprint(row["cached_fingerprint"])
        score = local_match.similarity(raw_fingerprint, cached)
        if score >= min_similarity and (best is None or score > best[0]):
            best = (score, row["title"])
    return best[1] if best else None


def get_now_playing(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT now_playing.*, collection.artist, collection.album, collection.cover_art_url
        FROM now_playing
        JOIN collection ON collection.id = now_playing.collection_id
        WHERE now_playing.id = 1
        """
    ).fetchone()

import sqlite3

from app import discogs, musicbrainz


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
) -> int:
    """Insert a collection row and return its id."""
    cursor = conn.execute(
        """
        INSERT INTO collection (artist, album, format, barcode, cover_art_url, musicbrainz_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (artist, album, format, barcode, cover_art_url, musicbrainz_id),
    )
    conn.commit()
    return cursor.lastrowid


def list_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM collection ORDER BY date_added DESC").fetchall()

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collection (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    artist         TEXT NOT NULL,
    album          TEXT NOT NULL,
    format         TEXT NOT NULL,
    barcode        TEXT UNIQUE,
    cover_art_url  TEXT,
    musicbrainz_id TEXT,
    date_added     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Single-row table: id is always 1, holds whatever is currently playing.
CREATE TABLE IF NOT EXISTS now_playing (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    collection_id INTEGER REFERENCES collection(id) ON DELETE SET NULL,
    track_title   TEXT,
    started_at    TEXT NOT NULL DEFAULT (datetime('now')),
    source        TEXT NOT NULL CHECK (source IN ('fingerprint', 'manual'))
);

CREATE TABLE IF NOT EXISTS history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER REFERENCES collection(id) ON DELETE SET NULL,
    track_title   TEXT NOT NULL,
    played_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_history_played_at ON history(played_at);
CREATE INDEX IF NOT EXISTS idx_collection_barcode ON collection(barcode);

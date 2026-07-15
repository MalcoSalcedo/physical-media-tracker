import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema.sql"
DB_PATH = REPO_ROOT / "data" / "collection.db"


def _migrate(conn: sqlite3.Connection) -> None:
    """Patch columns added after a table already existed in the wild."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "collection" in tables:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(collection)")}
        if "discogs_id" not in columns:
            conn.execute("ALTER TABLE collection ADD COLUMN discogs_id TEXT")


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the database file and tables if they don't already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _migrate(conn)
        conn.executescript(SCHEMA_PATH.read_text())


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

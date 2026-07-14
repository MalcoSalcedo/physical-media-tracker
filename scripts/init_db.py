"""Initialize the SQLite database from schema.sql."""

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schema.sql"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "collection.db"


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()
    init_db(args.db_path)
    print(f"Initialized database at {args.db_path}")


if __name__ == "__main__":
    main()

"""Initialize the SQLite database from schema.sql.

The app also self-initializes its schema on startup (see app.db.init_db),
so this script is mainly useful for pointing at a non-default db path.
"""

import argparse
from pathlib import Path

from app.db import DB_PATH, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DB_PATH,
        help=f"Path to the SQLite database file (default: {DB_PATH})",
    )
    args = parser.parse_args()
    init_db(args.db_path)
    print(f"Initialized database at {args.db_path}")


if __name__ == "__main__":
    main()

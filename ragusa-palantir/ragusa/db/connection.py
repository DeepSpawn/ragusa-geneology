"""SQLite connection helper with WAL mode and foreign key enforcement."""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "ragusa.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with recommended settings.

    Args:
        db_path: Path to the database file. Defaults to data/ragusa.db.

    Returns:
        A sqlite3.Connection with WAL mode and foreign keys enabled.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn

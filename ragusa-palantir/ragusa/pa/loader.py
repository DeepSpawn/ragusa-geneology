"""Load politically active men CSV into the database."""

from __future__ import annotations

import csv
import os
import sqlite3


DEFAULT_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "politically_active_men.csv")


def load_pa_csv(conn: sqlite3.Connection, csv_path: str = DEFAULT_CSV_PATH) -> int:
    """Load politically_active_men.csv into the politically_active_men table.

    Idempotent: uses INSERT OR REPLACE keyed on the original PDF ID.

    Returns:
        Number of rows loaded.
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            conn.execute(
                "INSERT OR REPLACE INTO politically_active_men "
                "(id, surname, name, father, grandfather, hackenberg_number, "
                "entry_year, entry_source, end_year, end_type, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(row["id"]),
                    row["surname"],
                    row["name"],
                    row["father"] or None,
                    row["grandfather"] or None,
                    row["hackenberg_number"] or None,
                    row["entry_year"] or None,
                    row["entry_source"] or None,
                    row["end_year"] or None,
                    row["end_type"] or None,
                    row["notes"] or None,
                ),
            )
            count += 1

    conn.commit()
    return count

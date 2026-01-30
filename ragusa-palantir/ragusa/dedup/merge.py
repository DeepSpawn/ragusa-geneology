"""Merge confirmed duplicate persons.

Uses soft merge: the removed record is preserved with is_canonical=0
and canonical_id pointing to the kept record.
"""

from __future__ import annotations

import sqlite3


def merge_persons(
    conn: sqlite3.Connection,
    keep_id: int,
    remove_id: int,
    reviewer_notes: str = "",
) -> None:
    """Merge person remove_id into keep_id.

    The remove_id record is NOT deleted — it is preserved with
    is_canonical=0 for auditability.

    Steps:
        1. Mark remove_id as non-canonical, pointing to keep_id
        2. Re-point family references
        3. Copy missing names, notes, annotations
        4. Merge date ranges (take narrowest known range)
        5. Log the merge
    """
    # 1. Mark as non-canonical
    conn.execute(
        "UPDATE persons SET canonical_id = ?, is_canonical = 0 WHERE id = ?",
        (keep_id, remove_id),
    )

    # 2. Re-point family relationships
    conn.execute(
        "UPDATE families SET husband_id = ? WHERE husband_id = ?",
        (keep_id, remove_id),
    )
    conn.execute(
        "UPDATE families SET wife_id = ? WHERE wife_id = ?",
        (keep_id, remove_id),
    )
    conn.execute(
        "UPDATE family_children SET child_id = ? WHERE child_id = ?",
        (keep_id, remove_id),
    )

    # 3. Copy person_names that don't already exist
    existing_names = {
        row[0]
        for row in conn.execute("SELECT name_raw FROM person_names WHERE person_id = ?", (keep_id,))
    }
    for row in conn.execute(
        "SELECT name_type, given_name, surname, name_raw, source "
        "FROM person_names WHERE person_id = ?",
        (remove_id,),
    ):
        if row["name_raw"] not in existing_names:
            conn.execute(
                "INSERT INTO person_names "
                "(person_id, name_type, given_name, surname, name_raw, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    keep_id,
                    row["name_type"],
                    row["given_name"],
                    row["surname"],
                    row["name_raw"],
                    row["source"],
                ),
            )

    # Copy notes
    for row in conn.execute(
        "SELECT note_category, note_text, gedcom_level, line_number FROM notes WHERE person_id = ?",
        (remove_id,),
    ):
        conn.execute(
            "INSERT INTO notes (person_id, note_category, note_text, gedcom_level, line_number) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                keep_id,
                row["note_category"],
                row["note_text"],
                row["gedcom_level"],
                row["line_number"],
            ),
        )

    # Copy annotations
    conn.execute(
        "UPDATE annotations SET person_id = ? WHERE person_id = ?",
        (keep_id, remove_id),
    )

    # Copy source references
    conn.execute(
        "UPDATE source_references SET person_id = ? WHERE person_id = ?",
        (keep_id, remove_id),
    )

    # Copy events
    conn.execute(
        "UPDATE events SET person_id = ? WHERE person_id = ?",
        (keep_id, remove_id),
    )

    # 4. Merge date ranges — take the more specific info
    keep = conn.execute(
        "SELECT birth_year_min, birth_year_max, death_year_min, death_year_max "
        "FROM persons WHERE id = ?",
        (keep_id,),
    ).fetchone()
    remove = conn.execute(
        "SELECT birth_year_min, birth_year_max, death_year_min, death_year_max "
        "FROM persons WHERE id = ?",
        (remove_id,),
    ).fetchone()

    updates = {}
    if remove["birth_year_min"] is not None and keep["birth_year_min"] is None:
        updates["birth_year_min"] = remove["birth_year_min"]
        updates["birth_year_max"] = remove["birth_year_max"]
    if remove["death_year_min"] is not None and keep["death_year_min"] is None:
        updates["death_year_min"] = remove["death_year_min"]
        updates["death_year_max"] = remove["death_year_max"]

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE persons SET {set_clause} WHERE id = ?",
            list(updates.values()) + [keep_id],
        )

    # 5. Log the merge
    conn.execute(
        "INSERT OR REPLACE INTO dedup_candidates "
        "(person_a_id, person_b_id, score, status, reviewed_at, reviewer_notes) "
        "VALUES (?, ?, 1.0, 'confirmed_match', datetime('now'), ?)",
        (keep_id, remove_id, reviewer_notes),
    )

    conn.commit()

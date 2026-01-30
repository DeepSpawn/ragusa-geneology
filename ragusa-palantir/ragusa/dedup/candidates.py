"""Generate candidate duplicate pairs for deduplication.

Uses surname blocking: only compares persons from different source files
who share the same (or variant) surname.
"""

from __future__ import annotations

import sqlite3

# Known surname variants — map to canonical form
SURNAME_VARIANTS: dict[str, str] = {
    "Dersie": "Derse",
    "Dersa": "Derse",
    "Derze": "Derse",
    "Bodaca": "Bodacia",
    "Bodazza": "Bodacia",
    "Budazza": "Bodacia",
    "Menze": "Mence",
    "Meno": "Mence",
    "Goze": "Goce",
    "Prosulo": "Proculo",
}


def get_canonical_surname(surname: str) -> str:
    """Map a surname to its canonical form."""
    return SURNAME_VARIANTS.get(surname, surname)


def generate_candidates(
    conn: sqlite3.Connection,
    min_score: float = 0.0,
) -> list[dict]:
    """Generate candidate duplicate pairs from persons in different source files.

    Uses surname blocking: only compares persons sharing the same canonical
    surname across different source files.

    Returns:
        List of candidate dicts with person_a_id, person_b_id, and blocking info.
    """
    # Get all source file IDs
    source_files = [row[0] for row in conn.execute("SELECT id FROM source_files ORDER BY id")]

    if len(source_files) < 2:
        return []

    # Get persons grouped by canonical surname and source file
    persons_by_surname: dict[str, dict[int, list]] = {}

    for row in conn.execute(
        "SELECT id, source_file_id, given_name, surname, sex, "
        "birth_year_min, birth_year_max, death_year_min, death_year_max, name_raw "
        "FROM persons WHERE surname IS NOT NULL AND is_canonical = 1"
    ):
        canonical = get_canonical_surname(row["surname"])
        if canonical not in persons_by_surname:
            persons_by_surname[canonical] = {}
        sf = row["source_file_id"]
        if sf not in persons_by_surname[canonical]:
            persons_by_surname[canonical][sf] = []
        persons_by_surname[canonical][sf].append(dict(row))

    candidates: list[dict] = []

    for surname, by_source in persons_by_surname.items():
        source_ids = sorted(by_source.keys())
        # Compare persons across different source files
        for i in range(len(source_ids)):
            for j in range(i + 1, len(source_ids)):
                sf_a, sf_b = source_ids[i], source_ids[j]
                for pa in by_source[sf_a]:
                    for pb in by_source[sf_b]:
                        # Quick pre-filter: sex must match (if known)
                        if (
                            pa["sex"]
                            and pb["sex"]
                            and pa["sex"] != "U"
                            and pb["sex"] != "U"
                            and pa["sex"] != pb["sex"]
                        ):
                            continue

                        candidates.append(
                            {
                                "person_a_id": pa["id"],
                                "person_b_id": pb["id"],
                                "surname": surname,
                                "person_a": pa,
                                "person_b": pb,
                            }
                        )

    return candidates

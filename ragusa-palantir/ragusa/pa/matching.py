"""Candidate generation and scoring for PA-to-GEDCOM person matching."""

from __future__ import annotations

import sqlite3

# Reuse Latin root stripping from the dedup scoring module
_LATIN_SUFFIXES = ("us", "um", "a", "e", "o", "is", "ius", "io", "ia")


def _latin_root(name: str) -> str:
    """Strip common Latin suffixes to get a comparable root."""
    name = name.lower().strip()
    for suffix in sorted(_LATIN_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix) and len(name) - len(suffix) >= 3:
            return name[: -len(suffix)]
    return name


def _score_name(pa_name: str, gedcom_name: str) -> float:
    """Score given name similarity."""
    a = (pa_name or "").lower().strip()
    b = (gedcom_name or "").lower().strip()

    if not a or not b:
        return 0.3

    if a == b:
        return 1.0

    if a.startswith(b) or b.startswith(a):
        return 0.85

    root_a = _latin_root(a)
    root_b = _latin_root(b)
    if root_a == root_b and len(root_a) >= 3:
        return 0.9

    if len(a) >= 3 and len(b) >= 3 and a[:3] == b[:3]:
        return 0.7

    return 0.0


def _score_date(pa_end_year: str | None, pa_end_type: str | None, death_year: int | None) -> float:
    """Score date similarity between PA end_year and GEDCOM death_year.

    For end_type='Period', the person survived past 1490 — their death year
    should be >= the end year, so we adjust scoring accordingly.
    """
    if not pa_end_year or pa_end_year == "?" or death_year is None:
        return 0.5  # No data — neutral

    try:
        end_yr = int(pa_end_year)
    except ValueError:
        return 0.5

    if pa_end_type == "Period":
        # Person survived past study period. Death should be >= end_year.
        if death_year >= end_yr:
            return 0.8  # Good — died after period end
        diff = end_yr - death_year
        if diff <= 5:
            return 0.5  # Possible minor discrepancy
        return 0.1  # Died well before period end — poor match

    # For other end types, end_year approximates death year
    diff = abs(end_yr - death_year)
    if diff == 0:
        return 1.0
    if diff <= 2:
        return 0.9
    if diff <= 5:
        return 0.6
    if diff <= 10:
        return 0.3
    return 0.0


def _get_father_name(conn: sqlite3.Connection, person_id: int) -> str | None:
    """Get the given name of a person's father from the family tree."""
    row = conn.execute(
        "SELECT father.given_name "
        "FROM family_children fc "
        "JOIN families f ON fc.family_id = f.id "
        "JOIN persons father ON f.husband_id = father.id "
        "WHERE fc.child_id = ? "
        "LIMIT 1",
        (person_id,),
    ).fetchone()
    return row[0] if row else None


def _get_grandfather_name(conn: sqlite3.Connection, person_id: int) -> str | None:
    """Get the given name of a person's paternal grandfather."""
    # First get the father's person ID
    father_row = conn.execute(
        "SELECT f.husband_id "
        "FROM family_children fc "
        "JOIN families f ON fc.family_id = f.id "
        "WHERE fc.child_id = ? AND f.husband_id IS NOT NULL "
        "LIMIT 1",
        (person_id,),
    ).fetchone()

    if not father_row:
        return None

    father_id = father_row[0]
    return _get_father_name(conn, father_id)


def generate_pa_candidates(conn: sqlite3.Connection) -> list[dict]:
    """Generate candidate matches for unmatched PA entries.

    Uses surname blocking: for each PA entry, finds GEDCOM males with the
    same surname who could have been alive during the political career.

    The PA dataset covers 1440-1490, so we apply a global lifespan filter:
    persons must have plausibly been alive during that window.

    Returns:
        List of dicts with 'pa' and 'person' keys.
    """
    # Get all unmatched PA entries
    pa_rows = conn.execute(
        "SELECT id, surname, name, father, grandfather, hackenberg_number, "
        "entry_year, entry_source, end_year, end_type "
        "FROM politically_active_men "
        "WHERE match_status = 'unmatched'"
    ).fetchall()

    # Pre-load canonical male persons who could have been alive during 1440-1490.
    # Allow margin: born by 1475 (age 15 in 1490), died no earlier than 1430
    # (10yr margin before period start). Unknown dates pass through.
    persons_by_surname: dict[str, list[dict]] = {}
    for row in conn.execute(
        "SELECT id, given_name, surname, birth_year_min, birth_year_max, "
        "death_year_min, death_year_max "
        "FROM persons "
        "WHERE is_canonical = 1 AND sex = 'M' AND surname IS NOT NULL "
        "AND (birth_year_min IS NULL OR birth_year_min <= 1475) "
        "AND (death_year_min IS NULL OR death_year_min >= 1430)"
    ):
        surname = row["surname"]
        if surname not in persons_by_surname:
            persons_by_surname[surname] = []
        persons_by_surname[surname].append(dict(row))

    candidates = []

    for pa in pa_rows:
        pa_dict = dict(pa)
        surname = pa_dict["surname"]
        gedcom_persons = persons_by_surname.get(surname, [])

        # Parse PA years for pre-filtering
        try:
            entry_yr = int(pa_dict["entry_year"]) if pa_dict["entry_year"] and pa_dict["entry_year"] != "?" else None
        except ValueError:
            entry_yr = None
        try:
            end_yr = int(pa_dict["end_year"]) if pa_dict["end_year"] else None
        except ValueError:
            end_yr = None

        for person in gedcom_persons:
            # Pre-filter: skip if person clearly died before PA entry
            if entry_yr and person["death_year_min"] and person["death_year_min"] < entry_yr - 10:
                continue
            # Pre-filter: skip if person born too late to have been active.
            # Allow 10yr margin for GEDCOM birth-year estimation error.
            if entry_yr and person["birth_year_min"] and person["birth_year_min"] > entry_yr + 10:
                continue

            candidates.append({"pa": pa_dict, "person": person})

    return candidates


def score_pa_match(
    conn: sqlite3.Connection, pa_row: dict, person: dict
) -> dict:
    """Score a PA entry against a GEDCOM person.

    Returns:
        Dict with 'score', 'name_score', 'father_score', 'date_score',
        'grandfather_score'.
    """
    # Name: 0.30
    name_score = _score_name(pa_row["name"], person["given_name"])

    # Father: 0.30
    gedcom_father = _get_father_name(conn, person["id"])
    if pa_row["father"] and gedcom_father:
        father_score = _score_name(pa_row["father"], gedcom_father)
    elif not pa_row["father"] and not gedcom_father:
        father_score = 0.5  # Both missing — neutral
    elif not pa_row["father"]:
        father_score = 0.5  # PA has no father listed — neutral
    else:
        father_score = 0.3  # PA has father but GEDCOM doesn't — slight penalty

    # Date: 0.25
    date_score = _score_date(
        pa_row["end_year"], pa_row["end_type"], person["death_year_min"]
    )

    # Grandfather: 0.15
    if pa_row["grandfather"]:
        gedcom_grandfather = _get_grandfather_name(conn, person["id"])
        if gedcom_grandfather:
            grandfather_score = _score_name(pa_row["grandfather"], gedcom_grandfather)
        else:
            grandfather_score = 0.3  # PA has grandfather but GEDCOM doesn't
    else:
        grandfather_score = 0.5  # No grandfather in PA — neutral

    total = (
        0.30 * name_score
        + 0.30 * father_score
        + 0.25 * date_score
        + 0.15 * grandfather_score
    )

    return {
        "score": min(1.0, max(0.0, total)),
        "name_score": name_score,
        "father_score": father_score,
        "date_score": date_score,
        "grandfather_score": grandfather_score,
    }

"""Score candidate duplicate pairs by similarity.

Combines name match, date overlap, spouse match, and filiation signals.
"""

from __future__ import annotations

import sqlite3


def score_pair(
    conn: sqlite3.Connection,
    person_a: dict,
    person_b: dict,
) -> float:
    """Score a candidate pair for likelihood of being the same person.

    Returns 0.0 (definitely different) to 1.0 (definitely same).

    Scoring weights:
        Name match:       0.30
        Date overlap:     0.25
        Spouse match:     0.25
        Filiation match:  0.15
        Children overlap: 0.05
    """
    name_score = _score_name(person_a, person_b)
    date_score = _score_dates(person_a, person_b)
    spouse_score = _score_spouses(conn, person_a["id"], person_b["id"])
    filiation_score = _score_filiation(conn, person_a["id"], person_b["id"])
    children_score = _score_children(conn, person_a["id"], person_b["id"])

    total = (
        0.30 * name_score
        + 0.25 * date_score
        + 0.25 * spouse_score
        + 0.15 * filiation_score
        + 0.05 * children_score
    )

    return min(1.0, max(0.0, total))


def _score_name(pa: dict, pb: dict) -> float:
    """Score name similarity."""
    given_a = (pa.get("given_name") or "").lower().strip()
    given_b = (pb.get("given_name") or "").lower().strip()

    if not given_a or not given_b:
        return 0.3  # Can't compare — slightly below neutral

    # Exact match
    if given_a == given_b:
        return 1.0

    # One is a prefix of the other (e.g., 'Petrus' vs 'Petrus Paulus')
    if given_a.startswith(given_b) or given_b.startswith(given_a):
        return 0.85

    # Check parenthetical variants: 'Damianus' vs 'Damiano'
    # Strip common Latin endings for comparison
    root_a = _latin_root(given_a)
    root_b = _latin_root(given_b)
    if root_a == root_b and len(root_a) >= 3:
        return 0.9

    # First 3 characters match (handles minor spelling variants)
    if len(given_a) >= 3 and len(given_b) >= 3 and given_a[:3] == given_b[:3]:
        return 0.7

    return 0.0


def _score_dates(pa: dict, pb: dict) -> float:
    """Score date overlap."""
    scores = []

    # Birth years
    b_a = pa.get("birth_year_min")
    b_b = pb.get("birth_year_min")
    if b_a is not None and b_b is not None:
        diff = abs(b_a - b_b)
        if diff == 0:
            scores.append(1.0)
        elif diff <= 2:
            scores.append(0.9)
        elif diff <= 5:
            scores.append(0.6)
        elif diff <= 10:
            scores.append(0.3)
        else:
            scores.append(0.0)

    # Death years
    d_a = pa.get("death_year_min")
    d_b = pb.get("death_year_min")
    if d_a is not None and d_b is not None:
        diff = abs(d_a - d_b)
        if diff == 0:
            scores.append(1.0)
        elif diff <= 2:
            scores.append(0.9)
        elif diff <= 5:
            scores.append(0.6)
        elif diff <= 10:
            scores.append(0.3)
        else:
            scores.append(0.0)

    if not scores:
        return 0.5  # No date data — neutral

    return sum(scores) / len(scores)


def _score_spouses(conn: sqlite3.Connection, id_a: int, id_b: int) -> float:
    """Score spouse name overlap."""
    spouses_a = _get_spouse_names(conn, id_a)
    spouses_b = _get_spouse_names(conn, id_b)

    if not spouses_a or not spouses_b:
        return 0.5  # No spouse data — neutral

    # Check for any matching spouse
    for sa in spouses_a:
        for sb in spouses_b:
            if sa == sb:
                return 1.0
            # Check root match
            root_a = _latin_root(sa.split()[0]) if sa.split() else ""
            root_b = _latin_root(sb.split()[0]) if sb.split() else ""
            if root_a == root_b and len(root_a) >= 3:
                return 0.8

            # Same surname for spouse
            parts_a = sa.split()
            parts_b = sb.split()
            if len(parts_a) > 1 and len(parts_b) > 1 and parts_a[-1] == parts_b[-1]:
                return 0.7

    return 0.2  # Have spouse data but no match


def _score_filiation(conn: sqlite3.Connection, id_a: int, id_b: int) -> float:
    """Score filiation annotation overlap."""
    fil_a = set()
    fil_b = set()

    for row in conn.execute(
        "SELECT value FROM annotations WHERE person_id = ? AND annotation_type = 'filiation'",
        (id_a,),
    ):
        fil_a.add(row[0].lower().strip())

    for row in conn.execute(
        "SELECT value FROM annotations WHERE person_id = ? AND annotation_type = 'filiation'",
        (id_b,),
    ):
        fil_b.add(row[0].lower().strip())

    if not fil_a or not fil_b:
        return 0.5  # No filiation data — neutral

    # Check for overlap
    if fil_a & fil_b:
        return 1.0

    # Check for partial overlap (same parent surname)
    surnames_a = {_extract_surname_from_filiation(f) for f in fil_a}
    surnames_b = {_extract_surname_from_filiation(f) for f in fil_b}
    surnames_a.discard(None)
    surnames_b.discard(None)

    if surnames_a & surnames_b:
        return 0.7

    return 0.2


def _score_children(conn: sqlite3.Connection, id_a: int, id_b: int) -> float:
    """Score children name overlap."""
    children_a = _get_children_names(conn, id_a)
    children_b = _get_children_names(conn, id_b)

    if not children_a or not children_b:
        return 0.5  # Neutral

    # Count matching children names
    matches = 0
    for ca in children_a:
        for cb in children_b:
            root_a = _latin_root(ca)
            root_b = _latin_root(cb)
            if root_a == root_b and len(root_a) >= 3:
                matches += 1
                break

    if matches == 0:
        return 0.3

    total = max(len(children_a), len(children_b))
    return min(1.0, matches / total + 0.3)


# ---- Helpers ----

_LATIN_SUFFIXES = ("us", "um", "a", "e", "o", "is", "ius", "io", "ia")


def _latin_root(name: str) -> str:
    """Strip common Latin suffixes to get a comparable root."""
    name = name.lower().strip()
    for suffix in sorted(_LATIN_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix) and len(name) - len(suffix) >= 3:
            return name[: -len(suffix)]
    return name


def _get_spouse_names(conn: sqlite3.Connection, person_id: int) -> list[str]:
    """Get spouse names for a person."""
    names = []
    for row in conn.execute(
        "SELECT COALESCE(ps.given_name, '') || ' ' || COALESCE(ps.surname, '') as name "
        "FROM families f "
        "LEFT JOIN persons ps ON "
        "  (CASE WHEN f.husband_id = ? THEN f.wife_id ELSE f.husband_id END) = ps.id "
        "WHERE (f.husband_id = ? OR f.wife_id = ?) AND ps.id IS NOT NULL",
        (person_id, person_id, person_id),
    ):
        name = row[0].strip()
        if name:
            names.append(name.lower())
    return names


def _get_children_names(conn: sqlite3.Connection, person_id: int) -> list[str]:
    """Get children's given names for a person."""
    names = []
    for row in conn.execute(
        "SELECT p.given_name "
        "FROM families f "
        "JOIN family_children fc ON fc.family_id = f.id "
        "JOIN persons p ON fc.child_id = p.id "
        "WHERE f.husband_id = ? OR f.wife_id = ?",
        (person_id, person_id),
    ):
        if row[0]:
            names.append(row[0].lower())
    return names


def _extract_surname_from_filiation(text: str) -> str | None:
    """Extract the surname from a filiation value like 'Marini Petri de Menze'."""
    parts = text.split()
    if not parts:
        return None
    # Remove 'de', 'del', 'gu.' etc.
    cleaned = [p for p in parts if p.lower() not in ("de", "del", "di", "gu.", "ser")]
    if cleaned:
        return cleaned[-1].lower()
    return None

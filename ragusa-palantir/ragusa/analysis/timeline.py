"""Timeline and generation analysis tools."""

from __future__ import annotations

import sqlite3
from collections import defaultdict


def get_generation_summary(
    conn: sqlite3.Connection,
    surname: str,
    cohort_years: int = 30,
) -> list[dict]:
    """Break a family into approximate generations.

    Args:
        surname: Family surname.
        cohort_years: Width of each generation cohort in years.

    Returns:
        List of generation dicts with members.
    """
    rows = conn.execute(
        "SELECT id, given_name, surname, sex, "
        "birth_year_min, death_year_min "
        "FROM persons WHERE surname = ? AND birth_year_min IS NOT NULL "
        "ORDER BY birth_year_min",
        (surname,),
    ).fetchall()

    if not rows:
        return []

    min_year = rows[0]["birth_year_min"]
    generations: dict[int, list] = defaultdict(list)

    for r in rows:
        gen_num = (r["birth_year_min"] - min_year) // cohort_years
        generations[gen_num].append(dict(r))

    return [
        {
            "generation": gen + 1,
            "year_range": (
                f"{min_year + gen * cohort_years}-{min_year + (gen + 1) * cohort_years - 1}"
            ),
            "year_start": min_year + gen * cohort_years,
            "year_end": min_year + (gen + 1) * cohort_years - 1,
            "count": len(members),
            "members": members,
        }
        for gen, members in sorted(generations.items())
    ]


def get_period_snapshot(
    conn: sqlite3.Connection,
    year: int,
) -> dict:
    """Who was alive in a given year?

    Uses birth/death year bounds. Persons without both dates are excluded.

    Returns:
        {surname: [person_summaries], ...} sorted by surname.
    """
    rows = conn.execute(
        "SELECT id, given_name, surname, sex, birth_year_min, death_year_min "
        "FROM persons "
        "WHERE birth_year_min IS NOT NULL AND death_year_min IS NOT NULL "
        "AND birth_year_min <= ? AND death_year_min >= ? "
        "ORDER BY surname, given_name",
        (year, year),
    ).fetchall()

    by_family: dict[str, list] = defaultdict(list)
    for r in rows:
        surname = r["surname"] or "(unknown)"
        by_family[surname].append(dict(r))

    return dict(sorted(by_family.items()))


def get_family_timeline(
    conn: sqlite3.Connection,
    surname: str,
) -> list[dict]:
    """Chronological list of all events for a family.

    Combines births, deaths, marriages, and annotations with dates.
    """
    events: list[dict] = []

    # Births and deaths
    for r in conn.execute(
        "SELECT p.id, p.given_name, p.surname, e.event_type, "
        "e.date_raw, e.year_min, e.place "
        "FROM events e "
        "JOIN persons p ON e.person_id = p.id "
        "WHERE p.surname = ? AND e.year_min IS NOT NULL "
        "ORDER BY e.year_min",
        (surname,),
    ):
        events.append(
            {
                "year": r["year_min"],
                "type": r["event_type"],
                "person_id": r["id"],
                "person": f"{r['given_name'] or ''} {r['surname'] or ''}".strip(),
                "detail": r["place"] or r["date_raw"],
            }
        )

    # Marriages
    for r in conn.execute(
        "SELECT f.marriage_year_min as year, "
        "ph.id as h_id, ph.given_name as h_given, ph.surname as h_surname, "
        "pw.id as w_id, pw.given_name as w_given, pw.surname as w_surname "
        "FROM families f "
        "JOIN persons ph ON f.husband_id = ph.id "
        "JOIN persons pw ON f.wife_id = pw.id "
        "WHERE (ph.surname = ? OR pw.surname = ?) "
        "AND f.marriage_year_min IS NOT NULL "
        "ORDER BY f.marriage_year_min",
        (surname, surname),
    ):
        h_name = f"{r['h_given'] or ''} {r['h_surname'] or ''}".strip()
        w_name = f"{r['w_given'] or ''} {r['w_surname'] or ''}".strip()
        events.append(
            {
                "year": r["year"],
                "type": "MARR",
                "person_id": r["h_id"] if r["h_surname"] == surname else r["w_id"],
                "person": h_name if r["h_surname"] == surname else w_name,
                "detail": f"married {w_name}" if r["h_surname"] == surname else f"married {h_name}",
            }
        )

    # Annotations with dates
    for r in conn.execute(
        "SELECT a.annotation_type, a.value, a.date_year_min, "
        "p.id as person_id, p.given_name, p.surname "
        "FROM annotations a "
        "JOIN persons p ON a.person_id = p.id "
        "WHERE p.surname = ? AND a.date_year_min IS NOT NULL",
        (surname,),
    ):
        events.append(
            {
                "year": r["date_year_min"],
                "type": r["annotation_type"].upper(),
                "person_id": r["person_id"],
                "person": f"{r['given_name'] or ''} {r['surname'] or ''}".strip(),
                "detail": r["value"],
            }
        )

    events.sort(key=lambda e: e["year"])
    return events

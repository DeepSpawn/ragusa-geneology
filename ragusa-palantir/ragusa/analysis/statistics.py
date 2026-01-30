"""Data quality and coverage statistics for the Ragusa database."""

from __future__ import annotations

import sqlite3


def data_quality_report(conn: sqlite3.Connection) -> dict:
    """Generate a comprehensive data quality report.

    Returns a dict with counts, distributions, and quality metrics.
    """
    report = {}

    # Record counts
    for table in (
        "persons",
        "families",
        "family_children",
        "events",
        "notes",
        "source_references",
        "annotations",
        "person_names",
    ):
        report[f"count_{table}"] = _scalar(conn, f"SELECT COUNT(*) FROM {table}")

    # Person statistics
    report["persons_with_birth"] = _scalar(
        conn, "SELECT COUNT(*) FROM persons WHERE birth_year_min IS NOT NULL"
    )
    report["persons_with_death"] = _scalar(
        conn, "SELECT COUNT(*) FROM persons WHERE death_year_min IS NOT NULL"
    )
    report["persons_with_both_dates"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM persons "
        "WHERE birth_year_min IS NOT NULL AND death_year_min IS NOT NULL",
    )
    report["persons_with_surname"] = _scalar(
        conn, "SELECT COUNT(*) FROM persons WHERE surname IS NOT NULL"
    )
    report["persons_unnamed"] = _scalar(
        conn, "SELECT COUNT(*) FROM persons WHERE name_raw = '(unnamed)'"
    )
    report["canonical_persons"] = _scalar(
        conn, "SELECT COUNT(*) FROM persons WHERE is_canonical = 1"
    )

    # Date range
    report["earliest_birth"] = _scalar(
        conn, "SELECT MIN(birth_year_min) FROM persons WHERE birth_year_min IS NOT NULL"
    )
    report["latest_birth"] = _scalar(
        conn, "SELECT MAX(birth_year_max) FROM persons WHERE birth_year_max IS NOT NULL"
    )
    report["earliest_death"] = _scalar(
        conn, "SELECT MIN(death_year_min) FROM persons WHERE death_year_min IS NOT NULL"
    )
    report["latest_death"] = _scalar(
        conn, "SELECT MAX(death_year_max) FROM persons WHERE death_year_max IS NOT NULL"
    )

    # Surname distribution (top 30)
    report["surname_distribution"] = [
        {"surname": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT surname, COUNT(*) as cnt FROM persons "
            "WHERE surname IS NOT NULL GROUP BY surname ORDER BY cnt DESC LIMIT 30"
        )
    ]

    # Annotation type distribution
    report["annotation_types"] = [
        {"type": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT annotation_type, COUNT(*) as cnt FROM annotations "
            "GROUP BY annotation_type ORDER BY cnt DESC"
        )
    ]

    # Persons per century
    report["persons_per_century"] = [
        {"century": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT (birth_year_min / 100) * 100 as century, COUNT(*) as cnt "
            "FROM persons WHERE birth_year_min IS NOT NULL "
            "GROUP BY century ORDER BY century"
        )
    ]

    # Family statistics
    report["families_with_marriage_date"] = _scalar(
        conn, "SELECT COUNT(*) FROM families WHERE marriage_year_min IS NOT NULL"
    )
    report["families_with_both_spouses"] = _scalar(
        conn,
        "SELECT COUNT(*) FROM families WHERE husband_id IS NOT NULL AND wife_id IS NOT NULL",
    )
    report["avg_children_per_family"] = _scalar(
        conn,
        "SELECT ROUND(AVG(cnt), 1) FROM "
        "(SELECT family_id, COUNT(*) as cnt FROM family_children GROUP BY family_id)",
    )

    # Event statistics
    report["event_types"] = [
        {"type": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type ORDER BY cnt DESC"
        )
    ]

    # Events with places
    report["events_with_place"] = _scalar(
        conn, "SELECT COUNT(*) FROM events WHERE place IS NOT NULL"
    )
    report["unique_places"] = [
        {"place": row[0], "count": row[1]}
        for row in conn.execute(
            "SELECT place, COUNT(*) as cnt FROM events "
            "WHERE place IS NOT NULL GROUP BY place ORDER BY cnt DESC LIMIT 20"
        )
    ]

    # Source file breakdown
    report["source_files"] = [dict(row) for row in conn.execute("SELECT * FROM source_files")]

    return report


def print_report(conn: sqlite3.Connection) -> None:
    """Print a formatted data quality report to stdout."""
    r = data_quality_report(conn)

    print("=" * 60)
    print("RAGUSA DATABASE — DATA QUALITY REPORT")
    print("=" * 60)

    print("\n--- Record Counts ---")
    for table in (
        "persons",
        "families",
        "family_children",
        "events",
        "notes",
        "source_references",
        "annotations",
        "person_names",
    ):
        print(f"  {table:22s}: {r[f'count_{table}']:>6}")

    print("\n--- Person Coverage ---")
    total = r["count_persons"]
    print(f"  Total persons:         {total}")
    print(f"  Canonical (deduped):   {r['canonical_persons']}")
    pct_birth = 100 * r["persons_with_birth"] / total
    pct_death = 100 * r["persons_with_death"] / total
    pct_both = 100 * r["persons_with_both_dates"] / total
    pct_surname = 100 * r["persons_with_surname"] / total
    print(f"  With birth year:       {r['persons_with_birth']} ({pct_birth:.0f}%)")
    print(f"  With death year:       {r['persons_with_death']} ({pct_death:.0f}%)")
    print(f"  With both dates:       {r['persons_with_both_dates']} ({pct_both:.0f}%)")
    print(f"  With surname:          {r['persons_with_surname']} ({pct_surname:.0f}%)")
    print(f"  Unnamed:               {r['persons_unnamed']}")

    print("\n--- Date Range ---")
    print(f"  Earliest birth:        {r['earliest_birth']}")
    print(f"  Latest birth:          {r['latest_birth']}")
    print(f"  Earliest death:        {r['earliest_death']}")
    print(f"  Latest death:          {r['latest_death']}")

    print("\n--- Persons by Century ---")
    for entry in r["persons_per_century"]:
        bar = "#" * (entry["count"] // 20)
        print(f"  {entry['century']}s: {entry['count']:>5}  {bar}")

    print("\n--- Top 20 Surnames ---")
    for entry in r["surname_distribution"][:20]:
        bar = "#" * (entry["count"] // 5)
        print(f"  {entry['surname']:20s}: {entry['count']:>4}  {bar}")

    print("\n--- Annotation Types ---")
    for entry in r["annotation_types"]:
        print(f"  {entry['type']:22s}: {entry['count']:>5}")

    print("\n--- Family Statistics ---")
    print(f"  With marriage date:    {r['families_with_marriage_date']}")
    print(f"  With both spouses:     {r['families_with_both_spouses']}")
    print(f"  Avg children/family:   {r['avg_children_per_family']}")

    print("\n--- Events ---")
    for entry in r["event_types"]:
        print(f"  {entry['type']:10s}: {entry['count']:>5}")
    print(f"  With place: {r['events_with_place']}")

    if r["unique_places"]:
        print("\n--- Top Places ---")
        for entry in r["unique_places"]:
            print(f"  {entry['place']:30s}: {entry['count']:>4}")

    print("\n--- Source Files ---")
    for sf in r["source_files"]:
        print(f"  {sf['filename']}: v{sf['gedcom_version']}, {sf['encoding']}, {sf['software']}")


def _scalar(conn: sqlite3.Connection, sql: str):
    """Execute a query and return the single scalar result."""
    return conn.execute(sql).fetchone()[0]

"""Shared pytest fixtures for the ragusa-palantir test suite."""

from __future__ import annotations

import sqlite3

import pytest

from ragusa.db.schema import create_schema
from ragusa.parser.gedcom_reader import GedcomLine


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn():
    """In-memory SQLite database with schema created."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture()
def populated_db(db_conn):
    """Database pre-populated with a controlled genealogical dataset.

    Contains 2 source files, 8 persons (including 2 cross-file duplicates),
    3 families, family-children links, events, notes, annotations, source
    references, and alternate person names.
    """
    conn = db_conn

    # -- Source files --
    conn.execute(
        "INSERT INTO source_files (id, filename, gedcom_version, encoding, software, date_created)"
        " VALUES (1, 'Ragusan.ged', '5.5', 'IBMPC', 'GIM 3.17', '7 Jun 1999')"
    )
    conn.execute(
        "INSERT INTO source_files (id, filename, gedcom_version, encoding, software, date_created)"
        " VALUES (2, 'Gondola.Petrus.ged', '4.0', 'ANSEL', 'PAF 5.1', '9 Jul 2001')"
    )

    # -- Persons (source file 1) --
    persons_sf1 = [
        (1, 1, "@I1@", "Petrus", "Gondola", "Petrus Gondola", "M", 1260, 1260, 1320, 1320),
        (2, 1, "@I2@", "Margarita", "Mence", "Margarita Mence", "F", 1270, 1270, 1335, 1335),
        (3, 1, "@I3@", "Damianus", "Gondola", "Damianus Gondola", "M", 1290, 1290, 1350, 1350),
        (4, 1, "@I4@", "Maria", "Babalio", "Maria Babalio", "F", 1295, 1295, None, None),
        (5, 1, "@I5@", "Clemens", "Gondola", "Clemens Gondola", "M", 1292, 1292, 1360, 1360),
        (8, 1, "@I6@", "Elena", "Goce", "Elena Goce", "F", 1300, 1300, 1370, 1370),
    ]
    # -- Persons (source file 2, duplicates) --
    persons_sf2 = [
        (6, 2, "@I1@", "Petrus", "Gondola", "Petrus Gondola", "M", 1261, 1261, 1320, 1320),
        (7, 2, "@I2@", "Damiano", "Gondola", "Damiano Gondola", "M", 1290, 1290, None, None),
    ]

    for p in persons_sf1 + persons_sf2:
        conn.execute(
            "INSERT INTO persons"
            " (id, source_file_id, gedcom_id, given_name, surname, name_raw, sex,"
            "  birth_year_min, birth_year_max, death_year_min, death_year_max)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            p,
        )

    # -- Families --
    conn.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id,"
        "  marriage_year_min, marriage_year_max, marriage_place,"
        "  marriage_order_husband, marriage_order_wife)"
        " VALUES (1, 1, '@F1@', 1, 2, 1285, 1285, 'Ragusa', 1, 1)"
    )
    conn.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id,"
        "  marriage_year_min, marriage_year_max, marriage_place,"
        "  marriage_order_husband, marriage_order_wife)"
        " VALUES (2, 1, '@F2@', 3, 4, 1315, 1315, NULL, 1, 1)"
    )
    conn.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id,"
        "  marriage_year_min, marriage_year_max, marriage_place,"
        "  marriage_order_husband, marriage_order_wife)"
        " VALUES (3, 1, '@F3@', 5, 8, 1318, 1318, 'Ragusa', 1, 1)"
    )

    # -- Family children --
    conn.execute(
        "INSERT INTO family_children (family_id, child_id, child_order)"
        " VALUES (1, 3, 1)"
    )
    conn.execute(
        "INSERT INTO family_children (family_id, child_id, child_order)"
        " VALUES (1, 5, 2)"
    )

    # -- Events --
    events = [
        (1, None, "BIRT", "1260", 1260, 1260, "Ragusa"),
        (1, None, "DEAT", "1320", 1320, 1320, "Ragusa"),
        (3, None, "BIRT", "ABT 1290", 1290, 1290, None),
        (3, None, "DEAT", "1350", 1350, 1350, "Stagno"),
    ]
    for e in events:
        conn.execute(
            "INSERT INTO events (person_id, family_id, event_type, date_raw, year_min, year_max, place)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            e,
        )

    # -- Notes --
    conn.execute(
        "INSERT INTO notes (id, person_id, family_id, note_category, note_text, gedcom_level)"
        " VALUES (1, 1, NULL, 'SOURCE NOTES', 'list 2, veja 6', 1)"
    )
    conn.execute(
        "INSERT INTO notes (id, person_id, family_id, note_category, note_text, gedcom_level)"
        " VALUES (2, 1, NULL, 'RESEARCH NOTES', 'sin Marini de Gondola', 1)"
    )
    conn.execute(
        "INSERT INTO notes (id, person_id, family_id, note_category, note_text, gedcom_level)"
        " VALUES (3, 3, NULL, 'RESEARCH NOTES', 'hči Petri de Gondola', 1)"
    )

    # -- Source references --
    conn.execute(
        "INSERT INTO source_references (note_id, person_id, list_number, veja_number, raw_text)"
        " VALUES (1, 1, 2, 6, 'list 2, veja 6')"
    )

    # -- Annotations --
    conn.execute(
        "INSERT INTO annotations (id, note_id, person_id, annotation_type, subtype, value, raw_text)"
        " VALUES (1, 2, 1, 'filiation', 'son', 'Marini de Gondola', 'sin Marini de Gondola')"
    )
    conn.execute(
        "INSERT INTO annotations (id, note_id, person_id, annotation_type, subtype, value, raw_text)"
        " VALUES (2, 3, 3, 'filiation', 'daughter', 'Petri de Gondola', 'hči Petri de Gondola')"
    )
    conn.execute(
        "INSERT INTO annotations (id, note_id, person_id, annotation_type, subtype, value,"
        " date_year_min, date_year_max, raw_text)"
        " VALUES (3, NULL, 3, 'monastic', NULL, 'entered monastery',"
        " 1345, 1345, '1345 mon.')"
    )

    # -- Person names (alternates) --
    conn.execute(
        "INSERT INTO person_names (person_id, name_type, given_name, surname, name_raw, source)"
        " VALUES (3, 'parenthetical', 'Damiano', 'Gondola', 'Damiano Gondola', NULL)"
    )
    conn.execute(
        "INSERT INTO person_names (person_id, name_type, given_name, surname, name_raw, source)"
        " VALUES (1, 'also', NULL, NULL, 'Petar Gundulić', 'Also: Petar Gundulić')"
    )

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# GEDCOM helpers
# ---------------------------------------------------------------------------


def make_gedcom_line(
    line_number: int,
    level: int,
    tag: str,
    xref: str | None = None,
    value: str | None = None,
) -> GedcomLine:
    """Build a GedcomLine without parsing a file."""
    parts = [str(level)]
    if xref:
        parts.append(xref)
    parts.append(tag)
    if value:
        parts.append(value)
    raw = " ".join(parts)
    return GedcomLine(
        line_number=line_number,
        level=level,
        xref=xref,
        tag=tag,
        value=value,
        raw=raw,
    )

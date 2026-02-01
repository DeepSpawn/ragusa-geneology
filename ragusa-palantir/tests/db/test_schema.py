"""Tests for ragusa.db.schema."""

from __future__ import annotations

import sqlite3

import pytest

from ragusa.db.schema import create_schema

EXPECTED_TABLES = {
    "source_files",
    "persons",
    "person_names",
    "families",
    "family_children",
    "events",
    "notes",
    "source_references",
    "annotations",
    "offices",
    "documents",
    "document_persons",
    "dedup_candidates",
    "politically_active_men",
    "pa_match_candidates",
}


def test_create_schema_creates_all_tables(db_conn):
    rows = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert table_names == EXPECTED_TABLES


def test_create_schema_idempotent(db_conn):
    # Schema already created by fixture; calling again should not error
    create_schema(db_conn)


def test_persons_table_sex_constraint(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO persons (source_file_id, gedcom_id, name_raw, sex)"
            " VALUES (1, '@I1@', 'Test', 'X')"
        )


def test_foreign_key_enforcement(db_conn):
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO person_names (person_id, name_type, name_raw)"
            " VALUES (9999, 'also', 'Test Name')"
        )


def test_unique_constraint_gedcom_id(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, '@I1@', 'Test', 'M')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO persons (source_file_id, gedcom_id, name_raw, sex)"
            " VALUES (1, '@I1@', 'Duplicate', 'F')"
        )

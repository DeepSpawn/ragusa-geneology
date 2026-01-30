"""Tests for ragusa.dedup.candidates."""

from __future__ import annotations

import pytest

from ragusa.dedup.candidates import (
    SURNAME_VARIANTS,
    generate_candidates,
    get_canonical_surname,
)


# ---------------------------------------------------------------------------
# get_canonical_surname
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_surname, expected",
    list(SURNAME_VARIANTS.items()),
    ids=list(SURNAME_VARIANTS.keys()),
)
def test_get_canonical_surname_known(input_surname, expected):
    assert get_canonical_surname(input_surname) == expected


def test_get_canonical_surname_unknown_passthrough():
    assert get_canonical_surname("Gondola") == "Gondola"


def test_get_canonical_surname_case_sensitive():
    """Variant lookup is case-sensitive (dict keys are capitalized)."""
    assert get_canonical_surname("dersie") == "dersie"


# ---------------------------------------------------------------------------
# generate_candidates
# ---------------------------------------------------------------------------


def test_generate_candidates_needs_two_source_files(db_conn):
    """With only one source file, no candidates should be generated."""
    db_conn.execute(
        "INSERT INTO source_files (id, filename) VALUES (1, 'only.ged')"
    )
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (1, '@I1@', 'Petrus', 'Gondola', 'Petrus Gondola', 'M')"
    )
    db_conn.commit()
    candidates = generate_candidates(db_conn)
    assert candidates == []


def test_generate_candidates_basic(populated_db):
    """Cross-file duplicates with same surname should produce candidates."""
    candidates = generate_candidates(populated_db)
    assert len(candidates) > 0


def test_generate_candidates_sex_filter(db_conn):
    """Male in source 1 vs female in source 2 with same surname should be filtered."""
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'a.ged')")
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (2, 'b.ged')")
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (1, '@I1@', 'Petrus', 'Gondola', 'Petrus Gondola', 'M')"
    )
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (2, '@I1@', 'Maria', 'Gondola', 'Maria Gondola', 'F')"
    )
    db_conn.commit()
    candidates = generate_candidates(db_conn)
    assert candidates == []


def test_generate_candidates_sex_unknown_passes(db_conn):
    """Sex 'U' (unknown) should not cause filtering."""
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'a.ged')")
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (2, 'b.ged')")
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (1, '@I1@', 'Petrus', 'Gondola', 'Petrus Gondola', 'M')"
    )
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (2, '@I1@', 'Petrus', 'Gondola', 'Petrus Gondola', 'U')"
    )
    db_conn.commit()
    candidates = generate_candidates(db_conn)
    assert len(candidates) == 1


def test_generate_candidates_structure(populated_db):
    """Each candidate dict should have the expected keys."""
    candidates = generate_candidates(populated_db)
    assert len(candidates) > 0
    c = candidates[0]
    assert "person_a_id" in c
    assert "person_b_id" in c
    assert "surname" in c
    assert "person_a" in c
    assert "person_b" in c

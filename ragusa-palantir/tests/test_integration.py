"""Integration tests: full GEDCOM load pipeline → database state verification."""

from __future__ import annotations

import sqlite3
import textwrap

import pytest

from ragusa.db.schema import create_schema
from ragusa.parser.gedcom_loader import load_gedcom_file


@pytest.fixture()
def integration_db():
    """In-memory database for integration tests."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_full_load_pipeline(tmp_path, integration_db):
    """Load a minimal GEDCOM file and verify all tables are populated."""
    gedcom = textwrap.dedent("""\
        0 HEAD
        1 CHAR ASCII
        1 SOUR PAF
        2 VERS 4.0
        1 GEDC
        2 VERS 5.5
        1 DATE 1 JAN 2000
        0 @I1@ INDI
        1 NAME Petrus Gondola
        1 SEX M
        1 BIRT
        2 DATE 1260
        2 PLAC Ragusa
        1 DEAT
        2 DATE 1320
        1 NOTE SOURCE NOTES:
        2 CONT list 2, veja 6
        1 NOTE RESEARCH NOTES:
        2 CONT sin Marini de Gondola
        0 @I2@ INDI
        1 NAME Margarita Mence
        1 SEX F
        1 BIRT
        2 DATE 1270
        0 @F1@ FAM
        1 HUSB @I1@
        1 WIFE @I2@
        1 MARR
        2 DATE 1285
        2 PLAC Ragusa
        1 CHIL @I1@
        0 TRLR
    """)
    f = tmp_path / "test.ged"
    f.write_text(gedcom, encoding="ascii")

    summary = load_gedcom_file(integration_db, str(f))

    assert summary["individuals"] == 2
    assert summary["families"] == 1
    assert summary["source_file_id"] is not None

    # Verify persons
    persons = integration_db.execute("SELECT * FROM persons ORDER BY id").fetchall()
    assert len(persons) == 2
    assert persons[0]["given_name"] == "Petrus"
    assert persons[0]["surname"] == "Gondola"
    assert persons[0]["birth_year_min"] == 1260

    # Verify families
    fam = integration_db.execute("SELECT * FROM families").fetchone()
    assert fam is not None
    assert fam["marriage_year_min"] == 1285
    assert fam["marriage_place"] == "Ragusa"

    # Verify events
    events = integration_db.execute("SELECT * FROM events").fetchall()
    assert len(events) >= 2  # At least BIRT and DEAT for person 1

    # Verify notes exist
    notes_count = integration_db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert notes_count >= 1

    # Verify source references
    refs = integration_db.execute("SELECT * FROM source_references").fetchall()
    assert len(refs) >= 1
    assert refs[0]["list_number"] == 2
    assert refs[0]["veja_number"] == 6


def test_load_pipeline_name_parsing(tmp_path, integration_db):
    """Verify parenthetical name parsing through the full pipeline."""
    gedcom = textwrap.dedent("""\
        0 HEAD
        1 CHAR ASCII
        0 @I1@ INDI
        1 NAME Damianus (Damiano) de Sorgo
        1 SEX M
        0 TRLR
    """)
    f = tmp_path / "test.ged"
    f.write_text(gedcom, encoding="ascii")

    load_gedcom_file(integration_db, str(f))

    person = integration_db.execute("SELECT * FROM persons").fetchone()
    assert person["given_name"] == "Damianus"
    assert person["surname"] == "Sorgo"

    alt_names = integration_db.execute("SELECT * FROM person_names").fetchall()
    assert len(alt_names) >= 1
    alt = alt_names[0]
    assert alt["given_name"] == "Damiano"
    assert alt["name_type"] == "parenthetical"


def test_load_pipeline_encoding_normalization(tmp_path, integration_db):
    """ANSEL encoding artifacts should be normalized in names."""
    # Write bytes with ANSEL charset declaration and \xd9$ sequence
    content = (
        b"0 HEAD\n"
        b"1 CHAR ANSEL\n"
        b"0 @I1@ INDI\n"
        b"1 NAME h\xd9$i Gondola\n"
        b"1 SEX M\n"
        b"0 TRLR\n"
    )
    f = tmp_path / "test.ged"
    f.write_bytes(content)

    load_gedcom_file(integration_db, str(f))

    person = integration_db.execute("SELECT * FROM persons").fetchone()
    # The \xd9$ should have been normalized to č
    assert "č" in person["name_raw"] or "č" in (person["given_name"] or "")


def test_load_pipeline_malformed_lines_handled(tmp_path, integration_db):
    """Malformed lines should not crash the pipeline."""
    gedcom = textwrap.dedent("""\
        0 HEAD
        1 CHAR ASCII
        this is malformed
        0 @I1@ INDI
        1 NAME Petrus Gondola
        1 SEX M
        0 TRLR
    """)
    f = tmp_path / "test.ged"
    f.write_text(gedcom, encoding="ascii")

    summary = load_gedcom_file(integration_db, str(f))
    assert summary["individuals"] == 1


def test_load_pipeline_empty_file(tmp_path, integration_db):
    """A file with only HEAD and TRLR should load without error."""
    gedcom = "0 HEAD\n1 CHAR ASCII\n0 TRLR\n"
    f = tmp_path / "test.ged"
    f.write_text(gedcom, encoding="ascii")

    summary = load_gedcom_file(integration_db, str(f))
    assert summary["individuals"] == 0
    assert summary["families"] == 0

    # Source file record should still be created
    sf = integration_db.execute("SELECT COUNT(*) FROM source_files").fetchone()[0]
    assert sf == 1

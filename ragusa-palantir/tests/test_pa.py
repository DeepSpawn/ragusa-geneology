"""Tests for the politically active men (PA) module."""

from __future__ import annotations

import csv
import os
import tempfile

import pytest

from ragusa.db.schema import create_schema
from ragusa.pa.loader import load_pa_csv
from ragusa.pa.matching import (
    _get_father_name,
    _get_grandfather_name,
    _latin_root,
    _score_date,
    _score_name,
    generate_pa_candidates,
    score_pa_match,
)
from ragusa.pa.review import run_pa_matching


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pa_db(db_conn):
    """Database with PA schema and test persons suitable for PA matching.

    Sets up:
    - 2 source files
    - Persons: Andrea Babalio (father=Volcius, grandfather=Blasius, d.1473),
      plus other Babalios and a Goce to test non-matching.
    - Family links for father/grandfather lookup.
    """
    conn = db_conn

    # Source files
    conn.execute(
        "INSERT INTO source_files (id, filename, gedcom_version, encoding, software, date_created)"
        " VALUES (1, 'Ragusan.ged', '5.5', 'IBMPC', 'GIM 3.17', '7 Jun 1999')"
    )

    # Persons
    persons = [
        # Grandfather: Blasius Babalio
        (100, 1, "@G1@", "Blasius", "Babalio", "Blasius Babalio", "M", 1340, 1340, 1400, 1400),
        # Father: Volcius Babalio (son of Blasius)
        (101, 1, "@G2@", "Volcius", "Babalio", "Volcius Babalio", "M", 1370, 1370, 1430, 1430),
        # Target: Andreas Babalio (son of Volcius, grandson of Blasius)
        (102, 1, "@G3@", "Andreas", "Babalio", "Andreas Babalio", "M", 1399, 1399, 1473, 1473),
        # Another Andreas Babalio (different father, different death year)
        (103, 1, "@G4@", "Andreas", "Babalio", "Andreas Babalio", "M", 1420, 1420, 1490, 1490),
        # Father of 103: Savinus
        (104, 1, "@G5@", "Savinus", "Babalio", "Savinus Babalio", "M", 1385, 1385, 1450, 1450),
        # A Goce (wrong surname for Babalio PA entries)
        (105, 1, "@G6@", "Andreas", "Goce", "Andreas Goce", "M", 1399, 1399, 1473, 1473),
        # Female (should be excluded from PA matching)
        (106, 1, "@G7@", "Maria", "Babalio", "Maria Babalio", "F", 1400, 1400, 1460, 1460),
    ]
    for p in persons:
        conn.execute(
            "INSERT INTO persons"
            " (id, source_file_id, gedcom_id, given_name, surname, name_raw, sex,"
            "  birth_year_min, birth_year_max, death_year_min, death_year_max)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            p,
        )

    # Families: Blasius -> Volcius -> Andreas
    conn.execute(
        "INSERT INTO families (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (10, 1, '@F10@', 100, NULL)"
    )
    conn.execute(
        "INSERT INTO family_children (family_id, child_id, child_order) VALUES (10, 101, 1)"
    )
    conn.execute(
        "INSERT INTO families (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (11, 1, '@F11@', 101, NULL)"
    )
    conn.execute(
        "INSERT INTO family_children (family_id, child_id, child_order) VALUES (11, 102, 1)"
    )
    # Savinus -> Andreas (103)
    conn.execute(
        "INSERT INTO families (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (12, 1, '@F12@', 104, NULL)"
    )
    conn.execute(
        "INSERT INTO family_children (family_id, child_id, child_order) VALUES (12, 103, 1)"
    )

    conn.commit()
    return conn


def _make_pa_csv(rows: list[dict]) -> str:
    """Write PA rows to a temp CSV file and return path."""
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    fieldnames = [
        "id", "surname", "name", "father", "grandfather",
        "hackenberg_number", "entry_year", "entry_source",
        "end_year", "end_type", "notes",
    ]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# Latin root tests
# ---------------------------------------------------------------------------


class TestLatinRoot:
    def test_strips_ius(self):
        assert _latin_root("Blasius") == "blas"

    def test_strips_o(self):
        assert _latin_root("Damiano") == "damian"

    def test_short_name_not_stripped(self):
        # "Go" after stripping "ce" is too short
        assert _latin_root("Go") == "go"

    def test_no_matching_suffix(self):
        # "Andreas" ends with "as", not a listed Latin suffix
        assert _latin_root("Andreas") == "andreas"


# ---------------------------------------------------------------------------
# Name scoring tests
# ---------------------------------------------------------------------------


class TestScoreName:
    def test_exact_match(self):
        assert _score_name("Andreas", "Andreas") == 1.0

    def test_case_insensitive(self):
        assert _score_name("andreas", "ANDREAS") == 1.0

    def test_latin_root_match(self):
        # Blasius vs Blase -> root "blas" matches
        score = _score_name("Blasius", "Blase")
        assert score >= 0.7

    def test_prefix_match(self):
        score = _score_name("Petrus", "Petrus Paulus")
        assert score == 0.85

    def test_no_match(self):
        assert _score_name("Andreas", "Marinus") == 0.0

    def test_missing_name(self):
        assert _score_name("", "Andreas") == 0.3


# ---------------------------------------------------------------------------
# Date scoring tests
# ---------------------------------------------------------------------------


class TestScoreDate:
    def test_exact_match(self):
        assert _score_date("1473", None, 1473) == 1.0

    def test_close_match(self):
        score = _score_date("1473", None, 1475)
        assert score == 0.9

    def test_moderate_diff(self):
        score = _score_date("1473", None, 1478)
        assert score == 0.6

    def test_large_diff(self):
        score = _score_date("1473", None, 1500)
        assert score == 0.0

    def test_period_end_type_survived(self):
        # Person survived past period; death after end_year is good
        score = _score_date("1490", "Period", 1510)
        assert score == 0.8

    def test_period_end_type_died_before(self):
        # Died well before period end — bad match
        score = _score_date("1490", "Period", 1470)
        assert score == 0.1

    def test_missing_data(self):
        assert _score_date("?", None, 1473) == 0.5
        assert _score_date("1473", None, None) == 0.5


# ---------------------------------------------------------------------------
# Father/grandfather lookup tests
# ---------------------------------------------------------------------------


class TestFamilyLookup:
    def test_get_father_name(self, pa_db):
        # Andreas (102) -> father is Volcius (101)
        assert _get_father_name(pa_db, 102) == "Volcius"

    def test_get_father_name_not_found(self, pa_db):
        # Blasius (100) has no recorded father
        assert _get_father_name(pa_db, 100) is None

    def test_get_grandfather_name(self, pa_db):
        # Andreas (102) -> grandfather is Blasius (100)
        assert _get_grandfather_name(pa_db, 102) == "Blasius"

    def test_get_grandfather_name_not_found(self, pa_db):
        # Volcius (101) -> father is Blasius but Blasius has no father
        assert _get_grandfather_name(pa_db, 101) is None


# ---------------------------------------------------------------------------
# CSV loader tests
# ---------------------------------------------------------------------------


class TestLoader:
    def test_load_pa_csv(self, pa_db):
        csv_path = _make_pa_csv([
            {
                "id": "18", "surname": "Babalio", "name": "Andreas",
                "father": "Volcius", "grandfather": "",
                "hackenberg_number": "01-040102", "entry_year": "1421",
                "entry_source": "", "end_year": "1473", "end_type": "",
                "notes": "",
            },
            {
                "id": "38", "surname": "Babalio", "name": "Benedetto",
                "father": "Savinus", "grandfather": "",
                "hackenberg_number": "01-040404", "entry_year": "1433",
                "entry_source": "", "end_year": "1454", "end_type": "",
                "notes": "A test note.",
            },
        ])
        try:
            count = load_pa_csv(pa_db, csv_path)
            assert count == 2

            rows = pa_db.execute("SELECT * FROM politically_active_men ORDER BY id").fetchall()
            assert len(rows) == 2
            assert rows[0]["surname"] == "Babalio"
            assert rows[0]["name"] == "Andreas"
            assert rows[0]["match_status"] == "unmatched"
            assert rows[0]["person_id"] is None
            assert rows[1]["notes"] == "A test note."
        finally:
            os.unlink(csv_path)

    def test_load_idempotent(self, pa_db):
        csv_path = _make_pa_csv([
            {
                "id": "18", "surname": "Babalio", "name": "Andreas",
                "father": "Volcius", "grandfather": "",
                "hackenberg_number": "01-040102", "entry_year": "1421",
                "entry_source": "", "end_year": "1473", "end_type": "",
                "notes": "",
            },
        ])
        try:
            load_pa_csv(pa_db, csv_path)
            load_pa_csv(pa_db, csv_path)  # Second load should not duplicate
            count = pa_db.execute("SELECT COUNT(*) FROM politically_active_men").fetchone()[0]
            assert count == 1
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Candidate generation tests
# ---------------------------------------------------------------------------


class TestCandidateGeneration:
    def test_surname_blocking(self, pa_db):
        csv_path = _make_pa_csv([
            {
                "id": "18", "surname": "Babalio", "name": "Andreas",
                "father": "Volcius", "grandfather": "",
                "hackenberg_number": "01-040102", "entry_year": "1421",
                "entry_source": "", "end_year": "1473", "end_type": "",
                "notes": "",
            },
        ])
        try:
            load_pa_csv(pa_db, csv_path)
            candidates = generate_pa_candidates(pa_db)

            # Should find Babalio males only, not Goce or female Babalio
            person_ids = {c["person"]["id"] for c in candidates}
            assert 102 in person_ids  # Andreas Babalio (father Volcius)
            assert 103 in person_ids  # Andreas Babalio (father Savinus)
            assert 105 not in person_ids  # Andreas Goce — wrong surname
            assert 106 not in person_ids  # Maria Babalio — female
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestScoring:
    def test_exact_match_high_score(self, pa_db):
        """PA 18 (Andreas, father Volcius, end 1473) should score high against GEDCOM 102."""
        pa_row = {
            "id": 18, "surname": "Babalio", "name": "Andreas",
            "father": "Volcius", "grandfather": "",
            "entry_year": "1421", "end_year": "1473", "end_type": "",
        }
        person = {
            "id": 102, "given_name": "Andreas", "surname": "Babalio",
            "birth_year_min": 1399, "death_year_min": 1473,
        }
        result = score_pa_match(pa_db, pa_row, person)
        assert result["score"] >= 0.85
        assert result["name_score"] == 1.0
        assert result["father_score"] == 1.0
        assert result["date_score"] == 1.0

    def test_wrong_father_lower_score(self, pa_db):
        """Same name but different father should score lower."""
        pa_row = {
            "id": 18, "surname": "Babalio", "name": "Andreas",
            "father": "Volcius", "grandfather": "",
            "entry_year": "1421", "end_year": "1473", "end_type": "",
        }
        person = {
            "id": 103, "given_name": "Andreas", "surname": "Babalio",
            "birth_year_min": 1420, "death_year_min": 1490,
        }
        result = score_pa_match(pa_db, pa_row, person)
        # Father is Savinus, not Volcius — father_score should be 0.0
        assert result["father_score"] == 0.0
        # Overall score should be lower than the correct match
        assert result["score"] < 0.70


# ---------------------------------------------------------------------------
# Full pipeline test
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_run_pa_matching(self, pa_db):
        csv_path = _make_pa_csv([
            {
                "id": "18", "surname": "Babalio", "name": "Andreas",
                "father": "Volcius", "grandfather": "",
                "hackenberg_number": "01-040102", "entry_year": "1421",
                "entry_source": "", "end_year": "1473", "end_type": "",
                "notes": "",
            },
        ])
        try:
            load_pa_csv(pa_db, csv_path)
            results = run_pa_matching(pa_db, verbose=False)

            # Should auto-match PA 18 to GEDCOM 102
            pa_row = pa_db.execute(
                "SELECT person_id, match_status, match_score "
                "FROM politically_active_men WHERE id = 18"
            ).fetchone()
            assert pa_row["person_id"] == 102
            assert pa_row["match_status"] == "auto_matched"
            assert pa_row["match_score"] >= 0.85
            assert results["auto_matched"] >= 1
        finally:
            os.unlink(csv_path)

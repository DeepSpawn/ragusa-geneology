"""Tests for ragusa.dedup.scoring."""

from __future__ import annotations

import pytest

from ragusa.dedup.scoring import (
    _extract_surname_from_filiation,
    _latin_root,
    _score_children,
    _score_dates,
    _score_filiation,
    _score_name,
    _score_spouses,
    score_pair,
)

# ---------------------------------------------------------------------------
# _latin_root
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Petrus", "petr"),
        ("Damianus", "damian"),
        ("Damiano", "damian"),
        ("Margarita", "margarit"),
        ("Clemens", "clemens"),  # 'ens' not a suffix
        ("Maria", "mar"),  # strips 'ia', result is 3 chars (minimum)
        ("Gregorius", "gregor"),  # strips 'ius'
        ("Antonio", "anton"),  # strips 'io'
        ("de", "de"),  # too short to strip
        ("  Petrus  ", "petr"),  # whitespace stripped
        ("PETRUS", "petr"),  # case insensitive
    ],
    ids=[
        "strip_us",
        "strip_us_longer",
        "strip_o",
        "strip_a",
        "no_matching_suffix",
        "strip_ia_minimum",
        "strip_ius",
        "strip_io",
        "too_short",
        "whitespace",
        "uppercase",
    ],
)
def test_latin_root(name, expected):
    assert _latin_root(name) == expected


# ---------------------------------------------------------------------------
# _score_name
# ---------------------------------------------------------------------------


def test_score_name_exact_match():
    pa = {"given_name": "Petrus"}
    pb = {"given_name": "Petrus"}
    assert _score_name(pa, pb) == 1.0


def test_score_name_prefix_match():
    pa = {"given_name": "Petrus"}
    pb = {"given_name": "Petrus Paulus"}
    assert _score_name(pa, pb) == 0.85


def test_score_name_latin_root_match():
    pa = {"given_name": "Damianus"}
    pb = {"given_name": "Damiano"}
    assert _score_name(pa, pb) == 0.9


def test_score_name_first_three_chars():
    pa = {"given_name": "Petronius"}
    pb = {"given_name": "Petrovus"}
    assert _score_name(pa, pb) == 0.7


def test_score_name_no_match():
    pa = {"given_name": "Marinus"}
    pb = {"given_name": "Clemens"}
    assert _score_name(pa, pb) == 0.0


def test_score_name_missing_given():
    pa = {"given_name": None}
    pb = {"given_name": "Petrus"}
    assert _score_name(pa, pb) == 0.3


# ---------------------------------------------------------------------------
# _score_dates
# ---------------------------------------------------------------------------


def test_score_dates_exact():
    pa = {"birth_year_min": 1260, "death_year_min": None}
    pb = {"birth_year_min": 1260, "death_year_min": None}
    assert _score_dates(pa, pb) == 1.0


def test_score_dates_close():
    pa = {"birth_year_min": 1260, "death_year_min": None}
    pb = {"birth_year_min": 1262, "death_year_min": None}
    assert _score_dates(pa, pb) == 0.9


def test_score_dates_moderate():
    pa = {"birth_year_min": 1260, "death_year_min": None}
    pb = {"birth_year_min": 1265, "death_year_min": None}
    assert _score_dates(pa, pb) == 0.6


def test_score_dates_far():
    pa = {"birth_year_min": 1260, "death_year_min": None}
    pb = {"birth_year_min": 1270, "death_year_min": None}
    assert _score_dates(pa, pb) == 0.3


def test_score_dates_too_far():
    pa = {"birth_year_min": 1260, "death_year_min": None}
    pb = {"birth_year_min": 1300, "death_year_min": None}
    assert _score_dates(pa, pb) == 0.0


def test_score_dates_no_data():
    pa = {"birth_year_min": None, "death_year_min": None}
    pb = {"birth_year_min": None, "death_year_min": None}
    assert _score_dates(pa, pb) == 0.5


def test_score_dates_both_birth_and_death():
    pa = {"birth_year_min": 1260, "death_year_min": 1320}
    pb = {"birth_year_min": 1260, "death_year_min": 1320}
    # Average of two 1.0 scores
    assert _score_dates(pa, pb) == 1.0


# ---------------------------------------------------------------------------
# _score_spouses, _score_filiation, _score_children — neutral when no data
# ---------------------------------------------------------------------------


def test_score_spouses_no_data(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    db_conn.execute(
        "INSERT INTO persons (id, source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, 1, '@I1@', 'Test', 'M')"
    )
    db_conn.commit()
    assert _score_spouses(db_conn, 1, 1) == 0.5


def test_score_filiation_no_data(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    db_conn.execute(
        "INSERT INTO persons (id, source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, 1, '@I1@', 'Test', 'M')"
    )
    db_conn.commit()
    assert _score_filiation(db_conn, 1, 1) == 0.5


def test_score_children_no_data(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    db_conn.execute(
        "INSERT INTO persons (id, source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, 1, '@I1@', 'Test', 'M')"
    )
    db_conn.commit()
    assert _score_children(db_conn, 1, 1) == 0.5


# ---------------------------------------------------------------------------
# _extract_surname_from_filiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("marini petri de menze", "menze"),
        ("clementis gondola", "gondola"),
        ("gu. petri de sorgo", "sorgo"),
        ("", None),
        ("de de", None),
    ],
    ids=[
        "with_de",
        "simple",
        "with_gu_de",
        "empty",
        "all_particles",
    ],
)
def test_extract_surname_from_filiation(text, expected):
    assert _extract_surname_from_filiation(text) == expected


# ---------------------------------------------------------------------------
# score_pair (integrated)
# ---------------------------------------------------------------------------


def test_score_pair_weighted(populated_db):
    """Cross-file duplicates (persons 1 & 6) should score reasonably high."""
    person_a = {
        "id": 1,
        "given_name": "Petrus",
        "surname": "Gondola",
        "birth_year_min": 1260,
        "birth_year_max": 1260,
        "death_year_min": 1320,
        "death_year_max": 1320,
    }
    person_b = {
        "id": 6,
        "given_name": "Petrus",
        "surname": "Gondola",
        "birth_year_min": 1261,
        "birth_year_max": 1261,
        "death_year_min": 1320,
        "death_year_max": 1320,
    }
    score = score_pair(populated_db, person_a, person_b)
    assert 0.0 <= score <= 1.0
    # Names match exactly (1.0), dates close (0.9/1.0), should be > 0.5
    assert score > 0.5

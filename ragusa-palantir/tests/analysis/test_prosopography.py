"""Tests for ragusa.analysis.prosopography."""

from __future__ import annotations

import pytest

from ragusa.analysis.prosopography import _ordinal, build_profile, search_persons

# ---------------------------------------------------------------------------
# _ordinal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "n, expected",
    [
        (None, "?"),
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
    ],
)
def test_ordinal(n, expected):
    assert _ordinal(n) == expected


# ---------------------------------------------------------------------------
# build_profile
# ---------------------------------------------------------------------------


def test_build_profile_returns_none_for_missing(populated_db):
    assert build_profile(populated_db, 99999) is None


def test_build_profile_basic_person_fields(populated_db):
    profile = build_profile(populated_db, 1)
    assert profile is not None
    person = profile["person"]
    assert person["given_name"] == "Petrus"
    assert person["surname"] == "Gondola"
    assert person["sex"] == "M"
    assert person["birth_year_min"] == 1260
    assert person["death_year_min"] == 1320


def test_build_profile_has_alternate_names(populated_db):
    profile = build_profile(populated_db, 1)
    assert len(profile["alternate_names"]) > 0


def test_build_profile_has_family_of_origin(populated_db):
    # Person 3 (Damianus) is child of family 1 (Petrus + Margarita)
    profile = build_profile(populated_db, 3)
    assert profile is not None
    origin = profile["family_of_origin"]
    assert origin is not None
    assert origin["father"] is not None
    assert origin["mother"] is not None


def test_build_profile_has_marriages(populated_db):
    # Person 1 (Petrus) is husband in family 1
    profile = build_profile(populated_db, 1)
    assert len(profile["marriages"]) >= 1
    marriage = profile["marriages"][0]
    assert marriage["spouse"] is not None


def test_build_profile_has_annotations(populated_db):
    # Person 1 has a filiation annotation
    profile = build_profile(populated_db, 1)
    assert "filiation" in profile["annotations"]


def test_build_profile_has_source_references(populated_db):
    # Person 1 has a source reference
    profile = build_profile(populated_db, 1)
    assert len(profile["source_references"]) > 0


# ---------------------------------------------------------------------------
# search_persons
# ---------------------------------------------------------------------------


def test_search_persons_by_surname(populated_db):
    results = search_persons(populated_db, surname="Gondola")
    assert len(results) > 0
    for r in results:
        assert r["surname"] == "Gondola"


def test_search_persons_by_sex(populated_db):
    results = search_persons(populated_db, sex="F")
    assert len(results) > 0
    for r in results:
        assert r["sex"] == "F"


def test_search_persons_empty_result(populated_db):
    results = search_persons(populated_db, surname="Nonexistent")
    assert results == []

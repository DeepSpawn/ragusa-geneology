"""Tests for ragusa.analysis.family_network."""

from __future__ import annotations

import pytest

from ragusa.analysis.family_network import (
    find_kinship_path,
    get_endogamy_rate,
    get_marriage_alliances,
    get_marriage_frequency_matrix,
    get_marriage_network,
)


# ---------------------------------------------------------------------------
# get_marriage_alliances
# ---------------------------------------------------------------------------


def test_get_marriage_alliances_basic(populated_db):
    alliances = get_marriage_alliances(populated_db, "Gondola")
    assert isinstance(alliances, list)
    partner_surnames = {a["partner_surname"] for a in alliances}
    # Petrus Gondola married Margarita Mence, Damianus married Maria Babalio,
    # Clemens married Elena Goce
    assert "Mence" in partner_surnames
    assert "Babalio" in partner_surnames
    assert "Goce" in partner_surnames


def test_get_marriage_alliances_year_filter(populated_db):
    alliances = get_marriage_alliances(populated_db, "Gondola", year_min=1310)
    # Only families 2 (1315) and 3 (1318) qualify
    years = []
    for a in alliances:
        for m in a["marriages"]:
            if m.get("year"):
                years.append(m["year"])
    assert all(y >= 1310 for y in years if y is not None)


def test_get_marriage_alliances_unknown_surname(populated_db):
    alliances = get_marriage_alliances(populated_db, "Nonexistent")
    assert alliances == []


# ---------------------------------------------------------------------------
# get_marriage_network
# ---------------------------------------------------------------------------


def test_get_marriage_network_basic(populated_db):
    edges = get_marriage_network(populated_db)
    assert isinstance(edges, list)
    assert len(edges) > 0
    for edge in edges:
        assert "family_a" in edge
        assert "family_b" in edge
        assert "count" in edge


def test_get_marriage_network_min_marriages_filter(populated_db):
    edges = get_marriage_network(populated_db, min_marriages=5)
    # No family pair has 5+ marriages in test data
    assert edges == []


# ---------------------------------------------------------------------------
# get_marriage_frequency_matrix
# ---------------------------------------------------------------------------


def test_get_marriage_frequency_matrix_shape(populated_db):
    result = get_marriage_frequency_matrix(populated_db, top_n=5)
    assert "families" in result
    assert "matrix" in result
    n = len(result["families"])
    assert len(result["matrix"]) == n
    for row in result["matrix"]:
        assert len(row) == n


# ---------------------------------------------------------------------------
# get_endogamy_rate
# ---------------------------------------------------------------------------


def test_get_endogamy_rate_no_endogamous(populated_db):
    rate = get_endogamy_rate(populated_db, "Gondola")
    # All Gondola marriages are with different surnames
    assert rate["endogamous"] == 0
    assert rate["endogamy_rate"] == 0.0


def test_get_endogamy_rate_no_marriages(populated_db):
    rate = get_endogamy_rate(populated_db, "Nonexistent")
    assert rate["total_marriages"] == 0
    assert rate["endogamy_rate"] == 0


# ---------------------------------------------------------------------------
# find_kinship_path
# ---------------------------------------------------------------------------


def test_find_kinship_path_self(populated_db):
    path = find_kinship_path(populated_db, 1, 1)
    assert path is not None
    assert len(path) == 1
    assert path[0]["person_id"] == 1


def test_find_kinship_path_spouse(populated_db):
    # Person 1 (Petrus) and Person 2 (Margarita) are married
    path = find_kinship_path(populated_db, 1, 2)
    assert path is not None
    assert len(path) == 2
    assert path[0]["person_id"] == 1
    assert path[1]["person_id"] == 2


def test_find_kinship_path_parent_child(populated_db):
    # Person 1 (Petrus) is parent of Person 3 (Damianus) via family 1
    path = find_kinship_path(populated_db, 1, 3)
    assert path is not None
    assert path[0]["person_id"] == 1
    assert path[-1]["person_id"] == 3


def test_find_kinship_path_no_connection(populated_db):
    # Insert an isolated person with no family ties
    populated_db.execute(
        "INSERT INTO persons"
        " (id, source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (99, 1, '@I99@', 'Isolated', 'Nobody', 'Isolated Nobody', 'M')"
    )
    path = find_kinship_path(populated_db, 1, 99)
    assert path is None

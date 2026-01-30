"""Tests for ragusa.parser.gedcom_loader."""

from __future__ import annotations

import pytest

from ragusa.parser.gedcom_loader import _parse_date, _parse_name

# ---------------------------------------------------------------------------
# _parse_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_given, expected_surname, expected_alt_count",
    [
        ("Petrus Gondola", "Petrus", "Gondola", 0),
        ("Damianus Petrus Gondola", "Damianus Petrus", "Gondola", 0),
        ("Damianus (Damiano) Sorgo", "Damianus", "Sorgo", 1),
        (" Babalio", None, "Babalio", 0),
        ("", None, None, 0),
        ("  ", None, None, 0),
        ("Domagna de Babalio", "Domagna", "Babalio", 0),
        ("Marinus del Gondola", "Marinus", "Gondola", 0),
        ("Petrus di Sorgo", "Petrus", "Sorgo", 0),
        ("Marinus da Goce", "Marinus", "Goce", 0),
        ("Petrus", "Petrus", None, 0),
        ("frater Marinus", "frater", "Marinus", 0),
        ("de Gondola", None, "Gondola", 0),
    ],
    ids=[
        "two_word",
        "multi_word_given",
        "parenthetical_alt",
        "leading_space_surname_only",
        "empty",
        "whitespace_only",
        "particle_de",
        "particle_del",
        "particle_di",
        "particle_da",
        "single_word_given",
        "frater_not_particle",
        "particle_only_given",
    ],
)
def test_parse_name(raw, expected_given, expected_surname, expected_alt_count):
    given, surname, alts = _parse_name(raw)
    assert given == expected_given
    assert surname == expected_surname
    assert len(alts) == expected_alt_count


def test_parse_name_parenthetical_alt_details():
    """Verify the parenthetical alternate name has correct fields."""
    given, surname, alts = _parse_name("Damianus (Damiano) Sorgo")
    assert len(alts) == 1
    alt = alts[0]
    assert alt["type"] == "parenthetical"
    assert alt["given_name"] == "Damiano"
    assert alt["surname"] == "Sorgo"


def test_parse_name_leading_space_with_parenthetical():
    """Leading space + parenthetical: surname only, alt name created."""
    given, surname, alts = _parse_name(" (Damiano) Gondola")
    assert given is None
    assert surname == "Gondola"
    assert len(alts) == 1
    assert alts[0]["given_name"] == "Damiano"


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "date_str, expected",
    [
        ("1399", (1399, 1399)),
        ("1189-1190", (1189, 1190)),
        ("1482-83", (1482, 1483)),
        ("1400-450", (1400, 1450)),
        ("9 Jul 2001", (2001, 2001)),
        ("ABT 1300", (1300, 1300)),
        ("BEF 1320", (1320, 1320)),
        ("AFT 1400", (1400, 1400)),
        ("EST 1250", (1250, 1250)),
        ("3 JAN 1285", (1285, 1285)),
        ("", (None, None)),
        ("   ", (None, None)),
        ("no date here", (None, None)),
    ],
    ids=[
        "single_year",
        "full_range",
        "short_range_2digit",
        "short_range_3digit",
        "gedcom_day_month_year",
        "modifier_abt",
        "modifier_bef",
        "modifier_aft",
        "modifier_est",
        "gedcom_day_month",
        "empty",
        "whitespace",
        "no_year",
    ],
)
def test_parse_date(date_str, expected):
    assert _parse_date(date_str) == expected


def test_parse_date_range_min_max_ordering():
    """When the range end looks smaller, output should be (min, max)."""
    # "1500-1490" → regex captures 1500 and 1490 (4-digit), then min/max applied
    result = _parse_date("1500-1490")
    assert result == (1490, 1500)

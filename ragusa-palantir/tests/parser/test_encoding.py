"""Tests for ragusa.parser.encoding."""

from __future__ import annotations

import pytest

from ragusa.parser.encoding import get_python_encoding, normalize_text

# ---------------------------------------------------------------------------
# get_python_encoding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "charset, expected",
    [
        ("ANSEL", "latin-1"),
        ("IBMPC", "cp852"),
        ("ASCII", "ascii"),
        ("UTF-8", "utf-8"),
        ("UNICODE", "utf-16"),
        ("ANSI", "cp1252"),
    ],
)
def test_get_python_encoding_known_charsets(charset, expected):
    assert get_python_encoding(charset) == expected


@pytest.mark.parametrize(
    "charset, expected",
    [
        ("ansel", "latin-1"),
        ("Utf-8", "utf-8"),
        ("ibmpc", "cp852"),
    ],
)
def test_get_python_encoding_case_insensitive(charset, expected):
    assert get_python_encoding(charset) == expected


@pytest.mark.parametrize("charset", ["UNKNOWN", "MACROMAN", ""])
def test_get_python_encoding_unknown_fallback(charset):
    assert get_python_encoding(charset) == "latin-1"


# ---------------------------------------------------------------------------
# normalize_text — ANSEL branch
# ---------------------------------------------------------------------------


def test_normalize_text_ansel_d9_dollar():
    """\\xd9$ sequence should become č (Croatian c-caron)."""
    assert normalize_text("h\xd9$i Marini", "ANSEL") == "hči Marini"


def test_normalize_text_ansel_d8():
    """\\xd8 should become š (Croatian s-caron)."""
    assert normalize_text("Mi\xd8tet", "ANSEL") == "Mištet"


def test_normalize_text_ansel_ea_combining():
    """\\xea followed by a letter should become ć + that letter."""
    result = normalize_text("eti\xeaa", "ANSEL")
    assert "ć" in result


def test_normalize_text_ansel_combined_replacements():
    """All three ANSEL patterns should be normalized in one pass."""
    text = "h\xd9$i Mi\xd8tet \xeaa"
    result = normalize_text(text, "ANSEL")
    assert "č" in result
    assert "š" in result
    assert "ć" in result


# ---------------------------------------------------------------------------
# normalize_text — passthrough for other charsets
# ---------------------------------------------------------------------------


def test_normalize_text_ibmpc_passthrough():
    text = "hči Clementis Dersie"
    assert normalize_text(text, "IBMPC") == text


def test_normalize_text_utf8_passthrough():
    text = "Some text with diacritics čšž"
    assert normalize_text(text, "UTF-8") == text


def test_normalize_text_case_insensitive_charset():
    """Charset string should be handled case-insensitively."""
    result = normalize_text("h\xd9$i", "ansel")
    assert "č" in result

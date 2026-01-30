"""Tests for ragusa.parser.gedcom_reader."""

from __future__ import annotations

import re

import pytest

from ragusa.parser.gedcom_reader import GedcomLine, _LINE_RE, detect_charset, parse_gedcom_file


# ---------------------------------------------------------------------------
# _LINE_RE regex tests
# ---------------------------------------------------------------------------


def test_line_regex_with_xref():
    m = _LINE_RE.match("0 @I1@ INDI")
    assert m is not None
    assert m.group(1) == "0"
    assert m.group(2) == "@I1@"
    assert m.group(3) == "INDI"
    assert m.group(4) is None


def test_line_regex_with_value():
    m = _LINE_RE.match("1 NAME Petrus Gondola")
    assert m is not None
    assert m.group(1) == "1"
    assert m.group(2) is None
    assert m.group(3) == "NAME"
    assert m.group(4) == "Petrus Gondola"


def test_line_regex_no_value():
    m = _LINE_RE.match("1 BIRT")
    assert m is not None
    assert m.group(1) == "1"
    assert m.group(3) == "BIRT"
    assert m.group(4) is None


def test_line_regex_continuation():
    m = _LINE_RE.match("2 CONT list 2, veja 6")
    assert m is not None
    assert m.group(3) == "CONT"
    assert m.group(4) == "list 2, veja 6"


def test_line_regex_malformed_no_match():
    assert _LINE_RE.match("this is not a GEDCOM line") is None


# ---------------------------------------------------------------------------
# detect_charset
# ---------------------------------------------------------------------------


def test_detect_charset_ibmpc(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n1 CHAR IBMPC\n0 TRLR\n", encoding="latin-1")
    assert detect_charset(str(f)) == "IBMPC"


def test_detect_charset_ansel(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n1 CHAR ANSEL\n0 TRLR\n", encoding="latin-1")
    assert detect_charset(str(f)) == "ANSEL"


def test_detect_charset_fallback_utf8(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n1 SOUR PAF\n0 TRLR\n", encoding="latin-1")
    assert detect_charset(str(f)) == "UTF-8"


def test_detect_charset_empty_file(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("", encoding="latin-1")
    assert detect_charset(str(f)) == "UTF-8"


# ---------------------------------------------------------------------------
# parse_gedcom_file
# ---------------------------------------------------------------------------


def test_parse_gedcom_file_basic(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text(
        "0 HEAD\n"
        "1 CHAR ASCII\n"
        "0 @I1@ INDI\n"
        "1 NAME Petrus Gondola\n"
        "0 TRLR\n",
        encoding="ascii",
    )
    lines = parse_gedcom_file(str(f), "ASCII")
    assert len(lines) == 5
    assert lines[0].tag == "HEAD"
    assert lines[2].xref == "@I1@"
    assert lines[2].tag == "INDI"
    assert lines[3].tag == "NAME"
    assert lines[3].value == "Petrus Gondola"


def test_parse_gedcom_file_malformed_line(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text(
        "0 HEAD\n"
        "not a valid line\n"
        "0 TRLR\n",
        encoding="ascii",
    )
    lines = parse_gedcom_file(str(f), "ASCII")
    malformed = [l for l in lines if l.tag == "_INVALID"]
    assert len(malformed) == 1
    assert malformed[0].level == 0


def test_parse_gedcom_file_blank_lines_skipped(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n\n   \n0 TRLR\n", encoding="ascii")
    lines = parse_gedcom_file(str(f), "ASCII")
    assert len(lines) == 2  # HEAD and TRLR only


def test_parse_gedcom_file_auto_detect_charset(tmp_path):
    f = tmp_path / "test.ged"
    f.write_text("0 HEAD\n1 CHAR ASCII\n0 TRLR\n", encoding="ascii")
    lines = parse_gedcom_file(str(f))  # charset=None triggers auto-detection
    assert len(lines) == 3
    assert lines[1].tag == "CHAR"

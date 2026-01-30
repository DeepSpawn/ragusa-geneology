"""Tests for ragusa.parser.gedcom_tree."""

from __future__ import annotations

import pytest

from ragusa.parser.gedcom_reader import GedcomLine
from ragusa.parser.gedcom_tree import GedcomRecord, build_tree


def make_gedcom_line(
    line_number: int,
    level: int,
    tag: str,
    xref: str | None = None,
    value: str | None = None,
) -> GedcomLine:
    """Build a GedcomLine without parsing a file."""
    parts = [str(level)]
    if xref:
        parts.append(xref)
    parts.append(tag)
    if value:
        parts.append(value)
    raw = " ".join(parts)
    return GedcomLine(
        line_number=line_number,
        level=level,
        xref=xref,
        tag=tag,
        value=value,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# build_tree
# ---------------------------------------------------------------------------


def test_build_tree_single_root():
    lines = [make_gedcom_line(1, 0, "HEAD")]
    roots = build_tree(lines)
    assert len(roots) == 1
    assert roots[0].tag == "HEAD"
    assert roots[0].children == []


def test_build_tree_root_with_children():
    lines = [
        make_gedcom_line(1, 0, "INDI", xref="@I1@"),
        make_gedcom_line(2, 1, "NAME", value="Petrus Gondola"),
        make_gedcom_line(3, 1, "SEX", value="M"),
    ]
    roots = build_tree(lines)
    assert len(roots) == 1
    assert len(roots[0].children) == 2
    assert roots[0].children[0].tag == "NAME"
    assert roots[0].children[1].tag == "SEX"


def test_build_tree_nested_three_levels():
    lines = [
        make_gedcom_line(1, 0, "INDI", xref="@I1@"),
        make_gedcom_line(2, 1, "BIRT"),
        make_gedcom_line(3, 2, "DATE", value="1260"),
        make_gedcom_line(4, 2, "PLAC", value="Ragusa"),
    ]
    roots = build_tree(lines)
    assert len(roots) == 1
    birt = roots[0].children[0]
    assert birt.tag == "BIRT"
    assert len(birt.children) == 2
    assert birt.children[0].tag == "DATE"
    assert birt.children[0].value == "1260"
    assert birt.children[1].tag == "PLAC"


def test_build_tree_multiple_roots():
    lines = [
        make_gedcom_line(1, 0, "INDI", xref="@I1@"),
        make_gedcom_line(2, 1, "NAME", value="Petrus"),
        make_gedcom_line(3, 0, "FAM", xref="@F1@"),
        make_gedcom_line(4, 1, "HUSB", value="@I1@"),
    ]
    roots = build_tree(lines)
    assert len(roots) == 2
    assert roots[0].tag == "INDI"
    assert roots[1].tag == "FAM"


def test_build_tree_sibling_reset():
    """After a level-2 child, a new level-1 resets as sibling of the first level-1."""
    lines = [
        make_gedcom_line(1, 0, "INDI"),
        make_gedcom_line(2, 1, "BIRT"),
        make_gedcom_line(3, 2, "DATE", value="1260"),
        make_gedcom_line(4, 1, "DEAT"),
    ]
    roots = build_tree(lines)
    root = roots[0]
    assert len(root.children) == 2
    assert root.children[0].tag == "BIRT"
    assert len(root.children[0].children) == 1  # DATE
    assert root.children[1].tag == "DEAT"
    assert root.children[1].children == []


def test_build_tree_empty_input():
    assert build_tree([]) == []


# ---------------------------------------------------------------------------
# GedcomRecord methods
# ---------------------------------------------------------------------------


def _make_record_with_children():
    """Helper: build a parent record with NAME and SEX children."""
    parent_line = make_gedcom_line(1, 0, "INDI")
    name_line = make_gedcom_line(2, 1, "NAME", value="Petrus")
    sex_line = make_gedcom_line(3, 1, "SEX", value="M")
    parent = GedcomRecord(line=parent_line)
    parent.children = [
        GedcomRecord(line=name_line),
        GedcomRecord(line=sex_line),
    ]
    return parent


def test_gedcom_record_find_existing():
    rec = _make_record_with_children()
    found = rec.find("NAME")
    assert found is not None
    assert found.value == "Petrus"


def test_gedcom_record_find_missing():
    rec = _make_record_with_children()
    assert rec.find("BIRT") is None


def test_gedcom_record_find_all():
    parent_line = make_gedcom_line(1, 0, "INDI")
    parent = GedcomRecord(line=parent_line)
    parent.children = [
        GedcomRecord(line=make_gedcom_line(2, 1, "NOTE", value="note1")),
        GedcomRecord(line=make_gedcom_line(3, 1, "NOTE", value="note2")),
    ]
    notes = parent.find_all("NOTE")
    assert len(notes) == 2


def test_gedcom_record_get_text_simple():
    rec = GedcomRecord(line=make_gedcom_line(1, 1, "NOTE", value="Some text"))
    assert rec.get_text() == "Some text"


def test_gedcom_record_get_text_with_cont():
    rec = GedcomRecord(line=make_gedcom_line(1, 1, "NOTE", value="line 1"))
    rec.children = [GedcomRecord(line=make_gedcom_line(2, 2, "CONT", value="line 2"))]
    assert rec.get_text() == "line 1\nline 2"


def test_gedcom_record_get_text_with_conc():
    rec = GedcomRecord(line=make_gedcom_line(1, 1, "NOTE", value="hel"))
    rec.children = [GedcomRecord(line=make_gedcom_line(2, 2, "CONC", value="lo"))]
    assert rec.get_text() == "hello"


def test_gedcom_record_get_text_mixed_cont_conc():
    rec = GedcomRecord(line=make_gedcom_line(1, 1, "NOTE", value="a"))
    rec.children = [
        GedcomRecord(line=make_gedcom_line(2, 2, "CONC", value="b")),
        GedcomRecord(line=make_gedcom_line(3, 2, "CONT", value="c")),
        GedcomRecord(line=make_gedcom_line(4, 2, "CONC", value="d")),
    ]
    assert rec.get_text() == "ab\ncd"


def test_gedcom_record_get_child_value():
    rec = _make_record_with_children()
    # Add a DATE child for lookup
    rec.children.append(GedcomRecord(line=make_gedcom_line(4, 1, "DATE", value="1285")))
    assert rec.get_child_value("DATE") == "1285"
    assert rec.get_child_value("PLAC") is None

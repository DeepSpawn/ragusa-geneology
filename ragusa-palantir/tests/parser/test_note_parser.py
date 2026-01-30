"""Tests for ragusa.parser.note_parser."""

from __future__ import annotations

import pytest

from ragusa.parser.note_parser import (
    ParsedNote,
    SourceRef,
    _extract_year_range,
    parse_note_block,
)


# ---------------------------------------------------------------------------
# _extract_year_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1367-1374", (1367, 1374)),
        ("1399", (1399, 1399)),
        ("1325-30", (1325, 1330)),
        ("no year", (None, None)),
        ("", (None, None)),
        ("ca. 1400", (1400, 1400)),
    ],
    ids=[
        "full_range",
        "single_year",
        "short_form",
        "no_year",
        "empty",
        "ca_prefix",
    ],
)
def test_extract_year_range(text, expected):
    assert _extract_year_range(text) == expected


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def test_parse_note_block_section_headers():
    lines = [
        "SOURCE NOTES:",
        "list 2, veja 6",
        "RESEARCH NOTES:",
        "hči Marini Gondola",
    ]
    results = parse_note_block(lines)
    categories = [n.category for n in results]
    assert "SOURCE NOTES" in categories
    assert "RESEARCH NOTES" in categories


def test_parse_note_block_general_category():
    results = parse_note_block(["some text without a header"])
    assert len(results) == 1
    assert results[0].category == "GENERAL"


def test_parse_note_block_embedded_newlines():
    """Newlines within a single line should split into separate sections."""
    lines = ["SOURCE NOTES:\nlist 2, veja 6\nRESEARCH NOTES:\nhči Petri Gondola"]
    results = parse_note_block(lines)
    categories = [n.category for n in results]
    assert "SOURCE NOTES" in categories
    assert "RESEARCH NOTES" in categories


def test_parse_note_block_empty_lines_ignored():
    lines = ["RESEARCH NOTES:", "", "  ", "hči Marini Gondola"]
    results = parse_note_block(lines)
    research = [n for n in results if n.category == "RESEARCH NOTES"]
    assert len(research) == 1
    assert len(research[0].annotations) == 1
    assert research[0].annotations[0].annotation_type == "filiation"


# ---------------------------------------------------------------------------
# Source line parsing
# ---------------------------------------------------------------------------


def test_source_list_veja():
    results = parse_note_block(["SOURCE NOTES:", "list 2, veja 6"])
    src = [n for n in results if n.category == "SOURCE NOTES"]
    assert len(src) == 1
    refs = src[0].source_refs
    assert len(refs) == 1
    assert refs[0].list_number == 2
    assert refs[0].veja_number == 6


def test_source_list_only():
    results = parse_note_block(["SOURCE NOTES:", "list 3"])
    refs = [n for n in results if n.category == "SOURCE NOTES"][0].source_refs
    assert len(refs) == 1
    assert refs[0].list_number == 3
    assert refs[0].veja_number is None


def test_source_veja_only():
    results = parse_note_block(["SOURCE NOTES:", "veja 12"])
    refs = [n for n in results if n.category == "SOURCE NOTES"][0].source_refs
    assert len(refs) == 1
    assert refs[0].list_number is None
    assert refs[0].veja_number == 12


def test_source_also_name():
    results = parse_note_block(["SOURCE NOTES:", "Also: Petar Gundulić"])
    src = [n for n in results if n.category == "SOURCE NOTES"][0]
    assert "Petar Gundulić" in src.also_names


# ---------------------------------------------------------------------------
# Filiation annotations
# ---------------------------------------------------------------------------


def test_filiation_daughter():
    results = parse_note_block(["RESEARCH NOTES:", "hči Marini Petri de Menze"])
    ann = _get_research_annotations(results)
    assert len(ann) == 1
    assert ann[0].annotation_type == "filiation"
    assert ann[0].subtype == "daughter"


def test_filiation_son():
    results = parse_note_block(["RESEARCH NOTES:", "sin Clementis Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "filiation"
    assert ann[0].subtype == "son"


def test_filiation_illegitimate_daughter():
    results = parse_note_block(["RESEARCH NOTES:", "hči nat Petri Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].subtype == "illegitimate_daughter"


def test_filiation_illegitimate_son():
    results = parse_note_block(["RESEARCH NOTES:", "sin nat Marini Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].subtype == "illegitimate_son"


def test_filiation_quondam():
    results = parse_note_block(["RESEARCH NOTES:", "hči gu. Petri Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "filiation"
    assert ann[0].value.startswith("gu.")


# ---------------------------------------------------------------------------
# Illegitimate / bastard
# ---------------------------------------------------------------------------


def test_bastard():
    results = parse_note_block(["RESEARCH NOTES:", "bastardus"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "illegitimate"


def test_fil_nat():
    results = parse_note_block(["RESEARCH NOTES:", "fil. nat. Petri 1300"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "illegitimate"
    assert ann[0].subtype == "fil. nat."


# ---------------------------------------------------------------------------
# Alias
# ---------------------------------------------------------------------------


def test_dictus():
    results = parse_note_block(["RESEARCH NOTES:", "dictus Lupus"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "alias"
    assert ann[0].value == "Lupus"


# ---------------------------------------------------------------------------
# Monastic / religious
# ---------------------------------------------------------------------------


def test_religiosa():
    results = parse_note_block(["RESEARCH NOTES:", "religiosa Stagno"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert ann[0].subtype == "religiosa"


def test_monastic_simple():
    results = parse_note_block(["RESEARCH NOTES:", "mon. Lacroma"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert "Lacroma" in ann[0].value


def test_monastic_with_year():
    results = parse_note_block(["RESEARCH NOTES:", "1345 mon. Lacromae"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert ann[0].date_year_min == 1345


def test_monastic_with_religious_name():
    results = parse_note_block(["RESEARCH NOTES:", "1400 mon. (soror Clara)"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert ann[0].subtype == "soror Clara"


def test_monastic_gt_prefix():
    results = parse_note_block(["RESEARCH NOTES:", "> 1522 mon."])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert ann[0].date_year_min == 1522


def test_religious_order():
    results = parse_note_block(["RESEARCH NOTES:", "ord. Sancti Benedicti"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "monastic"
    assert "Sancti Benedicti" in ann[0].value


def test_frater():
    results = parse_note_block(["RESEARCH NOTES:", "frater Marinus"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "religious_name"


def test_soror():
    results = parse_note_block(["RESEARCH NOTES:", "soror Clara"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "religious_name"


# ---------------------------------------------------------------------------
# Clerical
# ---------------------------------------------------------------------------


def test_clerical_presbiter():
    results = parse_note_block(["RESEARCH NOTES:", "presbiter ecclesiae"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "clerical"


def test_clerical_with_year():
    results = parse_note_block(["RESEARCH NOTES:", "canonicus 1350"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "clerical"
    assert ann[0].date_year_min == 1350


def test_reclusa():
    results = parse_note_block(["RESEARCH NOTES:", "reclusa"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "recluse"


# ---------------------------------------------------------------------------
# Marriage
# ---------------------------------------------------------------------------


def test_marriage_second():
    results = parse_note_block([
        "RESEARCH NOTES:",
        "drugič poročena 1315 z Marinus Sorgo",
    ])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "alt_marriage"
    assert ann[0].subtype == "second_marriage"
    assert ann[0].date_year_min == 1315
    assert "Marinus Sorgo" in ann[0].value


def test_marriage_first():
    results = parse_note_block([
        "RESEARCH NOTES:",
        "prvič poročena 1290 z Petrus Gondola",
    ])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "alt_marriage"
    assert ann[0].subtype == "first_marriage"


# ---------------------------------------------------------------------------
# Relicta, uxor, sestra
# ---------------------------------------------------------------------------


def test_relicta_with_year():
    results = parse_note_block(["RESEARCH NOTES:", "1350 relicta Marini Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "relicta"
    assert ann[0].date_year_min == 1350


def test_relicta_no_year():
    results = parse_note_block(["RESEARCH NOTES:", "relicta Clementis Sorgo"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "relicta"
    assert ann[0].date_year_min is None


def test_uxor():
    results = parse_note_block(["RESEARCH NOTES:", "ux. Petri Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "uxor"
    assert ann[0].value == "Petri Gondola"


def test_sestra():
    results = parse_note_block(["RESEARCH NOTES:", "sestra Damiani Gondola"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "family_relation"
    assert ann[0].subtype == "sister"


# ---------------------------------------------------------------------------
# Profession, citizenship, burial
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["aromatarius", "notarius", "medicus"])
def test_profession(text):
    results = parse_note_block(["RESEARCH NOTES:", text])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "profession"


def test_citizenship():
    results = parse_note_block(["RESEARCH NOTES:", "1390 civis Ragusii"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "citizenship"
    assert ann[0].date_year_min == 1390
    assert ann[0].value == "Ragusii"


def test_burial():
    results = parse_note_block(["RESEARCH NOTES:", "sepelitus in ecclesia"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "burial"
    assert ann[0].value == "in ecclesia"


# ---------------------------------------------------------------------------
# Source ref in research, fallback, combined
# ---------------------------------------------------------------------------


def test_source_ref_in_research():
    results = parse_note_block(["RESEARCH NOTES:", "list 5, veja 10"])
    research = [n for n in results if n.category == "RESEARCH NOTES"]
    assert len(research[0].source_refs) == 1
    assert research[0].source_refs[0].list_number == 5


def test_unrecognized_falls_to_other():
    results = parse_note_block(["RESEARCH NOTES:", "some unknown text"])
    ann = _get_research_annotations(results)
    assert ann[0].annotation_type == "other"


def test_combined_filiation_marriage():
    """Filiation + marriage on one line should produce 2 annotations."""
    results = parse_note_block([
        "RESEARCH NOTES:",
        "hči Mathie de Balaca, drugič poročena 1279 z Petrus de Dersa",
    ])
    ann = _get_research_annotations(results)
    types = {a.annotation_type for a in ann}
    assert "filiation" in types
    assert "alt_marriage" in types
    assert len(ann) >= 2


def test_also_name_in_research():
    results = parse_note_block(["RESEARCH NOTES:", "Also: Damiano Gondola"])
    research = [n for n in results if n.category == "RESEARCH NOTES"]
    assert "Damiano Gondola" in research[0].also_names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_research_annotations(results: list[ParsedNote]):
    """Extract annotations from RESEARCH NOTES (or GENERAL) sections."""
    annotations = []
    for n in results:
        if n.category in ("RESEARCH NOTES", "GENERAL"):
            annotations.extend(n.annotations)
    return annotations

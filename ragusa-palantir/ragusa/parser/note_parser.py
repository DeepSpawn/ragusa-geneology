"""Parse GEDCOM NOTE fields into structured annotations.

Notes in these files follow a consistent structure:

    1 NOTE SOURCE NOTES:
    1 NOTE list 2, veja 6            <- archival source reference
    1 NOTE RESEARCH NOTES:
    1 NOTE hči Marini Petri de Menze <- structured research annotation

Or (in Ragusan.ged) with CONT continuation:

    1 NOTE SOURCE NOTES:
    2 CONT veja 3
    1 NOTE RESEARCH NOTES:
    2 CONT hči Clementis Dersie

This module extracts:
- Source references (list/veja numbers)
- Alternate names ("Also: X")
- Structured annotations from Latin/Croatian research abbreviations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SourceRef:
    """A parsed archival source reference."""

    list_number: int | None = None
    veja_number: int | None = None
    raw_text: str = ""


@dataclass
class Annotation:
    """A parsed structured annotation from a research note."""

    annotation_type: str  # filiation, illegitimate, monastic, clerical, etc.
    value: str = ""
    subtype: str | None = None  # e.g. 'daughter', 'son', 'second_marriage'
    date_year_min: int | None = None
    date_year_max: int | None = None
    raw_text: str = ""


@dataclass
class ParsedNote:
    """Result of parsing a NOTE block."""

    category: str  # 'SOURCE NOTES', 'RESEARCH NOTES', 'GENERAL'
    raw_text: str
    source_refs: list[SourceRef] = field(default_factory=list)
    also_names: list[str] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)


# Regex patterns for source references
_LIST_RE = re.compile(r"list\s+(\d+)", re.IGNORECASE)
_VEJA_RE = re.compile(r"veja\s+(\d+)", re.IGNORECASE)

# Regex for dates in annotations
_YEAR_RE = re.compile(r"(\d{4})")
_YEAR_RANGE_RE = re.compile(r"(\d{4})\s*-\s*(\d{2,4})")

# Patterns for annotation classification (order matters — check specific before general)
_FILIATION_RE = re.compile(
    r"^(hči|hci|h\w*i|sin)\s+"
    r"(nat\s+)?"  # optional 'nat' for illegitimate
    r"(gu\.\s*)?"  # optional 'gu.' for quondam
    r"(ser\s+)?"  # optional 'ser' for title
    r"(.+)",
    re.IGNORECASE,
)

_ALSO_RE = re.compile(r"^Also:\s*(.+)", re.IGNORECASE)
_BASTARD_RE = re.compile(r"^bastard[aous]+", re.IGNORECASE)
_MONASTIC_RE = re.compile(
    r"^(?:(\d{4})\s+)?(?:>?\s*(\d{4})\s+)?"
    r"mon\.?\s*(.*)",
    re.IGNORECASE,
)
_ORDER_RE = re.compile(r"^ord\.\s*(.+)", re.IGNORECASE)
_FRATER_RE = re.compile(r"^(?:frater|soror|dom\.|fra\.?)\s+(.+)", re.IGNORECASE)
_FIL_NAT_RE = re.compile(
    r"^fil\.?\s*(?:nat\.?)?\s*(.*)",
    re.IGNORECASE,
)
_RELIGIOSA_RE = re.compile(r"^religiosa\b\s*(.*)", re.IGNORECASE)
_DICTUS_RE = re.compile(r"^dictus\s+(.+)", re.IGNORECASE)
_CLERICAL_RE = re.compile(
    r"^(presbiter|diaconus|subdiacontus|subdiaconus|clericus|canonicus|"
    r"abbas|archidiaconus|episcopus|archipresbiter)"
    r"(?:\s+(.*))?",
    re.IGNORECASE,
)
_RECLUSA_RE = re.compile(r"^reclus[ao]", re.IGNORECASE)
_MARRIAGE_RE = re.compile(
    r"(?:drugic|prvic|prvič|drugič)\s+(?:se\s+)?poro[cč](?:ena|i)\s+"
    r"(\d{4})?\s*(?:z\s+)?(.+)",
    re.IGNORECASE,
)
_RELICTA_RE = re.compile(
    r"^(\d{4})?\s*relicta\s+(.+)",
    re.IGNORECASE,
)
_UX_RE = re.compile(
    r"^ux\.\s+(.*)",
    re.IGNORECASE,
)
_SESTRA_RE = re.compile(r"^sestra\s+(.+)", re.IGNORECASE)
_PROFESSION_RE = re.compile(
    r"^(aromatarius|pilliparius|aurifex|mercator|peliparius|"
    r"sartor|notarius|medicus|magister|judex)\b\s*(.*)",
    re.IGNORECASE,
)
_CIVIS_RE = re.compile(r"^(\d{4})?\s*civis\s+(.+)", re.IGNORECASE)
_SEPULTUS_RE = re.compile(r"^sepel[it]+us\s+(.+)", re.IGNORECASE)


def parse_note_block(
    lines: list[str],
    gedcom_level: int = 1,
) -> list[ParsedNote]:
    """Parse a multi-line NOTE block into structured ParsedNote objects.

    The input is the assembled text from one or more NOTE records (with CONT
    lines already joined by the tree builder). Each NOTE may be a section
    header ("SOURCE NOTES:", "RESEARCH NOTES:") or content.

    Args:
        lines: List of note text strings (one per NOTE record, CONT already joined).
        gedcom_level: The GEDCOM level of the NOTE tags.

    Returns:
        List of ParsedNote objects.
    """
    # Flatten: each note line may contain embedded newlines from CONT assembly.
    # Split them so section headers are detected even when joined with content.
    flat_lines: list[str] = []
    for line in lines:
        flat_lines.extend(line.split("\n"))

    # Split into sections by category headers
    current_category = "GENERAL"
    sections: dict[str, list[str]] = {"GENERAL": []}

    for line in flat_lines:
        stripped = line.strip()
        if stripped == "SOURCE NOTES:":
            current_category = "SOURCE NOTES"
            if current_category not in sections:
                sections[current_category] = []
            continue
        if stripped == "RESEARCH NOTES:":
            current_category = "RESEARCH NOTES"
            if current_category not in sections:
                sections[current_category] = []
            continue
        if current_category not in sections:
            sections[current_category] = []
        sections[current_category].append(stripped)

    results: list[ParsedNote] = []

    for category, content_lines in sections.items():
        if not content_lines:
            continue

        raw_text = "\n".join(content_lines)
        note = ParsedNote(category=category, raw_text=raw_text)

        for content in content_lines:
            if not content:
                continue

            if category == "SOURCE NOTES":
                _parse_source_line(content, note)
            else:
                _parse_research_line(content, note)

        results.append(note)

    return results


def _parse_source_line(text: str, note: ParsedNote) -> None:
    """Parse a SOURCE NOTES line for list/veja refs and Also names."""
    # Check for "Also: X"
    m = _ALSO_RE.match(text)
    if m:
        note.also_names.append(m.group(1).strip())
        return

    # Check for list/veja references
    list_m = _LIST_RE.search(text)
    veja_m = _VEJA_RE.search(text)
    if list_m or veja_m:
        ref = SourceRef(
            list_number=int(list_m.group(1)) if list_m else None,
            veja_number=int(veja_m.group(1)) if veja_m else None,
            raw_text=text,
        )
        note.source_refs.append(ref)
        return

    # Also names can appear without "Also:" prefix — but only if short
    # and doesn't look like a ref. Store as annotation for manual review.
    note.annotations.append(
        Annotation(
            annotation_type="other",
            value=text,
            raw_text=text,
        )
    )


def _parse_research_line(text: str, note: ParsedNote) -> None:
    """Parse a RESEARCH NOTES or GENERAL line into annotations."""
    # Check for combined filiation + marriage note
    # e.g. "hci Mathie de Balaca, drugic porocena 1279 Petrus de Dersa"
    marriage_in_filiation = _MARRIAGE_RE.search(text)
    filiation_part = text
    if marriage_in_filiation and _FILIATION_RE.match(text):
        # Split at the marriage reference
        split_pos = text.lower().find("drugic")
        if split_pos == -1:
            split_pos = text.lower().find("prvic")
        if split_pos == -1:
            split_pos = text.lower().find("prvič")
        if split_pos == -1:
            split_pos = text.lower().find("drugič")
        if split_pos > 0:
            filiation_part = text[:split_pos].rstrip(", ")
            marriage_part = text[split_pos:]
            _parse_filiation(filiation_part, text, note)
            _parse_marriage_ref(marriage_part, text, note)
            return

    # Also names
    m = _ALSO_RE.match(text)
    if m:
        note.also_names.append(m.group(1).strip())
        return

    # Filiation (hči/sin)
    if _FILIATION_RE.match(text):
        _parse_filiation(text, text, note)
        return

    # Bastard
    if _BASTARD_RE.match(text):
        note.annotations.append(
            Annotation(
                annotation_type="illegitimate",
                value=text,
                raw_text=text,
            )
        )
        return

    # fil. / fil. nat. (illegitimate child)
    m = _FIL_NAT_RE.match(text)
    if m and text.lower().startswith("fil"):
        years = _extract_year_range(text)
        note.annotations.append(
            Annotation(
                annotation_type="illegitimate",
                subtype="fil. nat.",
                value=m.group(1).strip() if m.group(1) else text,
                date_year_min=years[0],
                date_year_max=years[1],
                raw_text=text,
            )
        )
        return

    # Dictus (alias)
    m = _DICTUS_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="alias",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Religiosa (woman in religious life)
    m = _RELIGIOSA_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="monastic",
                subtype="religiosa",
                value=m.group(1).strip() if m.group(1) else "religiosa",
                raw_text=text,
            )
        )
        return

    # Monastic (handles: "mon.", "> 1522 mon.", "1470 mon. Lacromae")
    cleaned_text = text.lstrip("> ")
    m = _MONASTIC_RE.match(cleaned_text)
    if m and "mon" in cleaned_text.lower():
        year = None
        if m.group(1):
            year = int(m.group(1))
        elif m.group(2):
            year = int(m.group(2))
        detail = m.group(3).strip() if m.group(3) else ""
        # Check for religious name in parentheses
        religious_name = None
        paren_m = re.search(r"\(([^)]+)\)", detail)
        if paren_m:
            religious_name = paren_m.group(1).strip()
        ann = Annotation(
            annotation_type="monastic",
            value=detail if detail else "entered monastery",
            date_year_min=year,
            date_year_max=year,
            raw_text=text,
        )
        if religious_name:
            ann.subtype = religious_name
        note.annotations.append(ann)
        return

    # Religious order without "mon." prefix
    m = _ORDER_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="monastic",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Frater / soror / dom.
    m = _FRATER_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="religious_name",
                value=m.group(0).strip(),
                raw_text=text,
            )
        )
        return

    # Clerical office
    m = _CLERICAL_RE.match(text)
    if m:
        years = _extract_year_range(text)
        note.annotations.append(
            Annotation(
                annotation_type="clerical",
                value=m.group(0).strip(),
                date_year_min=years[0],
                date_year_max=years[1],
                raw_text=text,
            )
        )
        return

    # Recluse
    if _RECLUSA_RE.match(text):
        note.annotations.append(
            Annotation(
                annotation_type="recluse",
                value=text,
                raw_text=text,
            )
        )
        return

    # Marriage reference (standalone, not combined with filiation)
    m = _MARRIAGE_RE.search(text)
    if m:
        _parse_marriage_ref(text, text, note)
        return

    # Relicta (widow of)
    m = _RELICTA_RE.match(text)
    if m:
        year = int(m.group(1)) if m.group(1) else None
        note.annotations.append(
            Annotation(
                annotation_type="relicta",
                value=m.group(2).strip(),
                date_year_min=year,
                date_year_max=year,
                raw_text=text,
            )
        )
        return

    # Uxor (wife of)
    m = _UX_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="uxor",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Sestra (sister)
    m = _SESTRA_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="family_relation",
                subtype="sister",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Profession
    m = _PROFESSION_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="profession",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Citizenship
    m = _CIVIS_RE.match(text)
    if m:
        year = int(m.group(1)) if m.group(1) else None
        note.annotations.append(
            Annotation(
                annotation_type="citizenship",
                value=m.group(2).strip(),
                date_year_min=year,
                date_year_max=year,
                raw_text=text,
            )
        )
        return

    # Burial
    m = _SEPULTUS_RE.match(text)
    if m:
        note.annotations.append(
            Annotation(
                annotation_type="burial",
                value=m.group(1).strip(),
                raw_text=text,
            )
        )
        return

    # Source reference that ended up in research notes
    list_m = _LIST_RE.search(text)
    veja_m = _VEJA_RE.search(text)
    if list_m or veja_m:
        ref = SourceRef(
            list_number=int(list_m.group(1)) if list_m else None,
            veja_number=int(veja_m.group(1)) if veja_m else None,
            raw_text=text,
        )
        note.source_refs.append(ref)
        return

    # Fallback: unrecognized pattern
    note.annotations.append(
        Annotation(
            annotation_type="other",
            value=text,
            raw_text=text,
        )
    )


def _parse_filiation(text: str, full_text: str, note: ParsedNote) -> None:
    """Parse a filiation note (hči/sin + parent name)."""
    m = _FILIATION_RE.match(text)
    if not m:
        return

    prefix = m.group(1).lower()
    is_nat = bool(m.group(2))
    is_quondam = bool(m.group(3))
    parent_desc = m.group(5).strip()

    # Determine subtype
    if prefix.startswith("sin"):
        subtype = "illegitimate_son" if is_nat else "son"
    else:
        subtype = "illegitimate_daughter" if is_nat else "daughter"

    # Clean up parent description — remove trailing punctuation
    parent_desc = parent_desc.rstrip(",. ")

    # Build value with quondam marker
    value = parent_desc
    if is_quondam:
        value = f"gu. {value}"

    note.annotations.append(
        Annotation(
            annotation_type="filiation",
            subtype=subtype,
            value=value,
            raw_text=full_text,
        )
    )


def _parse_marriage_ref(text: str, full_text: str, note: ParsedNote) -> None:
    """Parse a marriage reference (drugic/prvic porocena)."""
    m = _MARRIAGE_RE.search(text)
    if not m:
        return

    is_second = "drugic" in text.lower() or "drugič" in text.lower()
    subtype = "second_marriage" if is_second else "first_marriage"
    year = int(m.group(1)) if m.group(1) else None
    spouse = m.group(2).strip().rstrip(",. ")

    note.annotations.append(
        Annotation(
            annotation_type="alt_marriage",
            subtype=subtype,
            value=spouse,
            date_year_min=year,
            date_year_max=year,
            raw_text=full_text,
        )
    )


def _extract_year_range(text: str) -> tuple[int | None, int | None]:
    """Extract a year or year range from text.

    Handles: '1367-1374', '1399', '(ca. 1325-30)', etc.
    """
    # Try range first
    m = _YEAR_RANGE_RE.search(text)
    if m:
        y1 = int(m.group(1))
        y2_str = m.group(2)
        if len(y2_str) == 2:
            # Short form: 1482-83 -> 1482-1483
            y2 = (y1 // 100) * 100 + int(y2_str)
        else:
            y2 = int(y2_str)
        return (y1, y2)

    # Try single year
    m = _YEAR_RE.search(text)
    if m:
        y = int(m.group(1))
        return (y, y)

    return (None, None)

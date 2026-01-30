"""Load parsed GEDCOM records into the SQLite database.

Orchestrates the full pipeline: parse file -> build tree -> extract
persons/families/notes -> insert into database.
"""

from __future__ import annotations

import os
import re
import sqlite3

from .gedcom_reader import detect_charset, parse_gedcom_file
from .gedcom_tree import GedcomRecord, build_tree
from .note_parser import parse_note_block


def load_gedcom_file(conn: sqlite3.Connection, filepath: str) -> dict:
    """Parse a GEDCOM file and load all records into the database.

    Args:
        conn: Open database connection (schema must already exist).
        filepath: Path to the .ged file.

    Returns:
        Summary dict with counts: individuals, families, notes, annotations.
    """
    charset = detect_charset(filepath)
    lines = parse_gedcom_file(filepath, charset)
    records = build_tree(lines)

    # Extract header info
    header = records[0] if records and records[0].tag == "HEAD" else None
    gedcom_version = None
    software = None
    date_created = None

    if header:
        gedc = header.find("GEDC")
        if gedc:
            gedcom_version = gedc.get_child_value("VERS")
        sour = header.find("SOUR")
        if sour:
            software = sour.value
            vers = sour.get_child_value("VERS")
            if vers:
                software = f"{software} {vers}"
        date_rec = header.find("DATE")
        if date_rec:
            date_created = date_rec.value

    # Register source file
    cur = conn.execute(
        "INSERT INTO source_files (filename, gedcom_version, encoding, software, date_created) "
        "VALUES (?, ?, ?, ?, ?)",
        (os.path.basename(filepath), gedcom_version, charset, software, date_created),
    )
    source_file_id = cur.lastrowid

    # First pass: load all INDI records
    person_lookup: dict[str, int] = {}  # gedcom_id -> db person_id
    indi_count = 0
    note_count = 0
    annotation_count = 0

    for rec in records:
        if rec.tag == "INDI" and rec.xref:
            pid, n, a = _process_individual(conn, rec, source_file_id)
            person_lookup[rec.xref] = pid
            indi_count += 1
            note_count += n
            annotation_count += a

    # Second pass: load all FAM records
    fam_count = 0
    for rec in records:
        if rec.tag == "FAM" and rec.xref:
            fid, n, a = _process_family(conn, rec, source_file_id, person_lookup)
            fam_count += 1
            note_count += n
            annotation_count += a

    conn.commit()

    return {
        "filename": os.path.basename(filepath),
        "individuals": indi_count,
        "families": fam_count,
        "notes": note_count,
        "annotations": annotation_count,
        "source_file_id": source_file_id,
    }


def _process_individual(
    conn: sqlite3.Connection,
    rec: GedcomRecord,
    source_file_id: int,
) -> tuple[int, int, int]:
    """Process an INDI record into the persons table.

    Returns:
        (person_id, note_count, annotation_count)
    """
    gedcom_id = rec.xref

    # Parse NAME
    name_rec = rec.find("NAME")
    name_raw = name_rec.get_text().strip() if name_rec else ""
    given_name, surname, alt_names = _parse_name(name_raw)

    # Parse SEX
    sex_rec = rec.find("SEX")
    sex = sex_rec.value.strip() if sex_rec and sex_rec.value else None
    if sex and sex not in ("M", "F", "U"):
        sex = "U"

    # Parse BIRT
    birth_min, birth_max = None, None
    birt_rec = rec.find("BIRT")
    if birt_rec:
        date_rec = birt_rec.find("DATE")
        if date_rec and date_rec.value:
            birth_min, birth_max = _parse_date(date_rec.value)

    # Parse DEAT
    death_min, death_max = None, None
    deat_rec = rec.find("DEAT")
    if deat_rec:
        date_rec = deat_rec.find("DATE")
        if date_rec and date_rec.value:
            death_min, death_max = _parse_date(date_rec.value)

    # Insert person
    cur = conn.execute(
        "INSERT INTO persons "
        "(source_file_id, gedcom_id, given_name, surname, name_raw, sex, "
        " birth_year_min, birth_year_max, death_year_min, death_year_max) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_file_id,
            gedcom_id,
            given_name,
            surname,
            name_raw or "(unnamed)",
            sex,
            birth_min,
            birth_max,
            death_min,
            death_max,
        ),
    )
    person_id = cur.lastrowid

    # Insert alternate names
    for alt in alt_names:
        conn.execute(
            "INSERT INTO person_names "
            "(person_id, name_type, given_name, surname, name_raw, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                person_id,
                alt["type"],
                alt.get("given_name"),
                alt.get("surname"),
                alt["name_raw"],
                alt.get("source"),
            ),
        )

    # Process events (BIRT, DEAT, CHR, BURI) with places
    _process_events(conn, rec, person_id, None)

    # Process notes
    note_count, annotation_count = _process_notes(conn, rec, person_id, None)

    # Also process notes nested under BIRT/DEAT
    for event_tag in ("BIRT", "DEAT", "CHR", "BURI"):
        event_rec = rec.find(event_tag)
        if event_rec:
            n, a = _process_subnotes(conn, event_rec, person_id, None)
            note_count += n
            annotation_count += a

    return person_id, note_count, annotation_count


def _process_family(
    conn: sqlite3.Connection,
    rec: GedcomRecord,
    source_file_id: int,
    person_lookup: dict[str, int],
) -> tuple[int, int, int]:
    """Process a FAM record into the families table.

    Returns:
        (family_id, note_count, annotation_count)
    """
    gedcom_id = rec.xref

    # Look up HUSB and WIFE
    husb_rec = rec.find("HUSB")
    wife_rec = rec.find("WIFE")
    husband_id = person_lookup.get(husb_rec.value) if husb_rec and husb_rec.value else None
    wife_id = person_lookup.get(wife_rec.value) if wife_rec and wife_rec.value else None

    # Parse MARR
    marr_min, marr_max = None, None
    marr_place = None
    marr_rec = rec.find("MARR")
    if marr_rec:
        date_rec = marr_rec.find("DATE")
        if date_rec and date_rec.value:
            marr_min, marr_max = _parse_date(date_rec.value)
        place_rec = marr_rec.find("PLAC")
        if place_rec and place_rec.value:
            marr_place = place_rec.value.strip()

    # Determine marriage order for husband and wife
    marr_order_husb = None
    marr_order_wife = None
    if husband_id:
        cur = conn.execute("SELECT COUNT(*) FROM families WHERE husband_id = ?", (husband_id,))
        marr_order_husb = cur.fetchone()[0] + 1
    if wife_id:
        cur = conn.execute("SELECT COUNT(*) FROM families WHERE wife_id = ?", (wife_id,))
        marr_order_wife = cur.fetchone()[0] + 1

    cur = conn.execute(
        "INSERT INTO families "
        "(source_file_id, gedcom_id, husband_id, wife_id, "
        " marriage_year_min, marriage_year_max, marriage_place, "
        " marriage_order_husband, marriage_order_wife) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_file_id,
            gedcom_id,
            husband_id,
            wife_id,
            marr_min,
            marr_max,
            marr_place,
            marr_order_husb,
            marr_order_wife,
        ),
    )
    family_id = cur.lastrowid

    # Insert children
    child_order = 0
    for child_rec in rec.find_all("CHIL"):
        if child_rec.value:
            child_id = person_lookup.get(child_rec.value)
            if child_id:
                child_order += 1
                conn.execute(
                    "INSERT OR IGNORE INTO family_children (family_id, child_id, child_order) "
                    "VALUES (?, ?, ?)",
                    (family_id, child_id, child_order),
                )

    # Process notes
    note_count, annotation_count = _process_notes(conn, rec, None, family_id)

    return family_id, note_count, annotation_count


def _process_events(
    conn: sqlite3.Connection,
    rec: GedcomRecord,
    person_id: int | None,
    family_id: int | None,
) -> None:
    """Extract life events (BIRT, DEAT, CHR, BURI) and insert into events table."""
    for event_tag in ("BIRT", "DEAT", "CHR", "BURI"):
        event_rec = rec.find(event_tag)
        if not event_rec:
            continue

        date_raw = None
        year_min, year_max = None, None
        place = None

        date_rec = event_rec.find("DATE")
        if date_rec and date_rec.value:
            date_raw = date_rec.value
            year_min, year_max = _parse_date(date_raw)

        place_rec = event_rec.find("PLAC")
        if place_rec and place_rec.value:
            place = place_rec.value.strip()

        # Only insert if we have date or place data
        if date_raw or place:
            conn.execute(
                "INSERT INTO events (person_id, family_id, event_type, date_raw, "
                " year_min, year_max, place) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (person_id, family_id, event_tag, date_raw, year_min, year_max, place),
            )


def _process_notes(
    conn: sqlite3.Connection,
    rec: GedcomRecord,
    person_id: int | None,
    family_id: int | None,
) -> tuple[int, int]:
    """Extract NOTE records from a GEDCOM record and insert into notes/annotations.

    Returns:
        (note_count, annotation_count)
    """
    note_recs = rec.find_all("NOTE")
    if not note_recs:
        return 0, 0

    # Assemble note text lines
    note_lines = []
    for nr in note_recs:
        text = nr.get_text()
        if text:
            note_lines.append(text)

    if not note_lines:
        return 0, 0

    parsed_notes = parse_note_block(note_lines, gedcom_level=1)
    note_count = 0
    annotation_count = 0

    for pn in parsed_notes:
        if not pn.raw_text.strip():
            continue

        cur = conn.execute(
            "INSERT INTO notes (person_id, family_id, note_category, note_text, "
            " gedcom_level, line_number) VALUES (?, ?, ?, ?, ?, ?)",
            (
                person_id,
                family_id,
                pn.category,
                pn.raw_text,
                1,
                note_recs[0].line_number if note_recs else None,
            ),
        )
        note_id = cur.lastrowid
        note_count += 1

        # Insert source references
        for ref in pn.source_refs:
            conn.execute(
                "INSERT INTO source_references (note_id, person_id, list_number, "
                " veja_number, raw_text) VALUES (?, ?, ?, ?, ?)",
                (note_id, person_id, ref.list_number, ref.veja_number, ref.raw_text),
            )

        # Insert also names as person_names
        if person_id and pn.also_names:
            for also_name in pn.also_names:
                conn.execute(
                    "INSERT INTO person_names (person_id, name_type, name_raw, source) "
                    "VALUES (?, 'also', ?, ?)",
                    (person_id, also_name, f"Also: {also_name}"),
                )

        # Insert annotations
        for ann in pn.annotations:
            conn.execute(
                "INSERT INTO annotations (note_id, person_id, annotation_type, "
                " subtype, value, date_year_min, date_year_max, raw_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    person_id,
                    ann.annotation_type,
                    ann.subtype,
                    ann.value,
                    ann.date_year_min,
                    ann.date_year_max,
                    ann.raw_text,
                ),
            )
            annotation_count += 1

    return note_count, annotation_count


def _process_subnotes(
    conn: sqlite3.Connection,
    event_rec: GedcomRecord,
    person_id: int | None,
    family_id: int | None,
) -> tuple[int, int]:
    """Process NOTE records nested under an event (BIRT/DEAT etc.)."""
    note_recs = event_rec.find_all("NOTE")
    if not note_recs:
        return 0, 0

    note_lines = []
    for nr in note_recs:
        text = nr.get_text()
        if text:
            note_lines.append(text)

    if not note_lines:
        return 0, 0

    parsed_notes = parse_note_block(note_lines, gedcom_level=2)
    note_count = 0
    annotation_count = 0

    for pn in parsed_notes:
        if not pn.raw_text.strip():
            continue

        cur = conn.execute(
            "INSERT INTO notes (person_id, family_id, note_category, note_text, "
            " gedcom_level, line_number) VALUES (?, ?, ?, ?, ?, ?)",
            (
                person_id,
                family_id,
                pn.category,
                pn.raw_text,
                2,
                note_recs[0].line_number if note_recs else None,
            ),
        )
        note_id = cur.lastrowid
        note_count += 1

        for ref in pn.source_refs:
            conn.execute(
                "INSERT INTO source_references (note_id, person_id, list_number, "
                " veja_number, raw_text) VALUES (?, ?, ?, ?, ?)",
                (note_id, person_id, ref.list_number, ref.veja_number, ref.raw_text),
            )

        if person_id and pn.also_names:
            for also_name in pn.also_names:
                conn.execute(
                    "INSERT INTO person_names (person_id, name_type, name_raw, source) "
                    "VALUES (?, 'also', ?, ?)",
                    (person_id, also_name, f"Also: {also_name}"),
                )

        for ann in pn.annotations:
            conn.execute(
                "INSERT INTO annotations (note_id, person_id, annotation_type, "
                " subtype, value, date_year_min, date_year_max, raw_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    person_id,
                    ann.annotation_type,
                    ann.subtype,
                    ann.value,
                    ann.date_year_min,
                    ann.date_year_max,
                    ann.raw_text,
                ),
            )
            annotation_count += 1

    return note_count, annotation_count


# ---- Name parsing ----

_PAREN_NAME_RE = re.compile(r"\(([^)]+)\)")


def _parse_name(raw: str) -> tuple[str | None, str | None, list[dict]]:
    """Parse a GEDCOM NAME value into (given_name, surname, alternate_names).

    Examples:
        'Petrus Gondola '      -> ('Petrus', 'Gondola', [])
        'Damianus (Damiano) Sorgo ' -> ('Damianus', 'Sorgo', [{type: 'parenthetical', ...}])
        'Domagna de Babalio '  -> ('Domagna', 'Babalio', [])
        ' Babalio '            -> (None, 'Babalio', [])
        '  '                   -> (None, None, [])
        'frater Marinus '      -> ('frater Marinus', None, [])
    """
    alt_names: list[dict] = []

    if not raw or not raw.strip():
        return None, None, alt_names

    name = raw.strip()

    # Extract parenthetical alternate names: 'Damianus (Damiano) Sorgo'
    paren_match = _PAREN_NAME_RE.search(name)
    paren_given = None
    if paren_match:
        paren_given = paren_match.group(1).strip()
        name = name[: paren_match.start()] + name[paren_match.end() :]
        name = re.sub(r"\s+", " ", name).strip()

    # Split into words
    parts = name.split()

    if not parts:
        return None, None, alt_names

    if len(parts) == 1:
        # Single word — could be surname only or given only
        # If original had leading space, it's a surname
        if raw.startswith(" ") or raw.startswith("\t"):
            surname = parts[0]
            if paren_given:
                alt_names.append(
                    {
                        "type": "parenthetical",
                        "given_name": paren_given,
                        "surname": surname,
                        "name_raw": f"{paren_given} {surname}",
                    }
                )
            return None, surname, alt_names
        return parts[0], None, alt_names

    # Last word is surname, rest is given name
    # Strip 'de' / 'del' / 'di' from before surname
    surname_idx = len(parts) - 1
    given_parts = parts[:surname_idx]

    # Remove 'de', 'del', 'di' from end of given name (they're surname particles)
    while given_parts and given_parts[-1].lower() in ("de", "del", "di", "da"):
        given_parts.pop()

    surname = parts[-1]
    given_name = " ".join(given_parts) if given_parts else None

    if paren_given:
        alt_names.append(
            {
                "type": "parenthetical",
                "given_name": paren_given,
                "surname": surname,
                "name_raw": f"{paren_given} {surname}",
            }
        )

    return given_name, surname, alt_names


# ---- Date parsing ----

_DATE_RANGE_RE = re.compile(r"(\d{4})\s*-\s*(\d{2,4})")
_DATE_SINGLE_RE = re.compile(r"(\d{4})")
_DATE_GEDCOM_RE = re.compile(
    r"(?:(?:ABT|EST|CAL|BEF|AFT|FROM|TO|BET)\s+)?"
    r"(?:\d{1,2}\s+)?(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC\s+)?"
    r"(\d{4})",
    re.IGNORECASE,
)


def _parse_date(date_str: str) -> tuple[int | None, int | None]:
    """Parse a GEDCOM date string into (year_min, year_max).

    Handles:
        '1399'         -> (1399, 1399)
        '1189-1190'    -> (1189, 1190)
        '1482-83'      -> (1482, 1483)
        '9 Jul 2001'   -> (2001, 2001)
        ''             -> (None, None)
    """
    if not date_str or not date_str.strip():
        return None, None

    date_str = date_str.strip()

    # Try range first
    m = _DATE_RANGE_RE.search(date_str)
    if m:
        y1 = int(m.group(1))
        y2_str = m.group(2)
        if len(y2_str) == 2:
            y2 = (y1 // 100) * 100 + int(y2_str)
        elif len(y2_str) == 3:
            y2 = (y1 // 1000) * 1000 + int(y2_str)
        else:
            y2 = int(y2_str)
        return (min(y1, y2), max(y1, y2))

    # Try GEDCOM format with month names
    m = _DATE_GEDCOM_RE.search(date_str)
    if m:
        y = int(m.group(1))
        return (y, y)

    # Try bare year
    m = _DATE_SINGLE_RE.search(date_str)
    if m:
        y = int(m.group(1))
        return (y, y)

    return None, None

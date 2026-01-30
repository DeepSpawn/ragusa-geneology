"""Prosopographic profile builder for individual persons.

Builds comprehensive profiles combining genealogical data, annotations,
notes, and family connections.
"""

from __future__ import annotations

import sqlite3


def build_profile(conn: sqlite3.Connection, person_id: int) -> dict | None:
    """Build a comprehensive prosopographic profile for a person.

    Args:
        conn: Database connection.
        person_id: The person's database ID.

    Returns:
        Profile dict, or None if person not found.
    """
    row = conn.execute(
        "SELECT id, given_name, surname, name_raw, sex, "
        "birth_year_min, birth_year_max, death_year_min, death_year_max, "
        "source_file_id, gedcom_id, canonical_id, is_canonical "
        "FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()

    if not row:
        return None

    profile: dict = {
        "person": dict(row),
        "alternate_names": [],
        "family_of_origin": None,
        "marriages": [],
        "annotations": {},
        "source_references": [],
        "notes_verbatim": [],
        "offices": [],
        "documents": [],
    }

    # Alternate names
    profile["alternate_names"] = [
        dict(r)
        for r in conn.execute(
            "SELECT name_type, given_name, surname, name_raw, source "
            "FROM person_names WHERE person_id = ?",
            (person_id,),
        )
    ]

    # Family of origin (FAMC)
    origin = conn.execute(
        "SELECT f.id as family_id, "
        "ph.id as father_id, ph.given_name as father_given, ph.surname as father_surname, "
        "pw.id as mother_id, pw.given_name as mother_given, pw.surname as mother_surname "
        "FROM family_children fc "
        "JOIN families f ON fc.family_id = f.id "
        "LEFT JOIN persons ph ON f.husband_id = ph.id "
        "LEFT JOIN persons pw ON f.wife_id = pw.id "
        "WHERE fc.child_id = ?",
        (person_id,),
    ).fetchone()

    if origin:
        # Get siblings
        siblings = [
            dict(r)
            for r in conn.execute(
                "SELECT p.id, p.given_name, p.surname, p.sex, "
                "p.birth_year_min, p.death_year_min "
                "FROM family_children fc "
                "JOIN persons p ON fc.child_id = p.id "
                "WHERE fc.family_id = ? AND fc.child_id != ? "
                "ORDER BY p.birth_year_min",
                (origin["family_id"], person_id),
            )
        ]
        profile["family_of_origin"] = {
            "family_id": origin["family_id"],
            "father": {
                "id": origin["father_id"],
                "name": f"{origin['father_given'] or ''} {origin['father_surname'] or ''}".strip(),
            }
            if origin["father_id"]
            else None,
            "mother": {
                "id": origin["mother_id"],
                "name": f"{origin['mother_given'] or ''} {origin['mother_surname'] or ''}".strip(),
            }
            if origin["mother_id"]
            else None,
            "siblings": siblings,
        }

    # Marriages (FAMS) — as husband or wife
    marriages_raw = conn.execute(
        "SELECT f.id as family_id, f.marriage_year_min, f.marriage_year_max, "
        "f.marriage_place, f.marriage_order_husband, f.marriage_order_wife, "
        "f.husband_id, f.wife_id, "
        "ps.id as spouse_id, ps.given_name as spouse_given, "
        "ps.surname as spouse_surname, ps.sex as spouse_sex "
        "FROM families f "
        "LEFT JOIN persons ps ON "
        "(CASE WHEN f.husband_id = ? THEN f.wife_id ELSE f.husband_id END) = ps.id "
        "WHERE f.husband_id = ? OR f.wife_id = ? "
        "ORDER BY f.marriage_year_min",
        (person_id, person_id, person_id),
    ).fetchall()

    for m in marriages_raw:
        children = [
            dict(r)
            for r in conn.execute(
                "SELECT p.id, p.given_name, p.surname, p.sex, "
                "p.birth_year_min, p.death_year_min "
                "FROM family_children fc "
                "JOIN persons p ON fc.child_id = p.id "
                "WHERE fc.family_id = ? "
                "ORDER BY fc.child_order, p.birth_year_min",
                (m["family_id"],),
            )
        ]
        marriage_order = (
            m["marriage_order_husband"]
            if m["husband_id"] == person_id
            else m["marriage_order_wife"]
        )
        profile["marriages"].append(
            {
                "family_id": m["family_id"],
                "marriage_year": m["marriage_year_min"],
                "marriage_place": m["marriage_place"],
                "marriage_order": marriage_order,
                "spouse": {
                    "id": m["spouse_id"],
                    "name": f"{m['spouse_given'] or ''} {m['spouse_surname'] or ''}".strip(),
                }
                if m["spouse_id"]
                else None,
                "children": children,
            }
        )

    # Annotations (grouped by type)
    for row in conn.execute(
        "SELECT annotation_type, subtype, value, date_year_min, date_year_max, raw_text "
        "FROM annotations WHERE person_id = ? ORDER BY annotation_type, date_year_min",
        (person_id,),
    ):
        atype = row["annotation_type"]
        if atype not in profile["annotations"]:
            profile["annotations"][atype] = []
        profile["annotations"][atype].append(dict(row))

    # Source references
    profile["source_references"] = [
        dict(r)
        for r in conn.execute(
            "SELECT list_number, veja_number, raw_text FROM source_references WHERE person_id = ?",
            (person_id,),
        )
    ]

    # Verbatim notes
    profile["notes_verbatim"] = [
        dict(r)
        for r in conn.execute(
            "SELECT note_category, note_text FROM notes WHERE person_id = ? ORDER BY id",
            (person_id,),
        )
    ]

    # Offices (future data)
    profile["offices"] = [
        dict(r)
        for r in conn.execute(
            "SELECT office_title, institution, year_start, year_end "
            "FROM offices WHERE person_id = ? ORDER BY year_start",
            (person_id,),
        )
    ]

    return profile


def print_profile(conn: sqlite3.Connection, person_id: int) -> None:
    """Print a formatted prosopographic profile."""
    p = build_profile(conn, person_id)
    if not p:
        print(f"Person #{person_id} not found.")
        return

    person = p["person"]
    sex_label = {"M": "Male", "F": "Female", "U": "Unknown"}.get(person["sex"], "?")

    print("=" * 60)
    print(f"PROFILE: {person['name_raw']}")
    print("=" * 60)
    print(f"  ID:       #{person['id']} (GEDCOM: {person['gedcom_id']})")
    print(f"  Sex:      {sex_label}")

    if person["birth_year_min"]:
        birth = person["birth_year_min"]
        if person["birth_year_max"] != birth:
            birth = f"{birth}-{person['birth_year_max']}"
        print(f"  Born:     {birth}")

    if person["death_year_min"]:
        death = person["death_year_min"]
        if person["death_year_max"] != death:
            death = f"{death}-{person['death_year_max']}"
        print(f"  Died:     {death}")

    if p["alternate_names"]:
        print("\n  Also known as:")
        for alt in p["alternate_names"]:
            print(f"    - {alt['name_raw']} ({alt['name_type']})")

    if p["family_of_origin"]:
        fam = p["family_of_origin"]
        print("\n  Family of Origin:")
        if fam["father"]:
            print(f"    Father: {fam['father']['name']} (#{fam['father']['id']})")
        if fam["mother"]:
            print(f"    Mother: {fam['mother']['name']} (#{fam['mother']['id']})")
        if fam["siblings"]:
            print(f"    Siblings ({len(fam['siblings'])}):")
            for sib in fam["siblings"]:
                dates = ""
                if sib["birth_year_min"]:
                    dates = f" b.{sib['birth_year_min']}"
                if sib["death_year_min"]:
                    dates += f" d.{sib['death_year_min']}"
                name = f"{sib['given_name'] or '?'} {sib['surname'] or ''}"
                print(f"      - {name} ({sib['sex']}){dates}")

    if p["marriages"]:
        print(f"\n  Marriages ({len(p['marriages'])}):")
        for m in p["marriages"]:
            spouse_str = m["spouse"]["name"] if m["spouse"] else "(unknown)"
            year_str = f" ({m['marriage_year']})" if m["marriage_year"] else ""
            order_str = (
                f" [{_ordinal(m['marriage_order'])} marriage]"
                if m["marriage_order"] and m["marriage_order"] > 1
                else ""
            )
            print(f"    {spouse_str}{year_str}{order_str}")
            if m["children"]:
                for child in m["children"]:
                    dates = ""
                    if child["birth_year_min"]:
                        dates = f" b.{child['birth_year_min']}"
                    if child["death_year_min"]:
                        dates += f" d.{child['death_year_min']}"
                    name = f"{child['given_name'] or '?'} {child['surname'] or ''}"
                    print(f"      child: {name} ({child['sex']}){dates}")

    if p["annotations"]:
        print("\n  Annotations:")
        for atype, anns in p["annotations"].items():
            for ann in anns:
                date_str = ""
                if ann["date_year_min"]:
                    date_str = f" ({ann['date_year_min']})"
                subtype_str = f" [{ann['subtype']}]" if ann["subtype"] else ""
                print(f"    [{atype}]{subtype_str}: {ann['value']}{date_str}")

    if p["source_references"]:
        print("\n  Source References:")
        for ref in p["source_references"]:
            parts = []
            if ref["list_number"]:
                parts.append(f"list {ref['list_number']}")
            if ref["veja_number"]:
                parts.append(f"veja {ref['veja_number']}")
            print(f"    - {', '.join(parts)}")

    if p["offices"]:
        print("\n  Offices:")
        for off in p["offices"]:
            year_str = ""
            if off["year_start"]:
                year_str = f" ({off['year_start']}"
                if off["year_end"]:
                    year_str += f"-{off['year_end']}"
                year_str += ")"
            print(f"    - {off['office_title']}{year_str}")


def search_persons(
    conn: sqlite3.Connection,
    given_name: str | None = None,
    surname: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    sex: str | None = None,
    annotation_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search for persons matching criteria.

    All criteria are optional and combined with AND logic.
    """
    conditions = ["p.is_canonical = 1"]
    params: list = []

    if given_name:
        conditions.append("p.given_name LIKE ?")
        params.append(f"%{given_name}%")
    if surname:
        conditions.append("p.surname LIKE ?")
        params.append(f"%{surname}%")
    if sex:
        conditions.append("p.sex = ?")
        params.append(sex)
    if year_min:
        conditions.append("(p.birth_year_max >= ? OR p.death_year_max >= ?)")
        params.extend([year_min, year_min])
    if year_max:
        conditions.append("(p.birth_year_min <= ? OR p.death_year_min <= ?)")
        params.extend([year_max, year_max])

    where = " AND ".join(conditions)

    if annotation_type:
        sql = (
            f"SELECT DISTINCT p.id, p.given_name, p.surname, p.name_raw, p.sex, "
            f"p.birth_year_min, p.death_year_min "
            f"FROM persons p "
            f"JOIN annotations a ON a.person_id = p.id "
            f"WHERE {where} AND a.annotation_type = ? "
            f"ORDER BY p.surname, p.given_name LIMIT ?"
        )
        params.extend([annotation_type, limit])
    else:
        sql = (
            f"SELECT p.id, p.given_name, p.surname, p.name_raw, p.sex, "
            f"p.birth_year_min, p.death_year_min "
            f"FROM persons p "
            f"WHERE {where} "
            f"ORDER BY p.surname, p.given_name LIMIT ?"
        )
        params.append(limit)

    return [dict(r) for r in conn.execute(sql, params)]


def _ordinal(n: int | None) -> str:
    if n is None:
        return "?"
    if n == 1:
        return "1st"
    if n == 2:
        return "2nd"
    if n == 3:
        return "3rd"
    return f"{n}th"

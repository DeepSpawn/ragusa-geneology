"""Family network analysis: marriage alliances, kinship paths, and inter-family connections."""

from __future__ import annotations

import sqlite3
from collections import defaultdict


def get_marriage_alliances(
    conn: sqlite3.Connection,
    surname: str,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[dict]:
    """Find all families that married into the given surname.

    Returns a list of dicts: {partner_surname, count, marriages: [{year, husband, wife}]}
    sorted by count descending.
    """
    conditions = ["(ph.surname = ? OR pw.surname = ?)"]
    params: list = [surname, surname]

    if year_min:
        conditions.append("f.marriage_year_min >= ?")
        params.append(year_min)
    if year_max:
        conditions.append("f.marriage_year_max <= ?")
        params.append(year_max)

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT f.id, f.marriage_year_min, "
        f"ph.id as h_id, ph.given_name as h_given, ph.surname as h_surname, "
        f"pw.id as w_id, pw.given_name as w_given, pw.surname as w_surname "
        f"FROM families f "
        f"LEFT JOIN persons ph ON f.husband_id = ph.id "
        f"LEFT JOIN persons pw ON f.wife_id = pw.id "
        f"WHERE {where} "
        f"ORDER BY f.marriage_year_min",
        params,
    ).fetchall()

    alliances: dict[str, list] = defaultdict(list)
    target = surname.lower()

    for r in rows:
        h_surname = (r["h_surname"] or "").lower()
        w_surname = (r["w_surname"] or "").lower()

        if h_surname == target:
            partner = r["w_surname"] or "(unknown)"
        elif w_surname == target:
            partner = r["h_surname"] or "(unknown)"
        else:
            continue

        alliances[partner].append(
            {
                "family_id": r["id"],
                "year": r["marriage_year_min"],
                "husband": f"{r['h_given'] or ''} {r['h_surname'] or ''}".strip(),
                "wife": f"{r['w_given'] or ''} {r['w_surname'] or ''}".strip(),
            }
        )

    return sorted(
        [{"partner_surname": k, "count": len(v), "marriages": v} for k, v in alliances.items()],
        key=lambda x: -x["count"],
    )


def get_marriage_network(
    conn: sqlite3.Connection,
    year_min: int | None = None,
    year_max: int | None = None,
    min_marriages: int = 1,
) -> list[dict]:
    """Build the full inter-family marriage network.

    Returns a list of edges: {family_a, family_b, count, marriages}.
    Only includes edges with count >= min_marriages.
    """
    conditions = [
        "ph.surname IS NOT NULL",
        "pw.surname IS NOT NULL",
        "ph.surname != pw.surname",
    ]
    params: list = []

    if year_min:
        conditions.append("f.marriage_year_min >= ?")
        params.append(year_min)
    if year_max:
        conditions.append("f.marriage_year_max <= ?")
        params.append(year_max)

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT ph.surname as h_surname, pw.surname as w_surname, "
        f"f.marriage_year_min as year "
        f"FROM families f "
        f"JOIN persons ph ON f.husband_id = ph.id "
        f"JOIN persons pw ON f.wife_id = pw.id "
        f"WHERE {where} "
        f"ORDER BY f.marriage_year_min",
        params,
    ).fetchall()

    edges: dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = tuple(sorted([r["h_surname"], r["w_surname"]]))
        edges[key].append(r["year"])

    return sorted(
        [
            {
                "family_a": k[0],
                "family_b": k[1],
                "count": len(v),
                "years": v,
                "first_year": min(y for y in v if y) if any(v) else None,
                "last_year": max(y for y in v if y) if any(v) else None,
            }
            for k, v in edges.items()
            if len(v) >= min_marriages
        ],
        key=lambda x: -x["count"],
    )


def get_marriage_frequency_matrix(
    conn: sqlite3.Connection,
    top_n: int = 20,
    year_min: int | None = None,
    year_max: int | None = None,
) -> dict:
    """Build an NxN marriage frequency matrix for the top N families.

    Returns:
        {
            "families": ["Goce", "Mence", ...],
            "matrix": [[0, 5, 3, ...], [5, 0, 2, ...], ...],
        }
    """
    # Get top N families by size
    top_families = [
        row[0]
        for row in conn.execute(
            "SELECT surname, COUNT(*) as cnt FROM persons "
            "WHERE surname IS NOT NULL GROUP BY surname ORDER BY cnt DESC LIMIT ?",
            (top_n,),
        )
    ]

    family_idx = {name: i for i, name in enumerate(top_families)}
    n = len(top_families)
    matrix = [[0] * n for _ in range(n)]

    network = get_marriage_network(conn, year_min=year_min, year_max=year_max)
    for edge in network:
        a = family_idx.get(edge["family_a"])
        b = family_idx.get(edge["family_b"])
        if a is not None and b is not None:
            matrix[a][b] = edge["count"]
            matrix[b][a] = edge["count"]

    return {"families": top_families, "matrix": matrix}


def get_endogamy_rate(conn: sqlite3.Connection, surname: str) -> dict:
    """Calculate endogamy rate for a family.

    Returns:
        {
            "total_marriages": N,
            "endogamous": M (both spouses same surname),
            "exogamous": N - M,
            "endogamy_rate": M / N,
        }
    """
    total = conn.execute(
        "SELECT COUNT(*) FROM families f "
        "JOIN persons ph ON f.husband_id = ph.id "
        "JOIN persons pw ON f.wife_id = pw.id "
        "WHERE ph.surname = ? OR pw.surname = ?",
        (surname, surname),
    ).fetchone()[0]

    endogamous = conn.execute(
        "SELECT COUNT(*) FROM families f "
        "JOIN persons ph ON f.husband_id = ph.id "
        "JOIN persons pw ON f.wife_id = pw.id "
        "WHERE ph.surname = ? AND pw.surname = ?",
        (surname, surname),
    ).fetchone()[0]

    return {
        "surname": surname,
        "total_marriages": total,
        "endogamous": endogamous,
        "exogamous": total - endogamous,
        "endogamy_rate": endogamous / total if total > 0 else 0,
    }


def find_kinship_path(
    conn: sqlite3.Connection,
    person_a_id: int,
    person_b_id: int,
    max_depth: int = 10,
) -> list[dict] | None:
    """Find the shortest kinship path between two persons using BFS.

    Traverses parent-child and spouse relationships.

    Returns:
        List of steps [{person_id, name, relation_to_next}], or None if no path found.
    """
    if person_a_id == person_b_id:
        return [_person_summary(conn, person_a_id)]

    # BFS
    visited: set[int] = {person_a_id}
    queue: list[tuple[int, list[dict]]] = [(person_a_id, [_person_summary(conn, person_a_id)])]

    while queue:
        current_id, path = queue.pop(0)

        if len(path) > max_depth:
            continue

        # Get all connected persons
        neighbors = _get_neighbors(conn, current_id)
        for neighbor_id, relation in neighbors:
            if neighbor_id in visited:
                continue
            visited.add(neighbor_id)

            new_path = path.copy()
            new_path[-1]["relation_to_next"] = relation
            new_path.append(_person_summary(conn, neighbor_id))

            if neighbor_id == person_b_id:
                return new_path

            queue.append((neighbor_id, new_path))

    return None


def _get_neighbors(conn: sqlite3.Connection, person_id: int) -> list[tuple[int, str]]:
    """Get all persons directly connected to person_id via family relationships."""
    neighbors: list[tuple[int, str]] = []

    # Spouses
    for row in conn.execute(
        "SELECT CASE WHEN husband_id = ? THEN wife_id ELSE husband_id END as spouse_id "
        "FROM families WHERE husband_id = ? OR wife_id = ?",
        (person_id, person_id, person_id),
    ):
        if row["spouse_id"]:
            neighbors.append((row["spouse_id"], "spouse"))

    # Children (person is parent)
    for row in conn.execute(
        "SELECT fc.child_id FROM family_children fc "
        "JOIN families f ON fc.family_id = f.id "
        "WHERE f.husband_id = ? OR f.wife_id = ?",
        (person_id, person_id),
    ):
        neighbors.append((row["child_id"], "child"))

    # Parents (person is child)
    for row in conn.execute(
        "SELECT f.husband_id, f.wife_id FROM family_children fc "
        "JOIN families f ON fc.family_id = f.id "
        "WHERE fc.child_id = ?",
        (person_id,),
    ):
        if row["husband_id"]:
            neighbors.append((row["husband_id"], "parent"))
        if row["wife_id"]:
            neighbors.append((row["wife_id"], "parent"))

    return neighbors


def _person_summary(conn: sqlite3.Connection, person_id: int) -> dict:
    row = conn.execute(
        "SELECT id, given_name, surname, birth_year_min, death_year_min FROM persons WHERE id = ?",
        (person_id,),
    ).fetchone()
    if row:
        return {
            "person_id": row["id"],
            "name": f"{row['given_name'] or ''} {row['surname'] or ''}".strip(),
            "birth": row["birth_year_min"],
            "death": row["death_year_min"],
            "relation_to_next": None,
        }
    return {"person_id": person_id, "name": "?", "relation_to_next": None}

"""PA matching pipeline: generate, score, auto-match, and review candidates."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from .matching import generate_pa_candidates, score_pa_match


def run_pa_matching(
    conn: sqlite3.Connection,
    auto_threshold: float = 0.85,
    review_threshold: float = 0.50,
    verbose: bool = True,
) -> dict:
    """Run the full PA-to-GEDCOM matching pipeline.

    Args:
        conn: Database connection.
        auto_threshold: Score >= this with a unique match triggers auto-link.
        review_threshold: Score >= this is stored as a candidate.
        verbose: Print progress.

    Returns:
        Summary dict with counts.
    """
    if verbose:
        print("Generating PA match candidates...")
    candidates = generate_pa_candidates(conn)
    if verbose:
        print(f"  {len(candidates)} candidate pairs from surname blocking")

    if verbose:
        print("Scoring candidates...")

    # Group scored candidates by PA ID
    scored_by_pa: dict[int, list[dict]] = defaultdict(list)

    for candidate in candidates:
        pa = candidate["pa"]
        person = candidate["person"]
        scores = score_pa_match(conn, pa, person)

        if scores["score"] >= review_threshold:
            scored_by_pa[pa["id"]].append(
                {
                    "pa": pa,
                    "person": person,
                    **scores,
                }
            )

    results = {
        "total_candidates": len(candidates),
        "total_pa_entries": conn.execute(
            "SELECT COUNT(*) FROM politically_active_men WHERE match_status = 'unmatched'"
        ).fetchone()[0],
        "auto_matched": 0,
        "needs_review": 0,
        "no_candidates": 0,
    }

    # Count PA entries with no candidates above threshold
    all_unmatched_ids = {
        row[0]
        for row in conn.execute(
            "SELECT id FROM politically_active_men WHERE match_status = 'unmatched'"
        )
    }
    pa_ids_with_candidates = set(scored_by_pa.keys())
    results["no_candidates"] = len(all_unmatched_ids - pa_ids_with_candidates)

    # Process each PA entry
    for pa_id, scored_candidates in scored_by_pa.items():
        # Sort by score descending
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # Store all candidates in DB
        for sc in scored_candidates:
            conn.execute(
                "INSERT OR REPLACE INTO pa_match_candidates "
                "(pa_id, person_id, score, name_score, father_score, date_score, "
                "grandfather_score, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pa_id,
                    sc["person"]["id"],
                    sc["score"],
                    sc["name_score"],
                    sc["father_score"],
                    sc["date_score"],
                    sc["grandfather_score"],
                    "pending",
                ),
            )

        best = scored_candidates[0]
        second_best_score = scored_candidates[1]["score"] if len(scored_candidates) > 1 else 0.0

        # Auto-match: best score >= threshold AND no close competitor
        if best["score"] >= auto_threshold and second_best_score < 0.70:
            person_id = best["person"]["id"]
            conn.execute(
                "UPDATE politically_active_men SET person_id = ?, match_score = ?, "
                "match_status = 'auto_matched' WHERE id = ?",
                (person_id, best["score"], pa_id),
            )
            conn.execute(
                "UPDATE pa_match_candidates SET status = 'accepted' "
                "WHERE pa_id = ? AND person_id = ?",
                (pa_id, person_id),
            )
            results["auto_matched"] += 1
            if verbose and results["auto_matched"] <= 20:
                pa = best["pa"]
                print(
                    f"  AUTO: PA {pa_id} {pa['surname']} {pa['name']} "
                    f"-> #{person_id} {best['person']['given_name']} "
                    f"[{best['score']:.2f}]"
                )
        else:
            results["needs_review"] += 1

    conn.commit()

    if verbose:
        print(f"\nPA Matching Results:")
        print(f"  PA entries processed: {results['total_pa_entries']}")
        print(f"  Candidate pairs:     {results['total_candidates']}")
        print(f"  Auto-matched:        {results['auto_matched']}")
        print(f"  Needs review:        {results['needs_review']}")
        print(f"  No candidates:       {results['no_candidates']}")

    return results


def print_pa_review_queue(conn: sqlite3.Connection, limit: int = 50) -> None:
    """Print PA entries that need manual review with their top candidates."""
    # Get PA entries that are still unmatched and have candidates
    pa_rows = conn.execute(
        "SELECT pa.id, pa.surname, pa.name, pa.father, pa.grandfather, "
        "pa.entry_year, pa.end_year, pa.end_type "
        "FROM politically_active_men pa "
        "WHERE pa.match_status = 'unmatched' "
        "AND EXISTS (SELECT 1 FROM pa_match_candidates c WHERE c.pa_id = pa.id) "
        "ORDER BY pa.surname, pa.name "
        "LIMIT ?",
        (limit,),
    ).fetchall()

    if not pa_rows:
        print("No PA entries pending review.")
        return

    for pa in pa_rows:
        print(
            f"\nPA {pa['id']:>4} {pa['surname']} {pa['name']}"
            f"  father={pa['father'] or '?'}"
            f"  gf={pa['grandfather'] or '?'}"
            f"  entry={pa['entry_year'] or '?'}"
            f"  end={pa['end_year'] or '?'} {pa['end_type'] or ''}"
        )

        # Get top candidates
        candidates = conn.execute(
            "SELECT c.person_id, c.score, c.name_score, c.father_score, "
            "c.date_score, c.grandfather_score, "
            "p.given_name, p.surname, p.birth_year_min, p.death_year_min "
            "FROM pa_match_candidates c "
            "JOIN persons p ON c.person_id = p.id "
            "WHERE c.pa_id = ? AND c.status = 'pending' "
            "ORDER BY c.score DESC LIMIT 5",
            (pa["id"],),
        ).fetchall()

        for c in candidates:
            dates = ""
            if c["birth_year_min"]:
                dates += f"b.{c['birth_year_min']}"
            if c["death_year_min"]:
                dates += f" d.{c['death_year_min']}"
            print(
                f"  #{c['person_id']:>5} {c['given_name'] or '?':15s} "
                f"score={c['score']:.2f} "
                f"(name={c['name_score']:.1f} father={c['father_score']:.1f} "
                f"date={c['date_score']:.1f} gf={c['grandfather_score']:.1f}) "
                f"{dates}"
            )

    print(f"\n{len(pa_rows)} PA entries pending review")

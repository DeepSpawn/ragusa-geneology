"""Deduplication pipeline: generate, score, and optionally auto-merge candidates."""

from __future__ import annotations

import sqlite3

from .candidates import generate_candidates
from .merge import merge_persons
from .scoring import score_pair


def run_dedup(
    conn: sqlite3.Connection,
    auto_merge_threshold: float = 0.95,
    review_threshold: float = 0.6,
    auto_merge: bool = True,
    verbose: bool = True,
) -> dict:
    """Run the full deduplication pipeline.

    Args:
        conn: Database connection.
        auto_merge_threshold: Score >= this triggers automatic merge.
        review_threshold: Score >= this but < auto_merge is flagged for review.
        auto_merge: If True, automatically merge high-confidence pairs.
        verbose: Print progress.

    Returns:
        Summary dict with counts.
    """
    if verbose:
        print("Generating candidates...")
    candidates = generate_candidates(conn)
    if verbose:
        print(f"  {len(candidates)} candidate pairs from surname blocking")

    if verbose:
        print("Scoring candidates...")

    results = {
        "total_candidates": len(candidates),
        "auto_merged": 0,
        "needs_review": 0,
        "skipped": 0,
        "scored_pairs": [],
    }

    for i, candidate in enumerate(candidates):
        pa = candidate["person_a"]
        pb = candidate["person_b"]

        score = score_pair(conn, pa, pb)

        # Store in database
        conn.execute(
            "INSERT OR IGNORE INTO dedup_candidates "
            "(person_a_id, person_b_id, score, status) VALUES (?, ?, ?, ?)",
            (
                pa["id"],
                pb["id"],
                score,
                "auto_merged"
                if score >= auto_merge_threshold and auto_merge
                else "pending"
                if score >= review_threshold
                else "auto_skipped",
            ),
        )

        if score >= auto_merge_threshold and auto_merge:
            # Auto-merge: keep the person from the larger file (source_file_id=1 = Ragusan)
            keep_id = pa["id"] if pa["source_file_id"] == 1 else pb["id"]
            remove_id = pb["id"] if keep_id == pa["id"] else pa["id"]
            merge_persons(conn, keep_id, remove_id, reviewer_notes="auto-merge")
            results["auto_merged"] += 1
            if verbose and results["auto_merged"] <= 20:
                print(
                    f"  AUTO-MERGE: {pa['name_raw']} (#{pa['id']}) == "
                    f"{pb['name_raw']} (#{pb['id']}) [score={score:.2f}]"
                )
        elif score >= review_threshold:
            results["needs_review"] += 1
            results["scored_pairs"].append(
                {
                    "person_a": pa,
                    "person_b": pb,
                    "score": score,
                }
            )
        else:
            results["skipped"] += 1

    conn.commit()

    if verbose:
        print("\nDeduplication Results:")
        print(f"  Total candidates:  {results['total_candidates']}")
        print(f"  Auto-merged:       {results['auto_merged']}")
        print(f"  Needs review:      {results['needs_review']}")
        print(f"  Skipped (< {review_threshold}): {results['skipped']}")

        canonical = conn.execute("SELECT COUNT(*) FROM persons WHERE is_canonical = 1").fetchone()[
            0
        ]
        print(f"  Canonical persons: {canonical}")

    return results


def print_review_queue(conn: sqlite3.Connection, limit: int = 50) -> None:
    """Print candidates that need manual review."""
    rows = conn.execute(
        "SELECT dc.person_a_id, dc.person_b_id, dc.score, "
        "pa.name_raw as name_a, pa.birth_year_min as birth_a, pa.death_year_min as death_a, "
        "pb.name_raw as name_b, pb.birth_year_min as birth_b, pb.death_year_min as death_b "
        "FROM dedup_candidates dc "
        "JOIN persons pa ON dc.person_a_id = pa.id "
        "JOIN persons pb ON dc.person_b_id = pb.id "
        "WHERE dc.status = 'pending' "
        "ORDER BY dc.score DESC LIMIT ?",
        (limit,),
    ).fetchall()

    if not rows:
        print("No candidates pending review.")
        return

    print(f"{'Score':>5}  {'Person A':<30} {'Dates A':>12}  {'Person B':<30} {'Dates B':>12}")
    print("-" * 100)
    for r in rows:
        dates_a = f"b.{r['birth_a'] or '?'} d.{r['death_a'] or '?'}"
        dates_b = f"b.{r['birth_b'] or '?'} d.{r['death_b'] or '?'}"
        print(
            f"{r['score']:>5.2f}  {r['name_a']:<30} {dates_a:>12}  {r['name_b']:<30} {dates_b:>12}"
        )

    print(f"\n{len(rows)} candidates pending review")

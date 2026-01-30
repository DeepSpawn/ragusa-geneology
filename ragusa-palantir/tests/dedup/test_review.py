"""Tests for ragusa.dedup.review."""

from __future__ import annotations

from ragusa.dedup.review import run_dedup


def test_run_dedup_returns_summary(populated_db):
    result = run_dedup(populated_db, auto_merge=False, verbose=False)
    assert "total_candidates" in result
    assert "auto_merged" in result
    assert "needs_review" in result
    assert "skipped" in result
    assert "scored_pairs" in result


def test_run_dedup_no_auto_merge(populated_db):
    result = run_dedup(populated_db, auto_merge=False, verbose=False)
    assert result["auto_merged"] == 0


def test_run_dedup_stores_candidates_in_db(populated_db):
    run_dedup(populated_db, auto_merge=False, verbose=False)
    count = populated_db.execute("SELECT COUNT(*) FROM dedup_candidates").fetchone()[0]
    assert count > 0


def test_run_dedup_single_source_no_candidates(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'only.ged')")
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, given_name, surname, name_raw, sex)"
        " VALUES (1, '@I1@', 'Petrus', 'Gondola', 'Petrus Gondola', 'M')"
    )
    db_conn.commit()
    result = run_dedup(db_conn, verbose=False)
    assert result["total_candidates"] == 0

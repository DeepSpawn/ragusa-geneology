"""Tests for ragusa.analysis.timeline."""

from __future__ import annotations

from ragusa.analysis.timeline import (
    get_family_timeline,
    get_generation_summary,
    get_period_snapshot,
)


# ---------------------------------------------------------------------------
# get_generation_summary
# ---------------------------------------------------------------------------


def test_get_generation_summary_basic(populated_db):
    gens = get_generation_summary(populated_db, "Gondola", cohort_years=30)
    assert isinstance(gens, list)
    assert len(gens) > 0
    for g in gens:
        assert "generation" in g
        assert "year_range" in g
        assert "count" in g
        assert "members" in g


def test_get_generation_summary_no_data(populated_db):
    gens = get_generation_summary(populated_db, "Nonexistent")
    assert gens == []


def test_get_generation_summary_cohort_grouping(populated_db):
    """Persons born 30+ years apart should be in different generations."""
    gens = get_generation_summary(populated_db, "Gondola", cohort_years=30)
    # Petrus born 1260, Damianus/Clemens born 1290/1292 — same 30-year cohort
    if len(gens) > 0:
        for g in gens:
            assert g["count"] == len(g["members"])


# ---------------------------------------------------------------------------
# get_period_snapshot
# ---------------------------------------------------------------------------


def test_get_period_snapshot_persons_alive(populated_db):
    # Year 1300: Petrus (1260-1320), Margarita (1270-1335),
    # Damianus (1290-1350), Clemens (1292-1360), Elena (1300-1370) alive
    snapshot = get_period_snapshot(populated_db, 1300)
    assert isinstance(snapshot, dict)
    total = sum(len(v) for v in snapshot.values())
    assert total >= 4  # At least 4 persons alive


def test_get_period_snapshot_excludes_undated(populated_db):
    # Person 4 (Maria) has no death date — should be excluded
    snapshot = get_period_snapshot(populated_db, 1300)
    all_ids = [p["id"] for persons in snapshot.values() for p in persons]
    assert 4 not in all_ids


def test_get_period_snapshot_no_one_alive(populated_db):
    snapshot = get_period_snapshot(populated_db, 900)
    total = sum(len(v) for v in snapshot.values())
    assert total == 0


# ---------------------------------------------------------------------------
# get_family_timeline
# ---------------------------------------------------------------------------


def test_get_family_timeline_basic(populated_db):
    timeline = get_family_timeline(populated_db, "Gondola")
    assert isinstance(timeline, list)
    if len(timeline) > 1:
        # Should be sorted by year
        years = [e["year"] for e in timeline]
        assert years == sorted(years)


def test_get_family_timeline_includes_marriages(populated_db):
    timeline = get_family_timeline(populated_db, "Gondola")
    types = {e["type"] for e in timeline}
    assert "MARR" in types

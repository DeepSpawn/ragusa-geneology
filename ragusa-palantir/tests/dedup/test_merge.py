"""Tests for ragusa.dedup.merge."""

from __future__ import annotations

import pytest

from ragusa.dedup.merge import merge_persons


def test_merge_marks_removed_as_non_canonical(populated_db):
    merge_persons(populated_db, keep_id=1, remove_id=6)
    row = populated_db.execute(
        "SELECT is_canonical, canonical_id FROM persons WHERE id = 6"
    ).fetchone()
    assert row["is_canonical"] == 0
    assert row["canonical_id"] == 1


def test_merge_repoints_family_husband(populated_db):
    """Create a family with husband=6, then merge 6 into 1."""
    populated_db.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (10, 2, '@F10@', 6, NULL)"
    )
    populated_db.commit()
    merge_persons(populated_db, keep_id=1, remove_id=6)
    row = populated_db.execute(
        "SELECT husband_id FROM families WHERE id = 10"
    ).fetchone()
    assert row["husband_id"] == 1


def test_merge_repoints_family_wife(populated_db):
    """Create a family with wife=6, then merge 6 into 1."""
    populated_db.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (10, 2, '@F10@', NULL, 6)"
    )
    populated_db.commit()
    merge_persons(populated_db, keep_id=1, remove_id=6)
    row = populated_db.execute(
        "SELECT wife_id FROM families WHERE id = 10"
    ).fetchone()
    assert row["wife_id"] == 1


def test_merge_repoints_children(populated_db):
    """Create a family_children with child_id=6, then merge 6 into 1."""
    populated_db.execute(
        "INSERT INTO families"
        " (id, source_file_id, gedcom_id, husband_id, wife_id)"
        " VALUES (10, 2, '@F10@', NULL, NULL)"
    )
    populated_db.execute(
        "INSERT INTO family_children (family_id, child_id, child_order)"
        " VALUES (10, 6, 1)"
    )
    populated_db.commit()
    merge_persons(populated_db, keep_id=1, remove_id=6)
    row = populated_db.execute(
        "SELECT child_id FROM family_children WHERE family_id = 10"
    ).fetchone()
    assert row["child_id"] == 1


def test_merge_copies_missing_names(populated_db):
    """Person 6 gets a unique name; after merge it should appear on person 1."""
    populated_db.execute(
        "INSERT INTO person_names (person_id, name_type, given_name, surname, name_raw)"
        " VALUES (6, 'also', 'Petar', 'Gundulić', 'Petar Gundulić from source 2')"
    )
    populated_db.commit()
    merge_persons(populated_db, keep_id=1, remove_id=6)
    names = populated_db.execute(
        "SELECT name_raw FROM person_names WHERE person_id = 1"
    ).fetchall()
    raw_names = [r["name_raw"] for r in names]
    assert "Petar Gundulić from source 2" in raw_names


def test_merge_fills_missing_dates(populated_db):
    """Person 7 has no death date; person 3 does. Merge should fill gap."""
    # Person 7: Damiano, birth 1290, no death
    # Person 3: Damianus, birth 1290, death 1350
    merge_persons(populated_db, keep_id=3, remove_id=7)
    row = populated_db.execute(
        "SELECT death_year_min, death_year_max FROM persons WHERE id = 3"
    ).fetchone()
    # Person 3 already had death dates, so they stay
    assert row["death_year_min"] == 1350


def test_merge_fills_dates_from_removed(populated_db):
    """When keep record is missing dates that remove record has."""
    # Person 4 (Maria) has no death date; insert death on a duplicate
    populated_db.execute(
        "INSERT INTO persons"
        " (id, source_file_id, gedcom_id, given_name, surname, name_raw, sex,"
        "  birth_year_min, birth_year_max, death_year_min, death_year_max)"
        " VALUES (20, 2, '@I20@', 'Maria', 'Babalio', 'Maria Babalio', 'F',"
        "  1295, 1295, 1365, 1365)"
    )
    populated_db.commit()
    merge_persons(populated_db, keep_id=4, remove_id=20)
    row = populated_db.execute(
        "SELECT death_year_min, death_year_max FROM persons WHERE id = 4"
    ).fetchone()
    assert row["death_year_min"] == 1365
    assert row["death_year_max"] == 1365


def test_merge_logs_to_dedup_candidates(populated_db):
    merge_persons(populated_db, keep_id=1, remove_id=6)
    row = populated_db.execute(
        "SELECT status FROM dedup_candidates"
        " WHERE person_a_id = 1 AND person_b_id = 6"
    ).fetchone()
    assert row is not None
    assert row["status"] == "confirmed_match"

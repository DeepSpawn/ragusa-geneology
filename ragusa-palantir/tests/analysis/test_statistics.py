"""Tests for ragusa.analysis.statistics."""

from __future__ import annotations

from ragusa.analysis.statistics import _scalar, data_quality_report


def test_scalar_helper(db_conn):
    db_conn.execute("INSERT INTO source_files (id, filename) VALUES (1, 'test.ged')")
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, '@I1@', 'Test', 'M')"
    )
    db_conn.execute(
        "INSERT INTO persons (source_file_id, gedcom_id, name_raw, sex)"
        " VALUES (1, '@I2@', 'Test2', 'F')"
    )
    result = _scalar(db_conn, "SELECT COUNT(*) FROM persons")
    assert result == 2


def test_data_quality_report_empty_db(db_conn):
    report = data_quality_report(db_conn)
    assert report["count_persons"] == 0
    assert report["count_families"] == 0
    assert report["earliest_birth"] is None


def test_data_quality_report_with_data(populated_db):
    report = data_quality_report(populated_db)
    assert report["count_persons"] == 8
    assert report["count_families"] == 3
    assert report["count_events"] == 4
    assert report["earliest_birth"] == 1260
    assert report["persons_with_birth"] == 8


def test_data_quality_report_keys_present(populated_db):
    report = data_quality_report(populated_db)
    expected_keys = [
        "count_persons",
        "count_families",
        "count_family_children",
        "count_events",
        "count_notes",
        "count_source_references",
        "count_annotations",
        "count_person_names",
        "persons_with_birth",
        "persons_with_death",
        "persons_with_both_dates",
        "persons_with_surname",
        "earliest_birth",
        "latest_birth",
        "surname_distribution",
        "annotation_types",
        "source_files",
    ]
    for key in expected_keys:
        assert key in report, f"Missing key: {key}"

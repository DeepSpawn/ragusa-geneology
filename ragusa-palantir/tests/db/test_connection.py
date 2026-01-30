"""Tests for ragusa.db.connection."""

from __future__ import annotations

import sqlite3

from ragusa.db.connection import DEFAULT_DB_PATH, get_connection


def test_default_db_path():
    assert str(DEFAULT_DB_PATH).endswith("data/ragusa.db")


def test_get_connection_enables_wal_and_fk(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    try:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal == "wal"
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_get_connection_row_factory(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    try:
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()


def test_get_connection_creates_parent_directory(tmp_path):
    db_path = tmp_path / "sub" / "dir" / "test.db"
    conn = get_connection(db_path)
    try:
        assert db_path.parent.exists()
    finally:
        conn.close()

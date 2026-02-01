"""Database schema creation for the Ragusa research database."""

import sqlite3

SCHEMA_SQL = """
-- ============================================================
-- PROVENANCE
-- ============================================================
CREATE TABLE IF NOT EXISTS source_files (
    id              INTEGER PRIMARY KEY,
    filename        TEXT NOT NULL,
    gedcom_version  TEXT,
    encoding        TEXT,
    software        TEXT,
    date_created    TEXT,
    loaded_at       TEXT DEFAULT (datetime('now'))
);

-- ============================================================
-- CORE: Persons
-- ============================================================
CREATE TABLE IF NOT EXISTS persons (
    id              INTEGER PRIMARY KEY,
    source_file_id  INTEGER NOT NULL REFERENCES source_files(id),
    gedcom_id       TEXT NOT NULL,
    given_name      TEXT,
    surname         TEXT,
    name_raw        TEXT NOT NULL,
    sex             TEXT CHECK(sex IN ('M','F','U')),
    birth_year_min  INTEGER,
    birth_year_max  INTEGER,
    death_year_min  INTEGER,
    death_year_max  INTEGER,
    canonical_id    INTEGER REFERENCES persons(id),
    is_canonical    INTEGER DEFAULT 1,
    UNIQUE(source_file_id, gedcom_id)
);

CREATE INDEX IF NOT EXISTS idx_persons_surname ON persons(surname);
CREATE INDEX IF NOT EXISTS idx_persons_given_name ON persons(given_name);
CREATE INDEX IF NOT EXISTS idx_persons_canonical ON persons(canonical_id);
CREATE INDEX IF NOT EXISTS idx_persons_birth ON persons(birth_year_min, birth_year_max);
CREATE INDEX IF NOT EXISTS idx_persons_death ON persons(death_year_min, death_year_max);

-- ============================================================
-- CORE: Alternate Names
-- ============================================================
CREATE TABLE IF NOT EXISTS person_names (
    id          INTEGER PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES persons(id),
    name_type   TEXT NOT NULL,
    given_name  TEXT,
    surname     TEXT,
    name_raw    TEXT NOT NULL,
    source      TEXT
);

CREATE INDEX IF NOT EXISTS idx_person_names_person ON person_names(person_id);

-- ============================================================
-- CORE: Families
-- ============================================================
CREATE TABLE IF NOT EXISTS families (
    id                      INTEGER PRIMARY KEY,
    source_file_id          INTEGER NOT NULL REFERENCES source_files(id),
    gedcom_id               TEXT NOT NULL,
    husband_id              INTEGER REFERENCES persons(id),
    wife_id                 INTEGER REFERENCES persons(id),
    marriage_year_min       INTEGER,
    marriage_year_max       INTEGER,
    marriage_place          TEXT,
    marriage_order_husband  INTEGER,
    marriage_order_wife     INTEGER,
    UNIQUE(source_file_id, gedcom_id)
);

CREATE INDEX IF NOT EXISTS idx_families_husband ON families(husband_id);
CREATE INDEX IF NOT EXISTS idx_families_wife ON families(wife_id);
CREATE INDEX IF NOT EXISTS idx_families_marriage_year ON families(marriage_year_min);

-- ============================================================
-- CORE: Family-Child Relationships
-- ============================================================
CREATE TABLE IF NOT EXISTS family_children (
    id          INTEGER PRIMARY KEY,
    family_id   INTEGER NOT NULL REFERENCES families(id),
    child_id    INTEGER NOT NULL REFERENCES persons(id),
    child_order INTEGER,
    UNIQUE(family_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_family_children_family ON family_children(family_id);
CREATE INDEX IF NOT EXISTS idx_family_children_child ON family_children(child_id);

-- ============================================================
-- CORE: Events (extensible typed events)
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER REFERENCES persons(id),
    family_id       INTEGER REFERENCES families(id),
    event_type      TEXT NOT NULL,
    date_raw        TEXT,
    year_min        INTEGER,
    year_max        INTEGER,
    place           TEXT,
    description     TEXT,
    source_detail   TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_person ON events(person_id);
CREATE INDEX IF NOT EXISTS idx_events_family ON events(family_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_year ON events(year_min, year_max);

-- ============================================================
-- CORE: Notes (verbatim preservation)
-- ============================================================
CREATE TABLE IF NOT EXISTS notes (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER REFERENCES persons(id),
    family_id       INTEGER REFERENCES families(id),
    event_id        INTEGER REFERENCES events(id),
    note_category   TEXT,
    note_text       TEXT NOT NULL,
    gedcom_level    INTEGER,
    line_number     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_notes_person ON notes(person_id);
CREATE INDEX IF NOT EXISTS idx_notes_family ON notes(family_id);

-- ============================================================
-- PARSED: Archival Source References
-- ============================================================
CREATE TABLE IF NOT EXISTS source_references (
    id          INTEGER PRIMARY KEY,
    note_id     INTEGER REFERENCES notes(id),
    person_id   INTEGER REFERENCES persons(id),
    list_number INTEGER,
    veja_number INTEGER,
    raw_text    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_refs_person ON source_references(person_id);
CREATE INDEX IF NOT EXISTS idx_source_refs_list ON source_references(list_number);

-- ============================================================
-- PARSED: Structured Annotations
-- ============================================================
CREATE TABLE IF NOT EXISTS annotations (
    id              INTEGER PRIMARY KEY,
    note_id         INTEGER REFERENCES notes(id),
    person_id       INTEGER REFERENCES persons(id),
    annotation_type TEXT NOT NULL,
    subtype         TEXT,
    value           TEXT,
    date_year_min   INTEGER,
    date_year_max   INTEGER,
    raw_text        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_person ON annotations(person_id);
CREATE INDEX IF NOT EXISTS idx_annotations_type ON annotations(annotation_type);

-- ============================================================
-- EXTENSION: Offices and Roles
-- ============================================================
CREATE TABLE IF NOT EXISTS offices (
    id              INTEGER PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES persons(id),
    office_title    TEXT NOT NULL,
    institution     TEXT,
    year_start      INTEGER,
    year_end        INTEGER,
    source_detail   TEXT,
    annotation_id   INTEGER REFERENCES annotations(id)
);

CREATE INDEX IF NOT EXISTS idx_offices_person ON offices(person_id);
CREATE INDEX IF NOT EXISTS idx_offices_title ON offices(office_title);

-- ============================================================
-- EXTENSION: Documents
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    doc_type        TEXT NOT NULL,
    archive         TEXT,
    series          TEXT,
    volume          TEXT,
    folio           TEXT,
    date_raw        TEXT,
    year_min        INTEGER,
    year_max        INTEGER,
    summary         TEXT,
    transcription   TEXT
);

CREATE TABLE IF NOT EXISTS document_persons (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id),
    person_id       INTEGER NOT NULL REFERENCES persons(id),
    role            TEXT,
    detail          TEXT
);

CREATE INDEX IF NOT EXISTS idx_doc_persons_doc ON document_persons(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_persons_person ON document_persons(person_id);

-- ============================================================
-- DEDUPLICATION: Tracking merge decisions
-- ============================================================
CREATE TABLE IF NOT EXISTS dedup_candidates (
    id              INTEGER PRIMARY KEY,
    person_a_id     INTEGER NOT NULL REFERENCES persons(id),
    person_b_id     INTEGER NOT NULL REFERENCES persons(id),
    score           REAL,
    status          TEXT DEFAULT 'pending',
    reviewed_at     TEXT,
    reviewer_notes  TEXT,
    UNIQUE(person_a_id, person_b_id)
);

CREATE INDEX IF NOT EXISTS idx_dedup_status ON dedup_candidates(status);
CREATE INDEX IF NOT EXISTS idx_dedup_score ON dedup_candidates(score DESC);

-- ============================================================
-- EXTENSION: Politically Active Men (1440-1490)
-- ============================================================
CREATE TABLE IF NOT EXISTS politically_active_men (
    id                  INTEGER PRIMARY KEY,
    surname             TEXT NOT NULL,
    name                TEXT NOT NULL,
    father              TEXT,
    grandfather         TEXT,
    hackenberg_number   TEXT,
    entry_year          TEXT,
    entry_source        TEXT,
    end_year            TEXT,
    end_type            TEXT,
    notes               TEXT,
    person_id           INTEGER REFERENCES persons(id),
    match_score         REAL,
    match_status        TEXT DEFAULT 'unmatched'
);

CREATE INDEX IF NOT EXISTS idx_pa_surname ON politically_active_men(surname);
CREATE INDEX IF NOT EXISTS idx_pa_person ON politically_active_men(person_id);
CREATE INDEX IF NOT EXISTS idx_pa_status ON politically_active_men(match_status);

CREATE TABLE IF NOT EXISTS pa_match_candidates (
    id              INTEGER PRIMARY KEY,
    pa_id           INTEGER NOT NULL REFERENCES politically_active_men(id),
    person_id       INTEGER NOT NULL REFERENCES persons(id),
    score           REAL NOT NULL,
    name_score      REAL,
    father_score    REAL,
    date_score      REAL,
    grandfather_score REAL,
    status          TEXT DEFAULT 'pending',
    UNIQUE(pa_id, person_id)
);

CREATE INDEX IF NOT EXISTS idx_pa_candidates_pa ON pa_match_candidates(pa_id);
CREATE INDEX IF NOT EXISTS idx_pa_candidates_score ON pa_match_candidates(score DESC);
CREATE INDEX IF NOT EXISTS idx_pa_candidates_status ON pa_match_candidates(status);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all database tables and indexes."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()

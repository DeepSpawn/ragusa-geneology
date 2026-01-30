# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ragusa-Palantir is a Python CLI tool for genealogical and prosopographic research on the historical Republic of Ragusa (Dubrovnik). It parses GEDCOM files, loads data into a normalized SQLite database, and provides analysis tools for family networks, marriage alliances, deduplication, and historical timelines.

## Development Setup

```bash
cd ragusa-palantir
pip install -e ".[dev,analysis]"
```

This installs the `ragusa` CLI entry point. Python 3.11+ required.

## Commands

```bash
# Run tests
pytest tests/

# Load GEDCOM source data
ragusa load ../Ragusa/Ragusan.ged ../Ragusa/Gondola.Petrus.ged

# Reset database
ragusa reset

# Example analysis commands
ragusa stats
ragusa search --surname Gozze
ragusa profile <person_id>
ragusa alliances Gozze
ragusa network
ragusa dedup
ragusa dedup-review
```

## Architecture

The main code lives in `ragusa-palantir/ragusa/` with four modules:

### Parser (`ragusa/parser/`)
Multi-stage GEDCOM loading pipeline: raw line parsing (`gedcom_reader.py`) → hierarchical tree (`gedcom_tree.py`) → extraction and DB insertion (`gedcom_loader.py`). Handles two source files with different character encodings (CP852, non-standard ANSEL) via `encoding.py`. The `note_parser.py` extracts structured data from NOTE fields: archival source references (list/veja numbers), Latin/Croatian annotations (filiation, clerical titles, monastic orders), and alternate names.

### Database (`ragusa/db/`)
SQLite with WAL mode and foreign keys. Schema (`schema.py`) has 17 normalized tables with 30+ indexes. Core tables: `persons`, `families`, `family_children`, `events`, `notes`. Each person tracks its `source_file` origin and `canonical_id` for deduplication. Connection defaults to `data/ragusa.db`.

### Analysis (`ragusa/analysis/`)
- `statistics.py` — Data quality reports: coverage percentages, surname distributions, annotation types
- `family_network.py` — Marriage alliances, inter-family network graphs, endogamy rates, kinship path finding (BFS)
- `prosopography.py` — Person profiles combining genealogical data, annotations, source references; search with filters
- `timeline.py` — Family timelines, generational cohorts, period snapshots (who was alive in year X)

### Deduplication (`ragusa/dedup/`)
Pipeline to find and merge duplicate persons across the two source GEDCOM files:
1. `candidates.py` — Surname blocking with variant mapping (Dersie→Derse, Bodaca→Bodacia, etc.)
2. `scoring.py` — Weighted similarity: name (30%), date overlap (25%), spouse match (25%), filiation (15%), children (5%)
3. `merge.py` — Soft merge preserving both records for audit; kept record absorbs all relationships
4. `review.py` — Auto-merges ≥0.95 score, flags 0.60–0.95 for manual review

### CLI (`ragusa/cli.py`)
Argparse-based command router with 15 subcommands dispatching to the modules above.

## Domain Context

- Source data: two GEDCOM files in `Ragusa/` — `Ragusan.ged` (larger, CP852) and `Gondola.Petrus.ged` (smaller, ANSEL variant)
- Croatian diacritics (č, ć, š, ž, đ) require careful encoding handling
- Note fields contain abbreviated Latin and Croatian genealogical terms (hči = daughter, etc.)
- Deduplication compares only cross-file pairs (same person recorded in both sources)

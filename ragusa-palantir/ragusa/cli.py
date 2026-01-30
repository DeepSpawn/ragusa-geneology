"""Command-line interface for the Ragusa Historical Research Database."""

from __future__ import annotations

import argparse
import os

from .db.connection import DEFAULT_DB_PATH, get_connection
from .db.schema import create_schema


def main():
    parser = argparse.ArgumentParser(
        description="Ragusa Historical Research Database",
        prog="ragusa",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Database path")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # load
    load_parser = subparsers.add_parser("load", help="Load GEDCOM files into the database")
    load_parser.add_argument("files", nargs="*", help="GEDCOM files to load")
    load_parser.add_argument("--reset", action="store_true", help="Drop and recreate database")

    # stats
    subparsers.add_parser("stats", help="Show data quality statistics")

    # profile
    profile_parser = subparsers.add_parser("profile", help="Show prosopographic profile")
    profile_parser.add_argument("person_id", type=int, help="Person ID")

    # search
    search_parser = subparsers.add_parser("search", help="Search for persons")
    search_parser.add_argument("--name", help="Given name (partial match)")
    search_parser.add_argument("--surname", help="Surname (partial match)")
    search_parser.add_argument("--sex", choices=["M", "F", "U"], help="Sex")
    search_parser.add_argument("--year-min", type=int, help="Active after this year")
    search_parser.add_argument("--year-max", type=int, help="Active before this year")
    search_parser.add_argument("--annotation", help="Has annotation of this type")
    search_parser.add_argument("--limit", type=int, default=50, help="Max results")

    # alliances
    alliances_parser = subparsers.add_parser(
        "alliances", help="Show marriage alliances for a family"
    )
    alliances_parser.add_argument("surname", help="Family surname")
    alliances_parser.add_argument("--year-min", type=int)
    alliances_parser.add_argument("--year-max", type=int)

    # network
    network_parser = subparsers.add_parser("network", help="Show marriage network")
    network_parser.add_argument("--year-min", type=int)
    network_parser.add_argument("--year-max", type=int)
    network_parser.add_argument(
        "--min-marriages", type=int, default=2, help="Minimum marriages to show"
    )
    network_parser.add_argument("--top", type=int, default=20, help="Top N families for matrix")

    # timeline
    timeline_parser = subparsers.add_parser("timeline", help="Show family timeline")
    timeline_parser.add_argument("surname", help="Family surname")

    # generations
    gen_parser = subparsers.add_parser("generations", help="Show generational breakdown")
    gen_parser.add_argument("surname", help="Family surname")
    gen_parser.add_argument("--cohort", type=int, default=30, help="Years per generation")

    # snapshot
    snap_parser = subparsers.add_parser("snapshot", help="Who was alive in a given year?")
    snap_parser.add_argument("year", type=int, help="Year")

    # kinship
    kinship_parser = subparsers.add_parser("kinship", help="Find kinship path between two persons")
    kinship_parser.add_argument("person_a", type=int, help="Person A ID")
    kinship_parser.add_argument("person_b", type=int, help="Person B ID")
    kinship_parser.add_argument("--max-depth", type=int, default=10)

    # endogamy
    endo_parser = subparsers.add_parser("endogamy", help="Calculate endogamy rate for a family")
    endo_parser.add_argument("surname", help="Family surname")

    # dedup
    dedup_parser = subparsers.add_parser("dedup", help="Run deduplication pipeline")
    dedup_parser.add_argument("--auto-merge-threshold", type=float, default=0.95)
    dedup_parser.add_argument("--review-threshold", type=float, default=0.6)
    dedup_parser.add_argument("--no-auto-merge", action="store_true")

    # dedup-review
    review_parser = subparsers.add_parser("dedup-review", help="Show dedup review queue")
    review_parser.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    conn = get_connection(args.db)

    try:
        if args.command == "load":
            _cmd_load(conn, args)
        elif args.command == "stats":
            _cmd_stats(conn)
        elif args.command == "profile":
            _cmd_profile(conn, args)
        elif args.command == "search":
            _cmd_search(conn, args)
        elif args.command == "alliances":
            _cmd_alliances(conn, args)
        elif args.command == "network":
            _cmd_network(conn, args)
        elif args.command == "timeline":
            _cmd_timeline(conn, args)
        elif args.command == "generations":
            _cmd_generations(conn, args)
        elif args.command == "snapshot":
            _cmd_snapshot(conn, args)
        elif args.command == "kinship":
            _cmd_kinship(conn, args)
        elif args.command == "endogamy":
            _cmd_endogamy(conn, args)
        elif args.command == "dedup":
            _cmd_dedup(conn, args)
        elif args.command == "dedup-review":
            _cmd_dedup_review(conn, args)
    finally:
        conn.close()


def _cmd_load(conn, args):
    from .parser.gedcom_loader import load_gedcom_file

    if args.reset:
        conn.close()
        if os.path.exists(args.db):
            os.remove(args.db)
            print(f"Removed existing database: {args.db}")
        conn = get_connection(args.db)

    create_schema(conn)

    files = args.files
    if not files:
        ragusa_dir = os.path.join(os.path.dirname(__file__), "..", "..", "Ragusa")
        files = [
            os.path.join(ragusa_dir, "Ragusan.ged"),
            os.path.join(ragusa_dir, "Gondola.Petrus.ged"),
        ]

    for filepath in files:
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            print(f"ERROR: File not found: {filepath}")
            continue
        print(f"Loading {os.path.basename(filepath)}...")
        result = load_gedcom_file(conn, filepath)
        print(
            f"  Individuals: {result['individuals']}, Families: {result['families']}, "
            f"Notes: {result['notes']}, Annotations: {result['annotations']}"
        )

    conn.close()


def _cmd_stats(conn):
    from .analysis.statistics import print_report

    print_report(conn)


def _cmd_profile(conn, args):
    from .analysis.prosopography import print_profile

    print_profile(conn, args.person_id)


def _cmd_search(conn, args):
    from .analysis.prosopography import search_persons

    results = search_persons(
        conn,
        given_name=args.name,
        surname=args.surname,
        year_min=args.year_min,
        year_max=args.year_max,
        sex=args.sex,
        annotation_type=args.annotation,
        limit=args.limit,
    )

    if not results:
        print("No results found.")
        return

    print(f"{'ID':>6}  {'Name':<30}  {'Sex':>3}  {'Born':>6}  {'Died':>6}")
    print("-" * 60)
    for r in results:
        name = f"{r['given_name'] or ''} {r['surname'] or ''}".strip()
        birth = str(r["birth_year_min"]) if r["birth_year_min"] else ""
        death = str(r["death_year_min"]) if r["death_year_min"] else ""
        print(f"{r['id']:>6}  {name:<30}  {r['sex'] or '?':>3}  {birth:>6}  {death:>6}")

    print(f"\n{len(results)} result(s)")


def _cmd_alliances(conn, args):
    from .analysis.family_network import get_marriage_alliances

    alliances = get_marriage_alliances(
        conn,
        args.surname,
        year_min=args.year_min,
        year_max=args.year_max,
    )

    if not alliances:
        print(f"No marriage alliances found for {args.surname}.")
        return

    print(f"Marriage Alliances of the {args.surname} Family")
    print("=" * 60)

    total = sum(a["count"] for a in alliances)
    for a in alliances:
        pct = 100 * a["count"] / total
        bar = "#" * (a["count"])
        years = [str(m["year"]) for m in a["marriages"] if m["year"]]
        year_str = f" ({', '.join(years[:5])}{'...' if len(years) > 5 else ''})" if years else ""
        print(f"  {a['partner_surname']:20s}: {a['count']:>3} ({pct:4.1f}%)  {bar}{year_str}")

    print(f"\nTotal: {total} marriages with {len(alliances)} different families")


def _cmd_network(conn, args):
    from .analysis.family_network import get_marriage_frequency_matrix, get_marriage_network

    network = get_marriage_network(
        conn,
        year_min=args.year_min,
        year_max=args.year_max,
        min_marriages=args.min_marriages,
    )

    print("Inter-Family Marriage Network")
    print("=" * 60)
    for edge in network[:40]:
        years_str = ""
        valid_years = [y for y in edge["years"] if y]
        if valid_years:
            years_str = f" ({min(valid_years)}-{max(valid_years)})"
        fa = edge["family_a"]
        fb = edge["family_b"]
        cnt = edge["count"]
        print(f"  {fa:15s} <-> {fb:15s}: {cnt:>3} marriages{years_str}")

    print(f"\n{len(network)} connections with >= {args.min_marriages} marriages")

    # Matrix view
    print(f"\n{'=' * 60}")
    print(f"Marriage Frequency Matrix (Top {args.top} families)")
    print(f"{'=' * 60}")
    mdata = get_marriage_frequency_matrix(
        conn, top_n=args.top, year_min=args.year_min, year_max=args.year_max
    )
    families = mdata["families"]
    matrix = mdata["matrix"]

    # Print header (abbreviated names)
    abbrevs = [f[:3] for f in families]
    header = "        " + " ".join(f"{a:>4}" for a in abbrevs)
    print(header)
    for i, fam in enumerate(families):
        row_str = " ".join(
            f"{matrix[i][j]:>4}" if matrix[i][j] > 0 else "   ." for j in range(len(families))
        )
        print(f"  {fam[:6]:>6} {row_str}")


def _cmd_timeline(conn, args):
    from .analysis.timeline import get_family_timeline

    events = get_family_timeline(conn, args.surname)
    if not events:
        print(f"No events found for {args.surname}.")
        return

    print(f"Timeline of the {args.surname} Family")
    print("=" * 60)
    for e in events:
        print(f"  {e['year']:>4}  {e['type']:<8}  {e['person']:<25}  {e['detail'] or ''}")


def _cmd_generations(conn, args):
    from .analysis.timeline import get_generation_summary

    gens = get_generation_summary(conn, args.surname, cohort_years=args.cohort)
    if not gens:
        print(f"No generational data for {args.surname}.")
        return

    print(f"Generations of the {args.surname} Family ({args.cohort}-year cohorts)")
    print("=" * 60)
    for g in gens:
        print(f"\n  Generation {g['generation']} ({g['year_range']}) — {g['count']} members")
        for m in g["members"]:
            dates = ""
            if m["birth_year_min"]:
                dates = f" b.{m['birth_year_min']}"
            if m["death_year_min"]:
                dates += f" d.{m['death_year_min']}"
            print(f"    {m['given_name'] or '?':15s} ({m['sex']}){dates}")


def _cmd_snapshot(conn, args):
    from .analysis.timeline import get_period_snapshot

    snapshot = get_period_snapshot(conn, args.year)
    if not snapshot:
        print(f"No persons found alive in {args.year}.")
        return

    total = sum(len(v) for v in snapshot.values())
    print(f"Persons alive in {args.year}: {total} across {len(snapshot)} families")
    print("=" * 60)
    for surname, members in snapshot.items():
        names = ", ".join(m["given_name"] or "?" for m in members)
        print(f"  {surname:20s} ({len(members):>2}): {names}")


def _cmd_kinship(conn, args):
    from .analysis.family_network import find_kinship_path

    path = find_kinship_path(conn, args.person_a, args.person_b, max_depth=args.max_depth)
    if not path:
        print(
            f"No kinship path found between #{args.person_a} and #{args.person_b} "
            f"within {args.max_depth} steps."
        )
        return

    print(f"Kinship path ({len(path) - 1} steps):")
    for i, step in enumerate(path):
        dates = ""
        if step.get("birth"):
            dates = f" b.{step['birth']}"
        if step.get("death"):
            dates += f" d.{step['death']}"
        rel = f" --[{step['relation_to_next']}]--> " if step.get("relation_to_next") else ""
        print(f"  #{step['person_id']:>5} {step['name']}{dates}{rel}")


def _cmd_endogamy(conn, args):
    from .analysis.family_network import get_endogamy_rate

    result = get_endogamy_rate(conn, args.surname)
    print(f"Endogamy Analysis: {args.surname}")
    print(f"  Total marriages:    {result['total_marriages']}")
    print(f"  Endogamous:         {result['endogamous']} (both spouses {args.surname})")
    print(f"  Exogamous:          {result['exogamous']}")
    print(f"  Endogamy rate:      {result['endogamy_rate']:.1%}")


def _cmd_dedup(conn, args):
    from .dedup.review import run_dedup

    run_dedup(
        conn,
        auto_merge_threshold=args.auto_merge_threshold,
        review_threshold=args.review_threshold,
        auto_merge=not args.no_auto_merge,
        verbose=True,
    )


def _cmd_dedup_review(conn, args):
    from .dedup.review import print_review_queue

    print_review_queue(conn, limit=args.limit)


if __name__ == "__main__":
    main()

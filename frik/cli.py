"""
frik CLI — Fair Remuneration Intelligence Kit

Commands:
  frik wages        -- BLS OEWS wages by SOC code
  frik soc          -- list built-in SOC code definitions
  frik h1b download -- download + cache DOL LCA disclosure data
  frik h1b search   -- search cached H1B records by title / employer / state
  frik h1b summary  -- wage statistics (p25/median/p75/p90) for a query
"""

from __future__ import annotations

import argparse
import json
import sys

from frik.sources.bls import DEFAULT_OCCUPATIONS, fetch_wages


def _fmt_dollars(val: float | None) -> str:
    if val is None:
        return "N/A"
    if val < 1000:
        return f"{val:,.1f}k"
    return f"${int(val):,}"


def cmd_wages(args: argparse.Namespace) -> None:
    soc_codes = args.soc or None
    results = fetch_wages(soc_codes=soc_codes)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    col = 44
    print(f"\n{'Occupation':<{col}} {'Mean':>12} {'Median':>12} {'P75':>12} {'P90':>12}")
    print("-" * (col + 52))
    for r in results:
        w = r["wages"]
        print(
            f"{r['title']:<{col}}"
            f" {_fmt_dollars(w.get('annual_mean')):>12}"
            f" {_fmt_dollars(w.get('annual_median')):>12}"
            f" {_fmt_dollars(w.get('annual_p75')):>12}"
            f" {_fmt_dollars(w.get('annual_p90')):>12}"
        )
    print(
        "\nSource: BLS OEWS (latest annual release) — national, all industries."
        "\nDoes not include equity, bonus, or geographic cost-of-living adjustment."
    )

    if args.out:
        import pathlib
        pathlib.Path(args.out).write_text(json.dumps(results, indent=2))
        print(f"\nJSON written to {args.out}", file=sys.stderr)


def cmd_list_soc(_args: argparse.Namespace) -> None:
    print(f"\n{'SOC':<12} {'Category':<14} Title")
    print("-" * 70)
    for o in DEFAULT_OCCUPATIONS:
        print(f"{o['soc']:<12} {o['category']:<14} {o['title']}")
        if o["notes"]:
            print(f"{'':12} {'':14} {o['notes']}")
        print()


def cmd_h1b_download(args: argparse.Namespace) -> None:
    from frik.sources.h1b import download
    try:
        db = download(fy=args.fy, quarter=args.quarter, force=args.force)
        print(f"Cache ready: {db}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_h1b_search(args: argparse.Namespace) -> None:
    from frik.sources.h1b import search
    try:
        rows = search(
            title=args.title,
            soc_code=args.soc,
            state=args.state,
            employer=args.employer,
            limit=args.limit,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("No results found.")
        return

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    print(f"\n{'Employer':<35} {'Title':<35} {'State':<5} {'From':>12} {'To':>12} {'Level':<6}")
    print("-" * 110)
    for r in rows:
        print(
            f"{(r['employer'] or '')[:34]:<35}"
            f" {(r['job_title'] or '')[:34]:<35}"
            f" {(r['worksite_state'] or ''):<5}"
            f" {_fmt_dollars(r.get('annual_from')):>12}"
            f" {_fmt_dollars(r.get('annual_to')):>12}"
            f" {(r.get('pw_level') or ''):<6}"
        )
    print(f"\n{len(rows)} result(s)")


def cmd_h1b_summary(args: argparse.Namespace) -> None:
    from frik.sources.h1b import summarize
    try:
        stats = summarize(
            title=args.title,
            soc_code=args.soc,
            state=args.state,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if stats.get("n", 0) == 0:
        print("No matching records found.")
        return

    if args.json:
        print(json.dumps(stats, indent=2))
        return

    label = args.title or args.soc or "all"
    state_note = f" ({args.state})" if args.state else " (national)"
    print(f"\nH1B wage summary — {label}{state_note}")
    print(f"  n (filings):  {stats['n']:,}")
    print(f"  P25:          {_fmt_dollars(stats['p25'])}")
    print(f"  Median:       {_fmt_dollars(stats['median'])}")
    print(f"  Mean:         {_fmt_dollars(stats['mean'])}")
    print(f"  P75:          {_fmt_dollars(stats['p75'])}")
    print(f"  P90:          {_fmt_dollars(stats['p90'])}")
    print(f"  Range:        {_fmt_dollars(stats['min'])} – {_fmt_dollars(stats['max'])}")
    print("\nSource: DOL LCA Disclosure Data (H-1B certified filings, offered wage floor)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="frik",
        description="Fair Remuneration Intelligence Kit — compensation data from BLS, H1B filings, and job postings.",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    # frik wages
    p_wages = sub.add_parser("wages", help="BLS OEWS wages by SOC code")
    p_wages.add_argument(
        "--soc", nargs="+", metavar="SOC",
        help="SOC codes to look up (e.g. 15-1252 15-1299). Defaults to all built-in occupations.",
    )
    p_wages.add_argument("--json", action="store_true", help="Output raw JSON")
    p_wages.add_argument("--out", metavar="FILE", help="Write JSON output to file")
    p_wages.set_defaults(func=cmd_wages)

    # frik soc
    p_soc = sub.add_parser("soc", help="List built-in SOC code definitions")
    p_soc.set_defaults(func=cmd_list_soc)

    # frik h1b
    p_h1b = sub.add_parser("h1b", help="DOL H1B/LCA disclosure data")
    h1b_sub = p_h1b.add_subparsers(dest="h1b_command", metavar="subcommand")

    p_dl = h1b_sub.add_parser("download", help="Download + cache LCA data as SQLite")
    p_dl.add_argument("--fy", type=int, default=2025, metavar="YEAR",
                      help="Fiscal year to download (default: 2025)")
    p_dl.add_argument("--quarter", type=int, default=4, metavar="Q",
                      help="Quarter to download (default: 4)")
    p_dl.add_argument("--force", action="store_true",
                      help="Re-download even if cache exists")
    p_dl.set_defaults(func=cmd_h1b_download)

    p_srch = h1b_sub.add_parser("search", help="Search H1B records")
    p_srch.add_argument("--title", metavar="TITLE", help="Job title (full-text search)")
    p_srch.add_argument("--soc", metavar="SOC", help="SOC code (e.g. 15-1252)")
    p_srch.add_argument("--state", metavar="ST", help="Two-letter state code (e.g. CA)")
    p_srch.add_argument("--employer", metavar="NAME", help="Employer name substring")
    p_srch.add_argument("--limit", type=int, default=50)
    p_srch.add_argument("--json", action="store_true", help="Output raw JSON")
    p_srch.set_defaults(func=cmd_h1b_search)

    p_sum = h1b_sub.add_parser("summary", help="Wage statistics for a title/SOC query")
    p_sum.add_argument("--title", metavar="TITLE", help="Job title (full-text search)")
    p_sum.add_argument("--soc", metavar="SOC", help="SOC code (e.g. 15-1252)")
    p_sum.add_argument("--state", metavar="ST", help="Two-letter state code (e.g. CA)")
    p_sum.add_argument("--json", action="store_true")
    p_sum.set_defaults(func=cmd_h1b_summary)

    def _h1b_help(_args: argparse.Namespace) -> None:
        p_h1b.print_help()

    p_h1b.set_defaults(func=_h1b_help)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

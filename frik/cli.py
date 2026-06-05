"""
frik CLI — Fair Remuneration Intelligence Kit

Commands:
  frik wages   -- BLS OEWS wages by SOC code or occupation name
  frik compare -- side-by-side comparison of multiple SOC codes
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

    # frik soc  (list available SOC codes)
    p_soc = sub.add_parser("soc", help="List built-in SOC code definitions")
    p_soc.set_defaults(func=cmd_list_soc)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

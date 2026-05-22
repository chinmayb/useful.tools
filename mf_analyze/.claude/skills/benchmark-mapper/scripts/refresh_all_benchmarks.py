"""Refresh all TRI benchmarks needed by the current portfolio.

Reads the most recent holdings snapshot under data/holdings/<YYYY-MM-DD>/holdings.csv,
maps each (in-scope) fund to its benchmark via references/category_to_benchmark.md,
deduplicates, and fetches each TRI series via fetch_tri.py.

Out-of-v1-scope categories are skipped (debt, hybrid, FoF Overseas, commodity FoF).

Usage:
    python refresh_all_benchmarks.py                 # latest snapshot, default start (2013-01-01)
    python refresh_all_benchmarks.py --start 2018-01-01
    python refresh_all_benchmarks.py --force         # bypass per-index cache
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# Allow `python scripts/refresh_all_benchmarks.py` from the repo root.
sys.path.insert(0, str(Path(__file__).parent))
from fetch_tri import fetch_tri  # noqa: E402

HOLDINGS_ROOT = Path("data/holdings")

# Equity-only v1 categories. Anything else is skipped with a notice.
EQUITY_CATEGORIES = {
    "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
    "Flexi Cap", "Multi Cap", "ELSS", "Focused", "Value", "Contra",
    "Dividend Yield", "Sectoral/Thematic", "Index Funds",
}

# Default category → niftyindices `name` for non-index, non-sectoral funds.
CATEGORY_DEFAULT_BENCHMARK = {
    "Large Cap": "NIFTY 100",
    "Large & Mid Cap": "NIFTY LARGEMIDCAP 250",
    "Mid Cap": "NIFTY MIDCAP 150",
    "Small Cap": "NIFTY SMALLCAP 250",
    "Flexi Cap": "NIFTY 500",
    "Multi Cap": "NIFTY500 MULTICAP 50:25:25",
    "ELSS": "NIFTY 500",
    "Focused": "NIFTY 500",
    "Value": "NIFTY 500",
    "Contra": "NIFTY 500",
    "Dividend Yield": "NIFTY DIVIDEND OPPORTUNITIES 50",
}

# Index funds — match by scheme-name substring (case-insensitive).
INDEX_NAME_PATTERNS = [
    ("nifty next 50", "NIFTY NEXT 50"),
    ("nifty midcap 150", "NIFTY MIDCAP 150"),
    ("nifty largemidcap 250", "NIFTY LARGEMIDCAP 250"),
    ("nifty large midcap 250", "NIFTY LARGEMIDCAP 250"),
    ("nifty smallcap 250", "NIFTY SMALLCAP 250"),
    ("nifty 100", "NIFTY 100"),
    ("nifty 500", "NIFTY 500"),
    ("nifty 50", "NIFTY 50"),  # last — least specific
    ("sensex", None),  # BSE — out of scope
    ("bse 500", None),
]

# Sectoral funds — match by scheme-name substring (case-insensitive).
SECTORAL_PATTERNS = [
    ("financial services", "NIFTY FINANCIAL SERVICES"),
    ("finserv", "NIFTY FINANCIAL SERVICES"),
    ("banking & financial", "NIFTY FINANCIAL SERVICES"),
    ("pharma", "NIFTY PHARMA"),
    ("healthcare", "NIFTY PHARMA"),
    ("technology", "NIFTY IT"),
    ("digital", "NIFTY IT"),
    (" it ", "NIFTY IT"),
    ("auto", "NIFTY AUTO"),
    ("fmcg", "NIFTY FMCG"),
    ("consumption", "NIFTY FMCG"),
    ("infrastructure", "NIFTY INFRASTRUCTURE"),
    ("infra", "NIFTY INFRASTRUCTURE"),
    ("energy", "NIFTY ENERGY"),
    ("power", "NIFTY ENERGY"),
    ("metal", "NIFTY METAL"),
    ("mining", "NIFTY METAL"),
    ("psu", "NIFTY PSE"),
    ("mnc", "NIFTY MNC"),
    ("esg", "NIFTY 100 ESG"),
    ("manufacturing", "NIFTY INDIA MANUFACTURING"),
    ("banking", "NIFTY BANK"),  # last — Banking & FS already matched above
]


def _latest_holdings_snapshot() -> Path | None:
    if not HOLDINGS_ROOT.exists():
        return None
    dated = sorted(p for p in HOLDINGS_ROOT.iterdir()
                   if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    if not dated:
        return None
    return dated[-1] / "holdings.csv"


def resolve_benchmark(category: str, scheme_name: str) -> str | None:
    """Return the niftyindices `name` for this fund, or None if out of v1 scope."""
    if not category or category not in EQUITY_CATEGORIES:
        return None
    name_lower = (scheme_name or "").lower()

    if category == "Index Funds":
        for needle, bench in INDEX_NAME_PATTERNS:
            if needle in name_lower:
                return bench  # may be None (out of scope, e.g. Sensex)
        # Index fund we don't recognize — log and skip rather than guess.
        print(f"[skip] Index fund with unrecognized index: {scheme_name!r}",
              file=sys.stderr)
        return None

    if category == "Sectoral/Thematic":
        for needle, bench in SECTORAL_PATTERNS:
            if needle in name_lower:
                return bench
        # Unknown sector — fall back to Nifty 500 with a low-confidence flag.
        print(f"[low-confidence] Unrecognized sectoral fund, defaulting to NIFTY 500: {scheme_name!r}",
              file=sys.stderr)
        return "NIFTY 500"

    return CATEGORY_DEFAULT_BENCHMARK.get(category)


def benchmarks_needed(holdings: pd.DataFrame) -> dict[str, list[str]]:
    """Return {benchmark_name: [scheme_name, ...]} for in-scope funds."""
    out: dict[str, list[str]] = {}
    skipped: list[tuple[str, str]] = []
    for _, row in holdings.iterrows():
        bench = resolve_benchmark(row.get("category", ""), row.get("scheme_name", ""))
        if bench is None:
            skipped.append((row.get("scheme_name", ""), row.get("category", "")))
            continue
        out.setdefault(bench, []).append(row.get("scheme_name", ""))
    if skipped:
        print(f"\nSkipped {len(skipped)} fund(s) (out of v1 scope or unmappable):",
              file=sys.stderr)
        for name, cat in skipped:
            print(f"  - {name[:55]:<55}  [{cat}]", file=sys.stderr)
    return out


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh all TRI benchmarks for the current portfolio")
    p.add_argument("--holdings", type=Path,
                   help="Path to holdings.csv (default: latest snapshot under data/holdings)")
    p.add_argument("--start", type=_parse_date, default=date(2013, 1, 1),
                   help="Start date (YYYY-MM-DD). Default: 2013-01-01")
    p.add_argument("--end", type=_parse_date, default=date.today(),
                   help="End date (YYYY-MM-DD). Default: today")
    p.add_argument("--force", "-f", action="store_true",
                   help="Bypass per-benchmark cache")
    args = p.parse_args(argv)

    holdings_path = args.holdings or _latest_holdings_snapshot()
    if not holdings_path or not holdings_path.exists():
        print("No holdings snapshot found. Run zerodha-portfolio-sync first.",
              file=sys.stderr)
        return 1
    print(f"Reading holdings from {holdings_path}", file=sys.stderr)
    holdings = pd.read_csv(holdings_path)

    needed = benchmarks_needed(holdings)
    print(f"\n{len(needed)} unique benchmark(s) needed for "
          f"{sum(len(v) for v in needed.values())} in-scope fund(s):",
          file=sys.stderr)
    for bench, funds in sorted(needed.items()):
        print(f"  {bench:<35}  ({len(funds)} fund{'s' if len(funds) > 1 else ''})",
              file=sys.stderr)

    print(f"\nFetching from {args.start} to {args.end}...", file=sys.stderr)
    successes = 0
    failures: list[str] = []
    for bench in sorted(needed):
        df = fetch_tri(bench, args.start, args.end, force=args.force)
        if df is None:
            failures.append(bench)
        else:
            successes += 1

    print(f"\nDone: {successes}/{len(needed)} benchmark(s) cached successfully.",
          file=sys.stderr)
    if failures:
        print(f"Failed: {failures}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

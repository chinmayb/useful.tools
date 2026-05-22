"""Refresh the AMFI scheme master from portal.amfiindia.com.

Produces data/amfi_scheme_master.csv with columns:
    scheme_code, isin_growth, isin_reinvest, scheme_name, category, amc, nav, nav_date

Parsing details: see .claude/skills/fetch-nav-history/references/amfi_format.md

Usage:
    python -m scripts.refresh_scheme_master            # via Python -m
    python .claude/skills/fetch-nav-history/scripts/refresh_scheme_master.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
DEFAULT_OUTPUT = Path("data/amfi_scheme_master.csv")
CACHE_TTL_HOURS = 24


def fetch_raw(url: str = AMFI_URL, timeout: int = 30) -> str:
    """Fetch the raw NAVAll.txt body."""
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "mf_analyze/1.0"})
    resp.raise_for_status()
    return resp.text


def _normalize_category(amfi_str: str | None) -> str | None:
    """Strip AMFI prefixes/suffixes to get a clean SEBI-ish category name.

    Also collapses internal whitespace (AMFI occasionally publishes strings like
    'Sectoral/ Thematic' with a stray space).
    """
    if not amfi_str:
        return None
    s = amfi_str.strip()
    # Strip leading scheme-type prefix
    for prefix in ("Equity Scheme - ", "Debt Scheme - ", "Hybrid Scheme - ",
                   "Other Scheme - ", "Solution Oriented Scheme - "):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Strip trailing ' Fund'
    if s.endswith(" Fund"):
        s = s[: -len(" Fund")]
    # Collapse internal whitespace and tidy slash spacing
    s = " ".join(s.split())
    s = s.replace(" / ", "/").replace("/ ", "/").replace(" /", "/")
    return s


def parse(raw: str) -> pd.DataFrame:
    """Parse NAVAll.txt body into a DataFrame.

    See references/amfi_format.md for the format spec.
    """
    rows = []
    current_category = None
    current_amc = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Scheme Code"):
            continue  # column header
        if ";" not in line:
            # Category header has "(" and ")"; AMC header does not.
            if "(" in line and ")" in line:
                # e.g. "Open Ended Schemes(Equity Scheme - Small Cap Fund)"
                raw_cat = line.split("(", 1)[-1].rstrip(")").strip()
                current_category = _normalize_category(raw_cat)
            else:
                current_amc = line
            continue
        parts = line.split(";")
        if len(parts) != 6:
            continue  # malformed
        scheme_code = parts[0].strip()
        if not scheme_code.isdigit():
            continue
        nav_raw = parts[4].strip()
        try:
            nav = float(nav_raw) if nav_raw and nav_raw.upper() != "N.A." else None
        except ValueError:
            nav = None
        nav_date_raw = parts[5].strip()
        try:
            nav_date = datetime.strptime(nav_date_raw, "%d-%b-%Y").date().isoformat()
        except ValueError:
            nav_date = None
        rows.append({
            "scheme_code": scheme_code,
            "isin_growth": parts[1].strip() or None,
            "isin_reinvest": parts[2].strip() or None,
            "scheme_name": parts[3].strip(),
            "category": current_category,
            "amc": current_amc,
            "nav": nav,
            "nav_date": nav_date,
        })

    return pd.DataFrame(rows)


def is_cache_fresh(path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(tz=timezone.utc) - mtime
    return age < timedelta(hours=ttl_hours)


def refresh(output: Path = DEFAULT_OUTPUT, force: bool = False) -> pd.DataFrame:
    """Refresh the scheme master, writing CSV. Returns the DataFrame.

    Skips fetch if cache is fresh and force=False.
    """
    output = Path(output)
    if not force and is_cache_fresh(output):
        return pd.read_csv(output, dtype={"scheme_code": str})

    print(f"Fetching {AMFI_URL} ...", file=sys.stderr)
    raw = fetch_raw()
    df = parse(raw)
    if df.empty:
        raise RuntimeError("Parsed 0 rows from AMFI dump — format may have changed.")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f"Wrote {len(df)} schemes to {output}", file=sys.stderr)
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh AMFI scheme master")
    p.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--force", "-f", action="store_true", help="Bypass cache")
    args = p.parse_args(argv)
    refresh(args.output, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())

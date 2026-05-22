"""Fetch a single TRI (Total Return Index) series from niftyindices.com.

Endpoint contract: see references/niftyindices_endpoint.md
Mapping table:     see references/category_to_benchmark.md

Writes:
    data/benchmarks/<slug>.csv             columns: date, value
    data/benchmarks/_errors.jsonl          appended JSON Lines on failure

Honors a 1-day cache TTL; pass --force to refetch.

Usage:
    python fetch_tri.py "NIFTY 50"
    python fetch_tri.py "NIFTY SMALLCAP 250" --start 2020-01-01
    python fetch_tri.py "NIFTY 500" --force
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString"
BENCH_DIR = Path("data/benchmarks")
ERRORS_FILE = BENCH_DIR / "_errors.jsonl"
CACHE_TTL_HOURS = 24
CHUNK_DAYS = 365  # niftyindices accepts longer ranges, but chunking is safer
RATE_LIMIT_SEC = 1.0  # be courteous

HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Referer": "https://www.niftyindices.com/reports/historical-data/",
    "Origin": "https://www.niftyindices.com",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


def index_slug(name: str) -> str:
    """Filesystem-safe slug for an index name."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _cache_path(index_name: str) -> Path:
    return BENCH_DIR / f"{index_slug(index_name)}.csv"


def _manual_path(index_name: str) -> Path:
    return BENCH_DIR / f"{index_slug(index_name)}.manual.csv"


def _is_cache_fresh(path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - mtime < timedelta(hours=ttl_hours)


def _log_error(index_name: str, error: str) -> None:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "index_name": index_name,
        "error": error,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
    with ERRORS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _fetch_chunk(index_name: str, start: date, end: date, timeout: int = 30) -> list[dict]:
    """Fetch one chunk of TRI data. Returns parsed rows or [] on failure."""
    inner = (
        "{ 'name': '" + index_name + "', "
        "'startDate': '" + start.strftime("%d-%b-%Y") + "', "
        "'endDate': '" + end.strftime("%d-%b-%Y") + "', "
        "'indexName': '" + index_name + " - TRI' }"
    )
    body = {"cinfo": inner}
    resp = requests.post(TRI_URL, json=body, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    raw = payload.get("d", "")
    if not raw:
        return []
    return json.loads(raw)


def fetch_tri(
    index_name: str,
    start: date,
    end: date,
    force: bool = False,
    chunk_days: int = CHUNK_DAYS,
) -> pd.DataFrame | None:
    """Fetch TRI history for index_name between start..end (inclusive).

    Returns a DataFrame with [date, value] sorted ascending, or None on failure.
    Honors the on-disk cache and writes results back. Falls back to manual CSV
    if the network fetch fails entirely.
    """
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(index_name)

    if not force and _is_cache_fresh(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        return df

    chunks: list[dict] = []
    cursor = start
    chunk_count = 0
    failures = 0
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        try:
            rows = _fetch_chunk(index_name, cursor, chunk_end)
            chunks.extend(rows)
            chunk_count += 1
            if chunk_end < end:
                time.sleep(RATE_LIMIT_SEC)
        except (requests.RequestException, ValueError) as exc:
            failures += 1
            _log_error(index_name, f"chunk {cursor}..{chunk_end} failed: {exc}")
            # Continue with next chunk — partial data is still useful.
        cursor = chunk_end + timedelta(days=1)

    if not chunks:
        # Network path completely failed — try manual CSV fallback.
        manual = _manual_path(index_name)
        if manual.exists():
            print(f"Using manual fallback at {manual}", file=sys.stderr)
            df = pd.read_csv(manual, parse_dates=["date"])
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            return df
        _log_error(index_name, "no data fetched and no manual fallback present")
        return None

    rows = []
    for row in chunks:
        try:
            d = datetime.strptime(row["Date"], "%d %b %Y").date().isoformat()
            value = round(float(row["TotalReturnsIndex"]), 4)
        except (KeyError, ValueError):
            continue
        rows.append({"date": d, "value": value})

    if not rows:
        _log_error(index_name, "all rows failed to parse")
        return None

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    df.to_csv(cache_path, index=False)
    print(
        f"Wrote {len(df)} TRI rows for '{index_name}' to {cache_path} "
        f"({chunk_count} chunk(s), {failures} chunk failure(s))",
        file=sys.stderr,
    )
    return df


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch TRI history from niftyindices.com")
    p.add_argument("index_name", help='niftyindices "name" value, e.g. "NIFTY 50"')
    p.add_argument("--start", type=_parse_date, default=date(2013, 1, 1),
                   help="Start date (YYYY-MM-DD). Default: 2013-01-01 (Direct Plan launch)")
    p.add_argument("--end", type=_parse_date, default=date.today(),
                   help="End date (YYYY-MM-DD). Default: today")
    p.add_argument("--force", "-f", action="store_true", help="Bypass cache")
    args = p.parse_args(argv)

    df = fetch_tri(args.index_name, args.start, args.end, force=args.force)
    if df is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

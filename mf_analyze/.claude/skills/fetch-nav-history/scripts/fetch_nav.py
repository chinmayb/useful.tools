"""Fetch daily NAV history from mfapi.in for one or more scheme codes.

Writes:
    data/nav/<scheme_code>.csv      one row per (scheme_code, date), columns: date, nav
    data/nav/_errors.jsonl          appended JSON Lines on fetch failure

Honors a 1-day cache TTL; pass --force to refetch.

Usage:
    python fetch_nav.py 120586 122639            # fetch by scheme code
    python fetch_nav.py --isin INF200K01VK5      # resolve ISIN via the scheme master
    python fetch_nav.py --portfolio              # fetch for every scheme present in data/holdings/*/holdings.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

MFAPI_URL = "https://api.mfapi.in/mf/{scheme_code}"
NAV_DIR = Path("data/nav")
ERRORS_FILE = NAV_DIR / "_errors.jsonl"
SCHEME_MASTER = Path("data/amfi_scheme_master.csv")
CACHE_TTL_HOURS = 24
RATE_LIMIT_RPS = 3  # requests per second


def _is_cache_fresh(path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - mtime < timedelta(hours=ttl_hours)


def _log_error(scheme_code: str, error: str) -> None:
    NAV_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "scheme_code": scheme_code,
        "error": error,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
    with ERRORS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _resolve_isin_to_scheme_code(isin: str, master: pd.DataFrame) -> str | None:
    hit = master[(master["isin_growth"] == isin) | (master["isin_reinvest"] == isin)]
    if hit.empty:
        return None
    return str(hit.iloc[0]["scheme_code"])


def fetch_one(scheme_code: str, force: bool = False, timeout: int = 30) -> pd.DataFrame | None:
    """Fetch (or load cached) NAV history for one scheme code. Returns DataFrame or None on failure."""
    NAV_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = NAV_DIR / f"{scheme_code}.csv"

    if not force and _is_cache_fresh(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"]).assign(
            date=lambda d: d["date"].dt.strftime("%Y-%m-%d")
        )

    url = MFAPI_URL.format(scheme_code=scheme_code)
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "mf_analyze/1.0"})
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        _log_error(scheme_code, f"fetch failed: {exc}")
        return None

    data = payload.get("data") or []
    if not data:
        _log_error(scheme_code, "empty data array from mfapi.in")
        return None

    rows = []
    for row in data:
        try:
            d = datetime.strptime(row["date"], "%d-%m-%Y").date().isoformat()
            nav = round(float(row["nav"]), 4)
        except (KeyError, ValueError):
            continue
        rows.append({"date": d, "nav": nav})

    if not rows:
        _log_error(scheme_code, "all rows failed to parse")
        return None

    df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    return df


def fetch_many(
    scheme_codes: list[str],
    force: bool = False,
    rate_limit_rps: float = RATE_LIMIT_RPS,
) -> dict[str, pd.DataFrame]:
    """Fetch multiple scheme codes, rate-limited. Returns dict[scheme_code -> DataFrame]."""
    delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0
    out: dict[str, pd.DataFrame] = {}
    for i, sc in enumerate(scheme_codes):
        df = fetch_one(sc, force=force)
        if df is not None:
            out[sc] = df
        if delay and i < len(scheme_codes) - 1:
            time.sleep(delay)
    return out


def combine_long(navs: dict[str, pd.DataFrame], master: pd.DataFrame) -> pd.DataFrame:
    """Combine per-scheme NAV frames into a long-format DataFrame joined with the scheme master."""
    frames = []
    for sc, df in navs.items():
        df = df.copy()
        df["scheme_code"] = sc
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["isin", "scheme_code", "scheme_name", "category", "date", "nav"])
    combined = pd.concat(frames, ignore_index=True)
    master_slim = master.rename(columns={"isin_growth": "isin"})[
        ["scheme_code", "isin", "scheme_name", "category"]
    ]
    master_slim["scheme_code"] = master_slim["scheme_code"].astype(str)
    combined["scheme_code"] = combined["scheme_code"].astype(str)
    return combined.merge(master_slim, on="scheme_code", how="left")[
        ["isin", "scheme_code", "scheme_name", "category", "date", "nav"]
    ]


def _load_master() -> pd.DataFrame:
    if not SCHEME_MASTER.exists():
        raise SystemExit(
            f"Scheme master not found at {SCHEME_MASTER}. "
            "Run refresh_scheme_master.py first."
        )
    return pd.read_csv(SCHEME_MASTER, dtype={"scheme_code": str})


def _scheme_codes_from_portfolio(master: pd.DataFrame) -> list[str]:
    """Find every ISIN currently in any holdings snapshot, resolve to scheme codes."""
    holdings_dir = Path("data/holdings")
    if not holdings_dir.exists():
        return []
    isins: set[str] = set()
    for csv_path in holdings_dir.glob("*/holdings.csv"):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        if "isin" in df.columns:
            isins.update(df["isin"].dropna().astype(str).tolist())
    codes = []
    for isin in isins:
        sc = _resolve_isin_to_scheme_code(isin, master)
        if sc:
            codes.append(sc)
    return sorted(set(codes))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch NAV history from mfapi.in")
    p.add_argument("scheme_codes", nargs="*", help="Scheme codes")
    p.add_argument("--isin", action="append", default=[], help="Look up ISIN(s) via scheme master")
    p.add_argument("--portfolio", action="store_true",
                   help="Fetch every scheme present in data/holdings/*/holdings.csv")
    p.add_argument("--force", "-f", action="store_true", help="Bypass cache")
    args = p.parse_args(argv)

    master = _load_master()
    codes = list(args.scheme_codes)

    for isin in args.isin:
        sc = _resolve_isin_to_scheme_code(isin, master)
        if sc is None:
            print(f"ISIN {isin} not found in scheme master", file=sys.stderr)
        else:
            codes.append(sc)

    if args.portfolio:
        codes.extend(_scheme_codes_from_portfolio(master))

    codes = sorted(set(codes))
    if not codes:
        print("No scheme codes to fetch. Pass codes positionally, via --isin, or --portfolio.",
              file=sys.stderr)
        return 1

    print(f"Fetching {len(codes)} scheme(s) at {RATE_LIMIT_RPS} req/s...", file=sys.stderr)
    navs = fetch_many(codes, force=args.force)
    combined = combine_long(navs, master)
    print(f"Fetched {len(navs)}/{len(codes)} successfully; {len(combined)} total rows", file=sys.stderr)
    if len(navs) < len(codes):
        print(f"See {ERRORS_FILE} for failures.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

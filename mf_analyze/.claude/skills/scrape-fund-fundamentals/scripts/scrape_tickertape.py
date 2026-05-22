"""Scrape Indian MF fundamentals from Tickertape.

Inputs: ISIN(s) or --portfolio (latest holdings snapshot).
Auth:   reads ~/.config/mf_analyze/tickertape.env (JWT + CSRF).
Output: data/fundamentals/<isin>.json (14-day cache TTL).

See SKILL.md and references/tickertape_endpoints.md for endpoint contracts.

Usage:
    python scrape_tickertape.py --portfolio
    python scrape_tickertape.py --isin INF879O01027 --isin INF200K01T51
    python scrape_tickertape.py --portfolio --force
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

AUTH_FILE = Path.home() / ".config" / "mf_analyze" / "tickertape.env"
SCHEME_MASTER = Path("data/amfi_scheme_master.csv")
HOLDINGS_ROOT = Path("data/holdings")
FUND_DIR = Path("data/fundamentals")
ERRORS_FILE = FUND_DIR / "_errors.jsonl"
CACHE_TTL_DAYS = 14
RATE_LIMIT_SEC = 1.0

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


# ---------------------------------------------------------------------- Auth

def load_auth() -> dict:
    """Read JWT + CSRF from the env file. Exit with refresh instructions if missing."""
    if not AUTH_FILE.exists():
        sys.exit(
            f"\nMissing {AUTH_FILE}\n"
            "Create it with:\n"
            '  TICKERTAPE_JWT="<jwt>"\n'
            '  TICKERTAPE_CSRF="<csrf>"\n'
            "See SKILL.md § Authentication for the refresh procedure.\n"
        )
    creds = {}
    for line in AUTH_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
    if not creds.get("TICKERTAPE_JWT") or not creds.get("TICKERTAPE_CSRF"):
        sys.exit(f"{AUTH_FILE} missing TICKERTAPE_JWT or TICKERTAPE_CSRF")
    return creds


def _print_token_refresh_help() -> None:
    print(
        "\nTickertape JWT appears expired (HTTP 401).\n"
        "Refresh:\n"
        "  1. Log in at https://www.tickertape.in\n"
        "  2. DevTools → Network → Fetch/XHR → reload a fund page\n"
        "  3. Copy as cURL on any api.tickertape.in request\n"
        "  4. Extract jwt=... and x-csrf-token, update "
        f"{AUTH_FILE}\n",
        file=sys.stderr,
    )


# ----------------------------------------------------------- ISIN → SID resolve

_NOISE_TOKENS = {
    "direct", "regular", "growth", "option", "plan", "idcw",
    "payout", "reinvestment", "income", "distribution",
}


def _normalize_name(s: str) -> str:
    """Lowercase + strip plan/option suffix tokens entirely, regardless of order."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t and t not in _NOISE_TOKENS]
    return " ".join(tokens)


def search_mf(query: str, auth: dict, timeout: int = 10) -> list[dict]:
    """Authenticated MF search. Returns list of items (may be empty)."""
    url = f"https://api.tickertape.in/search?text={requests.utils.quote(query)}&types=mutualfund"
    headers = {
        "accept": "application/json",
        "accept-version": "8.14.0",
        "origin": "https://www.tickertape.in",
        "x-csrf-token": auth["TICKERTAPE_CSRF"],
        "x-device-type": "web",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    cookies = {"jwt": auth["TICKERTAPE_JWT"]}
    resp = requests.get(url, headers=headers, cookies=cookies, timeout=timeout)
    if resp.status_code == 401:
        _print_token_refresh_help()
        sys.exit(2)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("items", [])


def resolve_isin_to_sid(isin: str, master: pd.DataFrame, auth: dict) -> tuple[str, str] | None:
    """Map (ISIN) → (sid, slug). Returns None if no confident match.

    Strategy: pull AMFI scheme name → normalize → search → filter for Growth →
    fuzzy-match fullname; require similarity ≥ 0.65 (0-1).
    """
    hit = master[
        (master["isin_growth"] == isin) | (master["isin_reinvest"] == isin)
    ]
    if hit.empty:
        return None
    amfi_name = hit.iloc[0]["scheme_name"]
    norm_amfi = _normalize_name(amfi_name)
    # Use the first ~6 distinctive tokens as the search query
    query = " ".join(norm_amfi.split()[:6])
    items = search_mf(query, auth)
    if not items:
        return None
    candidates = [it for it in items if it.get("option") == "Growth"]
    if not candidates:
        candidates = items  # fallback: any option
    best, best_score = None, 0.0
    for it in candidates:
        score = difflib.SequenceMatcher(
            None, norm_amfi, _normalize_name(it.get("fullname", ""))
        ).ratio()
        if score > best_score:
            best, best_score = it, score
    if best is None or best_score < 0.65:
        return None
    return best["id"], best["slug"]


# --------------------------------------------------------------- Page scraping

def fetch_fund_pageprops(slug_or_sid: str, timeout: int = 20) -> dict | None:
    """Fetch the SSR'd fund page and extract pageProps. No auth needed."""
    if slug_or_sid.startswith("/"):
        url = f"https://www.tickertape.in{slug_or_sid}"
    else:
        url = f"https://www.tickertape.in/mutualfunds/{slug_or_sid}"
    resp = requests.get(
        url,
        headers={
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
        },
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return None
    data = json.loads(m.group(1))
    return data.get("props", {}).get("pageProps") or None


def fetch_scorecard(sid: str, auth: dict, timeout: int = 10) -> list[dict]:
    """Fetch the authenticated scorecard for sid. Empty list on any failure."""
    url = f"https://analyze.api.tickertape.in/mutualfunds/scorecard/{sid}"
    headers = {
        "accept": "application/json",
        "accept-version": "1.0.0",
        "origin": "https://www.tickertape.in",
        "x-csrf-token": auth["TICKERTAPE_CSRF"],
        "x-device-type": "web",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    cookies = {"jwt": auth["TICKERTAPE_JWT"]}
    try:
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=timeout)
    except requests.RequestException:
        return []
    if resp.status_code == 401:
        _print_token_refresh_help()
        sys.exit(2)
    if not resp.ok:
        return []
    return resp.json().get("data") or []


# ---------------------------------------------------------- Field extraction

def _kv_lookup(arr: list[dict], key_field: str, key_value: str, value_field: str = "value"):
    """Find an item where item[key_field] == key_value; return its value_field."""
    if not isinstance(arr, list):
        return None
    for item in arr:
        if isinstance(item, dict) and item.get(key_field) == key_value:
            return item.get(value_field)
    return None


def _kv_lookup_full(arr: list[dict], key_field: str, key_value: str):
    if not isinstance(arr, list):
        return None
    for item in arr:
        if isinstance(item, dict) and item.get(key_field) == key_value:
            return item
    return None


def extract_record(pp: dict, isin: str, scorecard: list[dict] | None = None) -> dict:
    """Map pageProps to our flat fundamentals schema.

    `scorecard` overrides pp['scorecard'] when supplied — the standalone
    /mutualfunds/scorecard/<sid> endpoint returns richer data (rank, peers,
    score values) than the stubbed copy embedded in pageProps.
    """
    si = pp.get("securityInfo") or {}
    ss = pp.get("securitySummary") or {}
    meta = ss.get("meta") or {}
    key_ratios = ss.get("keyRatios") or []
    scheme_info = ss.get("schemeInfo") or []
    amc_details = ss.get("amcDetails") or {}
    fund_mgrs = pp.get("fundManagers") or []
    if scorecard is None:
        scorecard = pp.get("scorecard") or []

    exit_load = _kv_lookup_full(scheme_info, "backL", "exitLoad") or {}

    return {
        "isin": isin or meta.get("isin"),
        "tickertape_sid": si.get("mfId") or pp.get("mfId"),
        "scheme_name": si.get("name") or meta.get("name"),
        "amc": meta.get("amc") or si.get("amc"),
        "plan": meta.get("plan"),
        "option": meta.get("option") or si.get("option"),
        "subsector": si.get("subsector") or meta.get("subsector"),
        "risk_classification": meta.get("riskClassification"),
        "stated_benchmark": meta.get("benchmarkIndex"),
        "nav_close": si.get("navClose"),
        "expense_ratio_pct": _kv_lookup(key_ratios, "backL", "expRatio"),
        "category_expense_ratio_pct": _kv_lookup(key_ratios, "backL", "catExpRatio"),
        "pe": _kv_lookup(key_ratios, "backL", "pe"),
        "sharpe_tickertape": _kv_lookup(key_ratios, "backL", "sharpe"),
        "aum_cr": amc_details.get("aum"),
        "exit_load_pct": exit_load.get("value"),
        "exit_load_remarks": exit_load.get("info") or meta.get("exitLoadRemarks"),
        "lock_in_months": _kv_lookup(scheme_info, "backL", "lockInPeriod"),
        "min_sip_amount": _kv_lookup(scheme_info, "backL", "sipinvest"),
        "managers": [
            {
                "name": m.get("name"),
                "fm_code": m.get("fmCode"),
                "experience_years": _coerce_int(m.get("exp")),
                "qualification": m.get("qualification"),
                "aum_cr": m.get("aumInCr"),
            }
            for m in fund_mgrs
        ],
        "scorecard": [
            {
                "name": s.get("name"),
                "tag": s.get("tag"),
                "color": s.get("colour"),
                "rank": s.get("rank"),
                "peers": s.get("peers"),
                "score": _coerce_float(_safe_get(s, "score", "value")),
                "score_max": _safe_get(s, "score", "max"),
                "description": s.get("description"),
                "last_updated": s.get("lastUpdated"),
            }
            for s in scorecard
        ],
        "cagr_series": [
            {
                "year_diff": c.get("yearDiff"),
                "value_pct": c.get("value"),
            }
            for c in (ss.get("cagrSeries") or [])
        ],
        "scraped_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "tickertape",
    }


def _coerce_float(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_int(x):
    try:
        return int(float(x)) if x is not None else None
    except (TypeError, ValueError):
        return None


def _safe_get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


# --------------------------------------------------------------- Cache / I/O

def _is_cache_fresh(path: Path, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(tz=timezone.utc) - mtime < timedelta(days=ttl_days)


def _log_error(isin: str, error: str) -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "isin": isin,
        "error": error,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
    with ERRORS_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_manual(isin: str) -> dict | None:
    manual = FUND_DIR / f"{isin}.manual.json"
    if manual.exists():
        with manual.open() as f:
            d = json.load(f)
            d["source"] = "manual"
            return d
    return None


def fetch_fund(isin: str, master: pd.DataFrame, auth: dict, force: bool = False) -> dict | None:
    """Top-level: get fundamentals for one ISIN. Honors manual + cache."""
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = FUND_DIR / f"{isin}.json"

    manual = _read_manual(isin)
    if manual is not None:
        print(f"[manual] {isin}", file=sys.stderr)
        return manual

    if not force and _is_cache_fresh(cache_path):
        with cache_path.open() as f:
            return json.load(f)

    # If we previously resolved a SID for this ISIN, reuse it (skip search).
    sid = None
    slug = None
    if cache_path.exists():
        try:
            prev = json.loads(cache_path.read_text())
            sid = prev.get("tickertape_sid")
        except Exception:
            sid = None

    if sid is None:
        try:
            resolved = resolve_isin_to_sid(isin, master, auth)
        except requests.RequestException as exc:
            _log_error(isin, f"search failed: {exc}")
            print(f"[error] {isin} search failed: {exc}", file=sys.stderr)
            return None
        if resolved is None:
            _log_error(isin, "no confident Tickertape match")
            print(f"[skip]  {isin} no confident Tickertape match", file=sys.stderr)
            return None
        sid, slug = resolved

    try:
        pp = fetch_fund_pageprops(slug or sid)
    except requests.RequestException as exc:
        _log_error(isin, f"page fetch failed: {exc}")
        print(f"[error] {isin} page fetch failed: {exc}", file=sys.stderr)
        return None

    if pp is None:
        _log_error(isin, "__NEXT_DATA__ not found on page")
        print(f"[error] {isin} __NEXT_DATA__ missing on Tickertape page", file=sys.stderr)
        return None

    # Pull the richer scorecard from the auth'd endpoint (the pageProps copy is a stub).
    sid_for_scorecard = pp.get("mfId") or sid or (pp.get("securityInfo") or {}).get("mfId")
    rich_scorecard = fetch_scorecard(sid_for_scorecard, auth) if sid_for_scorecard else []
    record = extract_record(pp, isin, scorecard=rich_scorecard or None)
    with cache_path.open("w") as f:
        json.dump(record, f, indent=2)
    print(
        f"[ok]    {isin} {record.get('tickertape_sid')}  "
        f"expRatio={record.get('expense_ratio_pct')}  "
        f"AUM={record.get('aum_cr')}cr  "
        f"managers={len(record.get('managers') or [])}",
        file=sys.stderr,
    )
    return record


# --------------------------------------------------------------- CLI plumbing

def _latest_holdings_snapshot() -> Path | None:
    if not HOLDINGS_ROOT.exists():
        return None
    dated = sorted(p for p in HOLDINGS_ROOT.iterdir()
                   if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    if not dated:
        return None
    return dated[-1] / "holdings.csv"


def _isins_from_portfolio() -> list[str]:
    path = _latest_holdings_snapshot()
    if not path or not path.exists():
        return []
    df = pd.read_csv(path, dtype={"isin": str})
    return df["isin"].dropna().astype(str).unique().tolist()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scrape Indian MF fundamentals from Tickertape")
    p.add_argument("--isin", action="append", default=[],
                   help="ISIN (repeatable)")
    p.add_argument("--portfolio", action="store_true",
                   help="Scrape all ISINs in the latest holdings snapshot")
    p.add_argument("--force", "-f", action="store_true",
                   help="Bypass the 14-day cache")
    args = p.parse_args(argv)

    isins = list(args.isin)
    if args.portfolio:
        isins.extend(_isins_from_portfolio())
    isins = sorted(set(i for i in isins if i))
    if not isins:
        print("No ISINs to scrape. Pass --isin or --portfolio.", file=sys.stderr)
        return 1

    if not SCHEME_MASTER.exists():
        sys.exit("AMFI scheme master not found. Run fetch-nav-history first.")
    master = pd.read_csv(SCHEME_MASTER, dtype={"scheme_code": str})
    auth = load_auth()

    print(f"Scraping {len(isins)} ISIN(s) at ~1 req/sec...", file=sys.stderr)
    successes = 0
    for i, isin in enumerate(isins):
        rec = fetch_fund(isin, master, auth)
        if rec is not None:
            successes += 1
        if i < len(isins) - 1:
            time.sleep(RATE_LIMIT_SEC)

    print(f"\nDone: {successes}/{len(isins)} cached.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

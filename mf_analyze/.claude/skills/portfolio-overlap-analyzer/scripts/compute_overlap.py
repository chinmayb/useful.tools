"""Compute the three pairwise overlap matrices for the current portfolio.

Reads:
    data/holdings/<latest>/holdings.csv      (in-scope filter via category)
    data/fundamentals/<isin>.json            (top_holdings + sector_weights)
    data/nav/<scheme_code>.csv               (for return correlation)

Writes:
    data/overlap/<YYYY-MM-DD>/stock_overlap.csv
    data/overlap/<YYYY-MM-DD>/sector_overlap.csv
    data/overlap/<YYYY-MM-DD>/return_correlation.csv
    data/overlap/<YYYY-MM-DD>/pairs_ranked.csv       # main consumable

Usage:
    python compute_overlap.py
    python compute_overlap.py --holdings data/holdings/2026-05-22/holdings.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from lib_overlap import (  # noqa: E402
    weighted_jaccard,
    cosine_similarity,
    monthly_returns,
    correlation_matrix,
    redundancy_score,
    is_redundant,
)

HOLDINGS_ROOT = Path("data/holdings")
NAV_DIR = Path("data/nav")
FUND_DIR = Path("data/fundamentals")
OVERLAP_ROOT = Path("data/overlap")

# Same equity-only filter as compute-core-metrics / benchmark-mapper.
EQUITY_CATEGORIES = {
    "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
    "Flexi Cap", "Multi Cap", "ELSS", "Focused", "Value", "Contra",
    "Dividend Yield", "Sectoral/Thematic", "Index Funds",
}


def _latest_holdings_snapshot() -> Path | None:
    if not HOLDINGS_ROOT.exists():
        return None
    dated = sorted(p for p in HOLDINGS_ROOT.iterdir()
                   if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    return (dated[-1] / "holdings.csv") if dated else None


def _holding_key(h: dict) -> str | None:
    """Pick a stable key for a stock holding. Prefer ticker; else name; else SID."""
    return h.get("ticker") or h.get("name") or h.get("sid")


def _load_fund_data(isin: str) -> dict | None:
    path = FUND_DIR / f"{isin}.json"
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def _stock_weights(fund: dict) -> dict[str, float]:
    """Extract {ticker_or_name: weight_pct} from a fundamentals JSON."""
    holdings = fund.get("top_holdings") or []
    out: dict[str, float] = {}
    for h in holdings:
        if h.get("type") and h["type"] != "Equity":
            continue  # ignore cash / bonds in stock-overlap calc
        key = _holding_key(h)
        if not key:
            continue
        w = h.get("weight_pct")
        if w is None:
            continue
        out[key] = out.get(key, 0.0) + float(w)
    return out


def _sector_vector(fund: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in fund.get("sector_weights") or []:
        name = s.get("sector")
        w = s.get("weight_pct")
        if name is None or w is None:
            continue
        out[name] = out.get(name, 0.0) + float(w)
    return out


def _load_monthly_returns(scheme_code: str, lookback_years: int = 5) -> pd.Series | None:
    path = NAV_DIR / f"{scheme_code}.csv"
    if not path.exists():
        return None
    try:
        nav = pd.read_csv(path)
    except Exception:
        return None
    if nav.empty:
        return None
    s = monthly_returns(nav)
    cutoff = s.index.max() - pd.DateOffset(years=lookback_years)
    return s.loc[s.index >= cutoff]


def compute(holdings: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    out_dir.mkdir(parents=True, exist_ok=True)

    in_scope = holdings[holdings["category"].isin(EQUITY_CATEGORIES)].copy()
    skipped = holdings[~holdings["category"].isin(EQUITY_CATEGORIES)]
    print(f"In-scope equity funds: {len(in_scope)}  (skipped: {len(skipped)})",
          file=sys.stderr)
    if len(in_scope) < 2:
        print("Need >=2 in-scope funds. Nothing to compare.", file=sys.stderr)
        return pd.DataFrame()

    # Build per-fund data
    stock_weights: dict[str, dict[str, float]] = {}
    sector_vecs: dict[str, dict[str, float]] = {}
    returns_by_isin: dict[str, pd.Series] = {}
    excluded_stock: list[str] = []
    excluded_sector: list[str] = []
    excluded_returns: list[str] = []

    for _, h in in_scope.iterrows():
        isin = h["isin"]
        scheme_code = str(h.get("scheme_code", ""))
        fund = _load_fund_data(isin)
        if fund is None:
            excluded_stock.append(isin)
            excluded_sector.append(isin)
        else:
            sw = _stock_weights(fund)
            if len(sw) >= 5:
                stock_weights[isin] = sw
            else:
                excluded_stock.append(isin)
            sv = _sector_vector(fund)
            if sv:
                sector_vecs[isin] = sv
            else:
                excluded_sector.append(isin)
        ret = _load_monthly_returns(scheme_code)
        if ret is not None and len(ret) >= 12:
            returns_by_isin[isin] = ret
        else:
            excluded_returns.append(isin)

    print(f"Stock-overlap input: {len(stock_weights)} funds "
          f"(excluded: {len(excluded_stock)})", file=sys.stderr)
    print(f"Sector-overlap input: {len(sector_vecs)} funds "
          f"(excluded: {len(excluded_sector)})", file=sys.stderr)
    print(f"Return-correlation input: {len(returns_by_isin)} funds "
          f"(excluded: {len(excluded_returns)})", file=sys.stderr)

    # --- Stock overlap matrix
    stock_ids = sorted(stock_weights)
    stock_mat = pd.DataFrame(float("nan"), index=stock_ids, columns=stock_ids)
    for i in stock_ids:
        for j in stock_ids:
            if i == j:
                stock_mat.loc[i, j] = 1.0
            else:
                stock_mat.loc[i, j] = weighted_jaccard(stock_weights[i], stock_weights[j])
    stock_mat.to_csv(out_dir / "stock_overlap.csv")

    # --- Sector overlap matrix
    sector_ids = sorted(sector_vecs)
    sector_mat = pd.DataFrame(float("nan"), index=sector_ids, columns=sector_ids)
    for i in sector_ids:
        for j in sector_ids:
            if i == j:
                sector_mat.loc[i, j] = 1.0
            else:
                sector_mat.loc[i, j] = cosine_similarity(sector_vecs[i], sector_vecs[j])
    sector_mat.to_csv(out_dir / "sector_overlap.csv")

    # --- Return correlation matrix
    corr_mat = correlation_matrix(returns_by_isin)
    corr_mat.to_csv(out_dir / "return_correlation.csv")

    # --- Ranked pairs
    name_by_isin = dict(zip(in_scope["isin"], in_scope["scheme_name"]))
    cat_by_isin = dict(zip(in_scope["isin"], in_scope["category"]))
    all_isins = sorted(set(in_scope["isin"]))
    rows = []
    for i, a in enumerate(all_isins):
        for b in all_isins[i + 1:]:
            sj = stock_mat.loc[a, b] if a in stock_ids and b in stock_ids else float("nan")
            sc = sector_mat.loc[a, b] if a in sector_ids and b in sector_ids else float("nan")
            rc = corr_mat.loc[a, b] if a in corr_mat.index and b in corr_mat.columns else float("nan")
            rows.append({
                "isin_a": a,
                "isin_b": b,
                "name_a": name_by_isin.get(a, ""),
                "name_b": name_by_isin.get(b, ""),
                "category_a": cat_by_isin.get(a, ""),
                "category_b": cat_by_isin.get(b, ""),
                "stock_jaccard": round(sj, 4) if sj == sj else float("nan"),
                "sector_cosine": round(sc, 4) if sc == sc else float("nan"),
                "return_corr_5y": round(rc, 4) if rc == rc else float("nan"),
                "redundancy_score": round(redundancy_score(sj, sc, rc), 4),
                "redundant_flag": is_redundant(sj, sc, rc),
            })

    pairs = pd.DataFrame(rows).sort_values("redundancy_score", ascending=False)
    pairs.to_csv(out_dir / "pairs_ranked.csv", index=False)
    return pairs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute portfolio overlap matrices")
    p.add_argument("--holdings", type=Path,
                   help="Path to holdings.csv (default: latest snapshot)")
    p.add_argument("--date", default=date.today().isoformat(),
                   help="Output snapshot date (default: today)")
    args = p.parse_args(argv)

    holdings_path = args.holdings or _latest_holdings_snapshot()
    if not holdings_path or not holdings_path.exists():
        print("No holdings snapshot found. Run zerodha-portfolio-sync first.",
              file=sys.stderr)
        return 1

    print(f"Reading holdings from {holdings_path}", file=sys.stderr)
    holdings = pd.read_csv(holdings_path, dtype={"isin": str, "scheme_code": str})

    out_dir = OVERLAP_ROOT / args.date
    pairs = compute(holdings, out_dir)
    if pairs.empty:
        return 1
    flagged = pairs[pairs["redundant_flag"]]
    print(f"\nWrote {len(pairs)} pairs to {out_dir}", file=sys.stderr)
    print(f"Flagged as redundant: {len(flagged)}/{len(pairs)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

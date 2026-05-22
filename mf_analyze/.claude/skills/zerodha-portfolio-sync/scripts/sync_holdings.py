"""Sync mutual-fund holdings from Zerodha (or a manual CSV) into the project schema.

Inputs
------
One of:
  --from-json <path>     Path to a JSON file containing the Zerodha MCP
                         get_mf_holdings response (array of objects).
                         Use '-' to read JSON from stdin.
  --from-manual          Read data/holdings/manual_holdings.csv instead.

Outputs
-------
  data/holdings/<YYYY-MM-DD>/lots.csv      one row per (isin, folio)
  data/holdings/<YYYY-MM-DD>/holdings.csv  one row per isin (aggregated)

Both files use the canonical project schema (see CLAUDE.md). The aggregated
holdings.csv is what every downstream metric skill consumes; lots.csv is the
source of truth for tax-aware-rebalancer.

Usage
-----
  # Pipe Zerodha MCP response from Claude
  python sync_holdings.py --from-json zerodha_response.json

  # Manual fallback
  python sync_holdings.py --from-manual
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

SCHEME_MASTER = Path("data/amfi_scheme_master.csv")
HOLDINGS_ROOT = Path("data/holdings")
MANUAL_CSV = HOLDINGS_ROOT / "manual_holdings.csv"

LOTS_COLS = [
    "isin", "scheme_code", "scheme_name", "category", "folio",
    "units", "avg_cost", "invested_amount", "current_nav", "current_value",
    "pnl", "purchase_date",
]
HOLDINGS_COLS = [
    "isin", "scheme_code", "scheme_name", "category",
    "units", "avg_cost", "invested_amount", "current_nav", "current_value",
    "pnl", "folios",
]


def _load_master() -> pd.DataFrame:
    if not SCHEME_MASTER.exists():
        raise SystemExit(
            f"Scheme master not found at {SCHEME_MASTER}. "
            "Run .claude/skills/fetch-nav-history/scripts/refresh_scheme_master.py first."
        )
    df = pd.read_csv(SCHEME_MASTER, dtype={"scheme_code": str})
    # Build an ISIN → (scheme_code, scheme_name, category) lookup.
    # AMFI publishes growth and reinvest ISINs separately; both should resolve.
    growth = df[["isin_growth", "scheme_code", "scheme_name", "category"]].rename(
        columns={"isin_growth": "isin"}
    )
    reinvest = df[["isin_reinvest", "scheme_code", "scheme_name", "category"]].rename(
        columns={"isin_reinvest": "isin"}
    )
    lookup = pd.concat([growth, reinvest], ignore_index=True).dropna(subset=["isin"])
    return lookup.drop_duplicates(subset=["isin"], keep="first")


def _read_json_input(path: str) -> list[dict]:
    if path == "-":
        data = json.load(sys.stdin)
    else:
        with open(path) as f:
            data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit("Expected a JSON array of holding objects from Zerodha MCP.")
    return data


def lots_from_zerodha(payload: list[dict]) -> pd.DataFrame:
    """Convert raw Zerodha get_mf_holdings response into the lots schema."""
    rows = []
    for item in payload:
        try:
            # Zerodha MCP returns ISIN under "tradingsymbol" for MF holdings;
            # accept either spelling.
            isin = item.get("isin") or item["tradingsymbol"]
            units = float(item["quantity"])
            avg_cost = float(item["average_price"])
            current_nav = float(item.get("last_price", item.get("nav", 0.0)))
        except (KeyError, TypeError, ValueError) as e:
            print(f"Skipping malformed row {item!r}: {e}", file=sys.stderr)
            continue
        invested = round(units * avg_cost, 2)
        current_value = round(units * current_nav, 2)
        rows.append({
            "isin": isin,
            "folio": str(item.get("folio", "")),
            "units": round(units, 4),
            "avg_cost": round(avg_cost, 4),
            "invested_amount": invested,
            "current_nav": round(current_nav, 4),
            "current_value": current_value,
            "pnl": round(current_value - invested, 2),
            "purchase_date": item.get("purchase_date") or item.get("last_price_date"),
        })
    return pd.DataFrame(rows)


def lots_from_manual(path: Path = MANUAL_CSV) -> pd.DataFrame:
    """Read the manual fallback CSV. Requires isin, units, avg_cost; folio + purchase_date optional."""
    if not path.exists():
        raise SystemExit(
            f"Manual holdings CSV not found at {path}. "
            "Copy assets/manual_holdings_template.csv there and fill it in."
        )
    df = pd.read_csv(path, dtype={"isin": str, "folio": str})
    required = {"isin", "units", "avg_cost"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Manual CSV missing required columns: {sorted(missing)}")
    df["folio"] = df.get("folio", pd.Series("", index=df.index)).fillna("").astype(str)
    df["purchase_date"] = df.get("purchase_date", pd.Series(None, index=df.index))
    df["invested_amount"] = (df["units"] * df["avg_cost"]).round(2)
    # Manual CSV doesn't carry current NAV — leave as null, will be filled
    # downstream by fetch-nav-history's latest row.
    df["current_nav"] = pd.NA
    df["current_value"] = pd.NA
    df["pnl"] = pd.NA
    return df[[
        "isin", "folio", "units", "avg_cost", "invested_amount",
        "current_nav", "current_value", "pnl", "purchase_date",
    ]]


def enrich_with_master(lots: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Join lots with AMFI scheme master to attach scheme_code, scheme_name, category."""
    enriched = lots.merge(master, on="isin", how="left")
    missing = enriched[enriched["scheme_code"].isna()]["isin"].unique().tolist()
    if missing:
        print(
            f"Warning: {len(missing)} ISIN(s) not found in AMFI scheme master: {missing}",
            file=sys.stderr,
        )
    # Reindex to the canonical lots schema (preserves NaN where columns are absent).
    for col in LOTS_COLS:
        if col not in enriched.columns:
            enriched[col] = pd.NA
    return enriched[LOTS_COLS]


def aggregate_to_holdings(lots: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-folio lots into per-ISIN holdings."""
    if lots.empty:
        return pd.DataFrame(columns=HOLDINGS_COLS)

    def _agg(group: pd.DataFrame) -> pd.Series:
        total_units = group["units"].sum()
        invested = group["invested_amount"].sum()
        weighted_avg = invested / total_units if total_units else float("nan")
        nav_series = group["current_nav"].dropna()
        current_nav = nav_series.max() if not nav_series.empty else pd.NA
        cv_series = group["current_value"].dropna()
        current_value = cv_series.sum() if not cv_series.empty else pd.NA
        pnl = (current_value - invested) if pd.notna(current_value) else pd.NA
        return pd.Series({
            "scheme_code": group["scheme_code"].iloc[0],
            "scheme_name": group["scheme_name"].iloc[0],
            "category": group["category"].iloc[0],
            "units": round(total_units, 4),
            "avg_cost": round(weighted_avg, 4) if pd.notna(weighted_avg) else pd.NA,
            "invested_amount": round(invested, 2),
            "current_nav": current_nav,
            "current_value": round(current_value, 2) if pd.notna(current_value) else pd.NA,
            "pnl": round(pnl, 2) if pd.notna(pnl) else pd.NA,
            "folios": ";".join(sorted(f for f in group["folio"].astype(str).unique() if f)),
        })

    holdings = lots.groupby("isin", dropna=False)[lots.columns].apply(_agg).reset_index()
    return holdings[HOLDINGS_COLS]


def write_snapshot(lots: pd.DataFrame, holdings: pd.DataFrame, snapshot_date: str) -> Path:
    out_dir = HOLDINGS_ROOT / snapshot_date
    out_dir.mkdir(parents=True, exist_ok=True)
    lots.to_csv(out_dir / "lots.csv", index=False)
    holdings.to_csv(out_dir / "holdings.csv", index=False)
    return out_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sync Zerodha MF holdings into project schema")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-json", help="Zerodha MCP JSON payload (file path or '-' for stdin)")
    src.add_argument("--from-manual", action="store_true",
                     help=f"Read manual fallback from {MANUAL_CSV}")
    p.add_argument("--date", default=date.today().isoformat(),
                   help="Snapshot date (defaults to today, ISO YYYY-MM-DD)")
    args = p.parse_args(argv)

    master = _load_master()
    if args.from_json:
        payload = _read_json_input(args.from_json)
        raw_lots = lots_from_zerodha(payload)
    else:
        raw_lots = lots_from_manual()

    if raw_lots.empty:
        print("No holdings rows parsed — nothing to write.", file=sys.stderr)
        return 1

    lots = enrich_with_master(raw_lots, master)
    holdings = aggregate_to_holdings(lots)
    out_dir = write_snapshot(lots, holdings, args.date)

    print(f"Wrote {len(lots)} lot(s) and {len(holdings)} aggregated holding(s) to {out_dir}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

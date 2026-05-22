"""Compute the after-tax exit plan for one or more MF positions.

Reads the latest holdings snapshot + per-fund fundamentals + optional lot dates.
Emits a per-lot exit plan with LTCG/STCG classification, exit load, and taxes.

Usage:
    python compute_rebalance.py --isin INF174K01LS2 --isin INF174K01KT2
    python compute_rebalance.py --isin INF174K01LS2 --ltcg-used-this-fy 50000
    python compute_rebalance.py --isin INF174K01LS2 --default-purchase-date 2018-04-01

See SKILL.md for the full design and tax assumptions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

HOLDINGS_ROOT = Path("data/holdings")
FUND_DIR = Path("data/fundamentals")
REBALANCE_ROOT = Path("data/rebalance")

# v1 defaults match FY 2025-26 new-regime equity rules.
DEFAULT_LTCG_RATE = 0.125
DEFAULT_LTCG_EXEMPTION = 125_000.0
DEFAULT_STCG_RATE = 0.20
DEFAULT_DEFAULT_PURCHASE_DATE = "2020-01-01"


def _latest_holdings_dir() -> Path | None:
    if not HOLDINGS_ROOT.exists():
        return None
    dated = sorted(p for p in HOLDINGS_ROOT.iterdir()
                   if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    return dated[-1] if dated else None


def _resolve_purchase_date(
    isin: str, folio: str,
    lot_dates: dict[tuple[str, str], date],
    lots_csv_date: date | None,
    default_date: date,
) -> tuple[date, str]:
    """Return (purchase_date, source-string)."""
    key = (isin, str(folio))
    if key in lot_dates:
        return lot_dates[key], "lot_dates.csv"
    if lots_csv_date is not None:
        return lots_csv_date, "lots.csv"
    return default_date, "default"


def _load_lot_dates(holdings_dir: Path) -> dict[tuple[str, str], date]:
    path = holdings_dir / "lot_dates.csv"
    if not path.exists():
        return {}
    out: dict[tuple[str, str], date] = {}
    with path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3 or parts[0].lower() == "isin":
                continue
            isin, folio, dstr = parts[0], parts[1], parts[2]
            try:
                d = datetime.strptime(dstr, "%Y-%m-%d").date()
            except ValueError:
                continue
            out[(isin, folio)] = d
    return out


def _load_fundamentals(isin: str) -> dict:
    path = FUND_DIR / f"{isin}.json"
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _exit_load_for_lot(fund: dict, holding_years: float) -> tuple[float, str]:
    """Best-effort exit-load resolution. Returns (pct, note)."""
    pct = fund.get("exit_load_pct")
    remarks = fund.get("exit_load_remarks") or ""
    if pct is None:
        return 0.0, "no exit-load data; assumed 0"
    pct = float(pct)
    # Heuristic: if held >= 1.5y AND remarks don't mention a >1Y band,
    # exit load almost certainly doesn't apply.
    if holding_years >= 1.5:
        if "after 1Y" in remarks or "Nil after 1" in remarks:
            return 0.0, f"holding >1.5Y, ladder ends: {remarks!r}"
        return 0.0, f"holding >1.5Y; remarks: {remarks!r}"
    # Held less than 1.5Y; conservatively apply headline rate.
    return pct, f"holding {holding_years:.2f}Y; remarks: {remarks!r}"


def compute_lot_plan(
    lots: pd.DataFrame,
    isins: list[str],
    lot_dates: dict[tuple[str, str], date],
    default_purchase_date: date,
    today: date,
) -> pd.DataFrame:
    """Per-lot plan for all (isin, folio) rows matching the requested isins."""
    rows = []
    targets = lots[lots["isin"].isin(isins)].copy()
    for _, lot in targets.iterrows():
        isin = lot["isin"]
        folio = str(lot.get("folio") or "")
        # Honor purchase_date from lots.csv if present.
        lots_dt = None
        if "purchase_date" in lot and pd.notna(lot.get("purchase_date")):
            try:
                lots_dt = datetime.strptime(str(lot["purchase_date"]), "%Y-%m-%d").date()
            except ValueError:
                lots_dt = None
        pdate, psource = _resolve_purchase_date(
            isin, folio, lot_dates, lots_dt, default_purchase_date
        )
        holding_years = round((today - pdate).days / 365.25, 2)
        regime = "LTCG" if holding_years >= 1.0 else "STCG"

        units = float(lot["units"])
        avg_cost = float(lot["avg_cost"])
        current_nav = float(lot.get("current_nav") or 0.0)
        gross_proceeds = round(units * current_nav, 2)

        fund = _load_fundamentals(isin)
        exit_pct, exit_note = _exit_load_for_lot(fund, holding_years)
        exit_load_rs = round(gross_proceeds * exit_pct / 100.0, 2)
        net_sale = round(gross_proceeds - exit_load_rs, 2)
        invested = round(units * avg_cost, 2)
        gain_pre_tax = round(net_sale - invested, 2)

        rows.append({
            "isin": isin,
            "scheme_name": lot.get("scheme_name") or fund.get("scheme_name"),
            "folio": folio,
            "units": round(units, 4),
            "avg_cost": round(avg_cost, 4),
            "current_nav": round(current_nav, 4),
            "purchase_date": pdate.isoformat(),
            "purchase_date_source": psource,
            "holding_years": holding_years,
            "regime": regime,
            "gross_proceeds": gross_proceeds,
            "exit_load_pct": exit_pct,
            "exit_load_rs": exit_load_rs,
            "exit_load_note": exit_note,
            "net_sale_proceeds": net_sale,
            "invested": invested,
            "gain_pre_tax": gain_pre_tax,
        })
    return pd.DataFrame(rows)


def apply_portfolio_taxes(
    lots: pd.DataFrame,
    ltcg_rate: float,
    ltcg_exemption: float,
    ltcg_used_this_fy: float,
    stcg_rate: float,
) -> tuple[pd.DataFrame, dict]:
    """Allocate taxes across lots, respecting the LTCG exemption pool.

    LTCG exemption is allocated to the LTCG lots in proportion to their gains
    (each lot's exempt portion ∝ its share of total LTCG gains). This means
    the per-lot tax_due is fair if the user only exits a subset later.
    """
    df = lots.copy()
    total_ltcg = float(df[df["regime"] == "LTCG"]["gain_pre_tax"].clip(lower=0).sum())
    total_stcg_gain_taxable = float(df[df["regime"] == "STCG"]["gain_pre_tax"].sum())
    remaining_exemption = max(0.0, ltcg_exemption - ltcg_used_this_fy)
    exempt_pool = min(total_ltcg, remaining_exemption)
    taxable_ltcg = max(0.0, total_ltcg - exempt_pool)
    ltcg_tax_total = round(ltcg_rate * taxable_ltcg, 2)
    stcg_tax_total = round(stcg_rate * max(0.0, total_stcg_gain_taxable), 2)

    # Per-lot tax allocation
    df["tax_due_this_lot"] = 0.0
    if total_ltcg > 0:
        for idx in df.index:
            if df.at[idx, "regime"] != "LTCG":
                continue
            lot_gain = max(0.0, float(df.at[idx, "gain_pre_tax"]))
            share = lot_gain / total_ltcg if total_ltcg else 0
            lot_exempt = exempt_pool * share
            lot_taxable = max(0.0, lot_gain - lot_exempt)
            df.at[idx, "tax_due_this_lot"] = round(ltcg_rate * lot_taxable, 2)
    for idx in df.index:
        if df.at[idx, "regime"] == "STCG":
            lot_gain = float(df.at[idx, "gain_pre_tax"])
            if lot_gain > 0:
                df.at[idx, "tax_due_this_lot"] = round(stcg_rate * lot_gain, 2)

    df["net_proceeds_after_tax"] = (
        df["net_sale_proceeds"] - df["tax_due_this_lot"]
    ).round(2)

    summary = {
        "total_ltcg_gain": round(total_ltcg, 2),
        "ltcg_exemption_used_pool": round(exempt_pool, 2),
        "ltcg_exemption_remaining_after_this_exit": round(
            max(0.0, remaining_exemption - exempt_pool), 2
        ),
        "ltcg_taxable": round(taxable_ltcg, 2),
        "ltcg_tax_total": ltcg_tax_total,
        "total_stcg_gain": round(total_stcg_gain_taxable, 2),
        "stcg_tax_total": stcg_tax_total,
        "total_tax_due": round(ltcg_tax_total + stcg_tax_total, 2),
        "total_invested_being_exited": round(float(df["invested"].sum()), 2),
        "total_gross_proceeds": round(float(df["gross_proceeds"].sum()), 2),
        "total_exit_load": round(float(df["exit_load_rs"].sum()), 2),
        "total_net_proceeds_after_tax": round(float(df["net_proceeds_after_tax"].sum()), 2),
    }
    return df, summary


def aggregate_summary(lots: pd.DataFrame) -> pd.DataFrame:
    """Roll up lots to one row per ISIN, plus a TOTAL row."""
    if lots.empty:
        return lots
    cols_sum = ["units", "invested", "gross_proceeds", "exit_load_rs",
                "net_sale_proceeds", "gain_pre_tax", "tax_due_this_lot",
                "net_proceeds_after_tax"]
    agg = lots.groupby(["isin", "scheme_name"], as_index=False).agg(
        {
            **{c: "sum" for c in cols_sum},
            "regime": lambda s: ",".join(sorted(set(s))),
            "folio": lambda s: ";".join(sorted(set(map(str, s)))),
        }
    )
    total_row = {
        "isin": "TOTAL", "scheme_name": "",
        "folio": "",
        "regime": "",
        **{c: round(float(agg[c].sum()), 2) for c in cols_sum},
    }
    return pd.concat([agg, pd.DataFrame([total_row])], ignore_index=True)


def write_notes(out_dir: Path, summary: dict, lots: pd.DataFrame,
                ltcg_exemption: float, ltcg_used_this_fy: float) -> None:
    """Markdown notes: harvesting hints + STCG/exit-load warnings."""
    md = [f"# Exit Plan — {date.today().isoformat()}\n"]

    md.append("## Headline\n")
    md.append(f"- **Funds being exited:** {lots['isin'].nunique()}")
    md.append(f"- **Invested being exited:** ₹{summary['total_invested_being_exited']:,.0f}")
    md.append(f"- **Gross proceeds:** ₹{summary['total_gross_proceeds']:,.0f}")
    md.append(f"- **Exit load:** ₹{summary['total_exit_load']:,.0f}")
    md.append(f"- **LTCG tax:** ₹{summary['ltcg_tax_total']:,.0f}")
    md.append(f"- **STCG tax:** ₹{summary['stcg_tax_total']:,.0f}")
    md.append(f"- **TOTAL tax:** ₹{summary['total_tax_due']:,.0f}")
    md.append(f"- **Net cash in hand:** ₹{summary['total_net_proceeds_after_tax']:,.0f}\n")

    # LTCG harvesting hint
    remaining = summary["ltcg_exemption_remaining_after_this_exit"]
    used = ltcg_used_this_fy + summary["ltcg_exemption_used_pool"]
    if remaining > 1000:
        md.append("## LTCG harvesting opportunity\n")
        md.append(
            f"FY exemption used so far: ₹{used:,.0f} of ₹{ltcg_exemption:,.0f}. "
            f"**₹{remaining:,.0f} of tax-free LTCG capacity remains** in this financial year.\n"
        )
        md.append(
            "Consider booking additional LTCG gains (from other low-conviction holdings) up to the remaining cap, "
            "then immediately repurchasing the same units to reset the cost basis. "
            "Pure tax efficiency play — costs only the bid/ask + ₹0 brokerage for direct MF.\n"
        )

    # STCG warnings
    stcg_lots = lots[lots["regime"] == "STCG"]
    if not stcg_lots.empty:
        md.append("## ⚠️ Short-term holdings being exited\n")
        md.append("Holding <1Y triggers 20% STCG (no exemption). Lots:\n")
        for _, l in stcg_lots.iterrows():
            md.append(
                f"- **{l['scheme_name']}** (folio {l['folio']}, held {l['holding_years']}Y): "
                f"₹{l['gain_pre_tax']:,.0f} STCG gain → ₹{l['tax_due_this_lot']:,.0f} tax. "
                f"Consider waiting {round(max(0, 1.0 - l['holding_years']) * 12, 1)} months to flip into LTCG."
            )
        md.append("")

    # Default-date warnings
    default_lots = lots[lots["purchase_date_source"] == "default"]
    if not default_lots.empty:
        md.append("## ⚠️ Purchase dates used the default fallback\n")
        md.append(
            "These lots have no explicit `purchase_date` in `lots.csv` or `lot_dates.csv` — "
            "the default was used. If any of these are actually <1Y old, fill in the real "
            "date at `data/holdings/<latest>/lot_dates.csv` and re-run.\n"
        )
        for _, l in default_lots.iterrows():
            md.append(f"- {l['scheme_name']}  (folio {l['folio']})")
        md.append("")

    # Exit-load remarks worth reviewing
    exit_lots = lots[lots["exit_load_rs"] > 0]
    if not exit_lots.empty:
        md.append("## Exit-load notes\n")
        for _, l in exit_lots.iterrows():
            md.append(
                f"- **{l['scheme_name']}** (folio {l['folio']}): "
                f"₹{l['exit_load_rs']:,.0f} ({l['exit_load_pct']}% on ₹{l['gross_proceeds']:,.0f}). "
                f"Remarks: {l['exit_load_note']}"
            )

    (out_dir / "exit_plan_notes.md").write_text("\n".join(md) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute after-tax exit plan for MF positions")
    p.add_argument("--isin", action="append", default=[], required=False,
                   help="ISIN(s) to exit (repeatable)")
    p.add_argument("--ltcg-rate", type=float, default=DEFAULT_LTCG_RATE)
    p.add_argument("--ltcg-exemption", type=float, default=DEFAULT_LTCG_EXEMPTION)
    p.add_argument("--ltcg-used-this-fy", type=float, default=0.0,
                   help="Rs of FY LTCG exemption already consumed (defaults 0)")
    p.add_argument("--stcg-rate", type=float, default=DEFAULT_STCG_RATE)
    p.add_argument("--default-purchase-date", type=str,
                   default=DEFAULT_DEFAULT_PURCHASE_DATE,
                   help="Used when no lot date is supplied (YYYY-MM-DD)")
    p.add_argument("--date", default=date.today().isoformat(),
                   help="Output snapshot date (default: today)")
    args = p.parse_args(argv)

    if not args.isin:
        print("No --isin provided. Pass at least one --isin to specify what to exit.",
              file=sys.stderr)
        return 1

    today = date.today()
    try:
        default_date = datetime.strptime(args.default_purchase_date, "%Y-%m-%d").date()
    except ValueError:
        sys.exit(f"Bad --default-purchase-date: {args.default_purchase_date!r} (need YYYY-MM-DD)")
    if default_date > today:
        sys.exit(f"--default-purchase-date {default_date} is in the future")

    holdings_dir = _latest_holdings_dir()
    if not holdings_dir:
        sys.exit("No holdings snapshot found. Run zerodha-portfolio-sync first.")
    lots_path = holdings_dir / "lots.csv"
    if not lots_path.exists():
        sys.exit(f"{lots_path} missing.")

    lots = pd.read_csv(lots_path, dtype={"isin": str, "scheme_code": str, "folio": str})
    lot_dates = _load_lot_dates(holdings_dir)

    out_dir = REBALANCE_ROOT / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    lots_plan = compute_lot_plan(lots, args.isin, lot_dates, default_date, today)
    if lots_plan.empty:
        sys.exit(f"No matching lots found for ISIN(s) {args.isin} in {lots_path}")

    lots_plan, summary = apply_portfolio_taxes(
        lots_plan, args.ltcg_rate, args.ltcg_exemption,
        args.ltcg_used_this_fy, args.stcg_rate
    )

    # Write outputs
    lots_plan.to_csv(out_dir / "exit_plan_lots.csv", index=False)
    aggregate_summary(lots_plan).to_csv(out_dir / "exit_plan_summary.csv", index=False)
    write_notes(out_dir, summary, lots_plan, args.ltcg_exemption, args.ltcg_used_this_fy)

    print(
        f"\nExit plan written to {out_dir}/",
        f"  lots:    {len(lots_plan)} rows",
        f"  invested:  ₹{summary['total_invested_being_exited']:>12,.0f}",
        f"  gross:     ₹{summary['total_gross_proceeds']:>12,.0f}",
        f"  exit load: ₹{summary['total_exit_load']:>12,.0f}",
        f"  LTCG tax:  ₹{summary['ltcg_tax_total']:>12,.0f}  "
        f"(taxable: ₹{summary['ltcg_taxable']:,.0f}, exemption pool: ₹{summary['ltcg_exemption_used_pool']:,.0f})",
        f"  STCG tax:  ₹{summary['stcg_tax_total']:>12,.0f}",
        f"  NET CASH:  ₹{summary['total_net_proceeds_after_tax']:>12,.0f}",
        sep="\n", file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

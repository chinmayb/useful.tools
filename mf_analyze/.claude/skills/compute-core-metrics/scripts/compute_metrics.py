"""Compute the per-fund core metrics for the current portfolio.

Reads the latest holdings snapshot, the per-fund NAV cache, and the per-benchmark
TRI cache; emits one wide row per in-scope fund.

Writes:
    data/metrics/<YYYY-MM-DD>/per_fund_metrics.csv
    data/metrics/<YYYY-MM-DD>/_errors.jsonl  (only on failure)

Usage:
    python compute_metrics.py                            # latest snapshot
    python compute_metrics.py --risk-free 0.065          # custom risk-free
    python compute_metrics.py --holdings data/holdings/2026-05-22/holdings.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# Allow importing benchmark resolver from sibling skill.
THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(THIS_DIR.parent.parent / "benchmark-mapper" / "scripts"))

from lib_metrics import compute_all_metrics  # noqa: E402
from refresh_all_benchmarks import resolve_benchmark  # noqa: E402
from fetch_tri import index_slug  # noqa: E402

HOLDINGS_ROOT = Path("data/holdings")
NAV_DIR = Path("data/nav")
BENCH_DIR = Path("data/benchmarks")
METRICS_ROOT = Path("data/metrics")

OUTPUT_COLS = [
    "isin", "scheme_code", "scheme_name", "category", "benchmark",
    "sortino_5y",
    "rolling_alpha_3y_median", "rolling_alpha_3y_recent", "beat_pct_3y", "n_rolling_windows",
    "max_drawdown_pct", "max_drawdown_date", "recovery_months",
    "downside_capture_5y", "beta_5y",
    "fund_age_years", "lookback_warnings",
]


def _latest_holdings_snapshot() -> Path | None:
    if not HOLDINGS_ROOT.exists():
        return None
    dated = sorted(p for p in HOLDINGS_ROOT.iterdir()
                   if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    if not dated:
        return None
    return dated[-1] / "holdings.csv"


def _log_error(out_dir: Path, isin: str, error: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "isin": isin,
        "error": error,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
    with (out_dir / "_errors.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def compute_for_holdings(
    holdings: pd.DataFrame,
    out_dir: Path,
    risk_free_annual: float = 0.07,
) -> pd.DataFrame:
    rows = []
    for _, h in holdings.iterrows():
        isin = h.get("isin", "")
        scheme_code = str(h.get("scheme_code", ""))
        scheme_name = h.get("scheme_name", "")
        category = h.get("category", "")

        benchmark = resolve_benchmark(category, scheme_name)
        if benchmark is None:
            print(f"[skip] out of v1 scope: {scheme_name[:55]}  [{category}]",
                  file=sys.stderr)
            continue

        nav_path = NAV_DIR / f"{scheme_code}.csv"
        tri_path = BENCH_DIR / f"{index_slug(benchmark)}.csv"

        if not nav_path.exists():
            _log_error(out_dir, isin, f"NAV cache missing: {nav_path}")
            print(f"[error] NAV missing for {scheme_name[:55]}", file=sys.stderr)
            continue
        if not tri_path.exists():
            _log_error(out_dir, isin, f"TRI cache missing: {tri_path}")
            print(f"[error] TRI missing for {scheme_name[:55]} ({benchmark})",
                  file=sys.stderr)
            continue

        try:
            nav = pd.read_csv(nav_path)
            tri = pd.read_csv(tri_path)
            metrics = compute_all_metrics(nav, tri, risk_free_annual=risk_free_annual)
        except Exception as e:
            _log_error(out_dir, isin, f"compute failed: {e}")
            print(f"[error] compute failed for {scheme_name[:55]}: {e}", file=sys.stderr)
            continue

        row = {
            "isin": isin,
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "category": category,
            "benchmark": benchmark,
            **metrics,
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLS)
    return pd.DataFrame(rows)[OUTPUT_COLS]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compute core metrics for the current portfolio")
    p.add_argument("--holdings", type=Path,
                   help="Path to holdings.csv (default: latest snapshot)")
    p.add_argument("--risk-free", type=float, default=0.07,
                   help="Annual risk-free rate, decimal (default: 0.07 = 7%%)")
    p.add_argument("--date", default=date.today().isoformat(),
                   help="Output snapshot date (default: today, ISO YYYY-MM-DD)")
    args = p.parse_args(argv)

    holdings_path = args.holdings or _latest_holdings_snapshot()
    if not holdings_path or not holdings_path.exists():
        print("No holdings snapshot found. Run zerodha-portfolio-sync first.",
              file=sys.stderr)
        return 1
    print(f"Reading holdings from {holdings_path}", file=sys.stderr)
    holdings = pd.read_csv(holdings_path, dtype={"scheme_code": str, "isin": str})

    out_dir = METRICS_ROOT / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = compute_for_holdings(holdings, out_dir, risk_free_annual=args.risk_free)
    out_path = out_dir / "per_fund_metrics.csv"
    metrics.to_csv(out_path, index=False)
    print(f"\nWrote {len(metrics)} fund metric row(s) to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

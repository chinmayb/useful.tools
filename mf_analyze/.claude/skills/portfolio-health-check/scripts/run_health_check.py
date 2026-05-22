"""Portfolio health check — one-command orchestrator.

Runs every refresh + analysis stage in sequence, then writes a single
synthesized markdown report at data/reports/<date>/portfolio_health.md.

Each stage is delegated to its own skill via subprocess so this orchestrator
remains a thin coordinator. Stages are fail-soft: a failure in one stage
logs the error but does NOT abort the rest of the run.

Usage:
    python run_health_check.py
    python run_health_check.py --skip-fundamentals --skip-tri
    python run_health_check.py --rebalance-isin INF174K01LS2 --rebalance-isin INF174K01KT2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(THIS_DIR))
from lib_report import (  # noqa: E402
    render_headline,
    render_allocation,
    render_per_fund_scorecard,
    render_sell_candidates,
    render_redundancy_map,
    render_out_of_scope,
    render_refresh_status,
)

REPO_ROOT = Path.cwd()
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
PY = REPO_ROOT / ".venv" / "bin" / "python"
HOLDINGS_ROOT = REPO_ROOT / "data" / "holdings"
METRICS_ROOT = REPO_ROOT / "data" / "metrics"
OVERLAP_ROOT = REPO_ROOT / "data" / "overlap"
REBALANCE_ROOT = REPO_ROOT / "data" / "rebalance"
FUND_DIR = REPO_ROOT / "data" / "fundamentals"
REPORTS_ROOT = REPO_ROOT / "data" / "reports"

# Same as compute-core-metrics + portfolio-overlap-analyzer
EQUITY_CATEGORIES = {
    "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
    "Flexi Cap", "Multi Cap", "ELSS", "Focused", "Value", "Contra",
    "Dividend Yield", "Sectoral/Thematic", "Index Funds",
}


def _run_stage(name: str, cmd: list[str]) -> tuple[str, str]:
    """Run a stage. Returns (status, error_message)."""
    print(f"\n=== Stage: {name} ===", file=sys.stderr)
    print(f"$ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, check=False, cwd=str(REPO_ROOT))
        elapsed = time.time() - t0
        if r.returncode == 0:
            print(f"  ✓ {name} ({elapsed:.1f}s)", file=sys.stderr)
            return "ok", ""
        else:
            print(f"  ✗ {name} exited {r.returncode}", file=sys.stderr)
            return "failed", f"exit code {r.returncode}"
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ {name} raised: {e}", file=sys.stderr)
        return "failed", str(e)


def _latest_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    dated = sorted(p for p in root.iterdir()
                   if p.is_dir() and len(p.name) >= 10 and p.name[4] == "-")
    return dated[-1] if dated else None


def _load_holdings() -> pd.DataFrame:
    d = _latest_dir(HOLDINGS_ROOT)
    if d is None:
        sys.exit("No holdings snapshot. Run zerodha-portfolio-sync first.")
    path = d / "holdings.csv"
    if not path.exists():
        sys.exit(f"{path} missing.")
    return pd.read_csv(path, dtype={"isin": str, "scheme_code": str})


def _load_metrics() -> pd.DataFrame | None:
    d = _latest_dir(METRICS_ROOT)
    if d is None:
        return None
    path = d / "per_fund_metrics.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"isin": str, "scheme_code": str})


def _load_overlap() -> pd.DataFrame | None:
    d = _latest_dir(OVERLAP_ROOT)
    if d is None:
        return None
    path = d / "pairs_ranked.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"isin_a": str, "isin_b": str})


def _load_fundamentals_by_isin() -> dict[str, dict]:
    out = {}
    if not FUND_DIR.exists():
        return out
    for f in FUND_DIR.glob("INF*.json"):
        if ".manual." in f.name:
            continue
        try:
            with f.open() as fh:
                d = json.load(fh)
                if d.get("isin"):
                    out[d["isin"]] = d
        except Exception:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portfolio health check orchestrator")
    p.add_argument("--skip-nav", action="store_true")
    p.add_argument("--skip-tri", action="store_true")
    p.add_argument("--skip-fundamentals", action="store_true")
    p.add_argument("--skip-metrics", action="store_true")
    p.add_argument("--skip-overlap", action="store_true")
    p.add_argument("--rebalance-isin", action="append", default=[],
                   help="ISIN(s) to include in the tax-aware exit plan (repeatable)")
    p.add_argument("--ltcg-used-this-fy", type=float, default=0.0)
    p.add_argument("--risk-free", type=float, default=0.07)
    p.add_argument("--date", default=date.today().isoformat())
    args = p.parse_args(argv)

    if not PY.exists():
        sys.exit(f"Project venv missing at {PY}. Activate the env before running.")

    stage_status: dict[str, str] = {}
    stage_errors: dict[str, str] = {}

    # --- Stage 1: NAV refresh
    if args.skip_nav:
        stage_status["nav"] = "skipped"
    else:
        s, e = _run_stage(
            "fetch-nav-history",
            [str(PY), str(SKILLS_ROOT / "fetch-nav-history" / "scripts" / "fetch_nav.py"),
             "--portfolio"],
        )
        stage_status["nav"], stage_errors["nav"] = s, e

    # --- Stage 2: TRI refresh
    if args.skip_tri:
        stage_status["tri"] = "skipped"
    else:
        s, e = _run_stage(
            "benchmark-mapper",
            [str(PY), str(SKILLS_ROOT / "benchmark-mapper" / "scripts" / "refresh_all_benchmarks.py")],
        )
        stage_status["tri"], stage_errors["tri"] = s, e

    # --- Stage 3: Fundamentals refresh
    if args.skip_fundamentals:
        stage_status["fundamentals"] = "skipped"
    else:
        s, e = _run_stage(
            "scrape-fund-fundamentals",
            [str(PY),
             str(SKILLS_ROOT / "scrape-fund-fundamentals" / "scripts" / "scrape_tickertape.py"),
             "--portfolio"],
        )
        stage_status["fundamentals"], stage_errors["fundamentals"] = s, e

    # --- Stage 4: Metrics
    if args.skip_metrics:
        stage_status["metrics"] = "skipped"
    else:
        s, e = _run_stage(
            "compute-core-metrics",
            [str(PY),
             str(SKILLS_ROOT / "compute-core-metrics" / "scripts" / "compute_metrics.py"),
             "--risk-free", str(args.risk_free),
             "--date", args.date],
        )
        stage_status["metrics"], stage_errors["metrics"] = s, e

    # --- Stage 5: Overlap
    if args.skip_overlap:
        stage_status["overlap"] = "skipped"
    else:
        s, e = _run_stage(
            "portfolio-overlap-analyzer",
            [str(PY),
             str(SKILLS_ROOT / "portfolio-overlap-analyzer" / "scripts" / "compute_overlap.py"),
             "--date", args.date],
        )
        stage_status["overlap"], stage_errors["overlap"] = s, e

    # --- Stage 6: Tax-aware rebalance (conditional)
    rebalance_notes = ""
    if args.rebalance_isin:
        cmd = [
            str(PY),
            str(SKILLS_ROOT / "tax-aware-rebalancer" / "scripts" / "compute_rebalance.py"),
            "--ltcg-used-this-fy", str(args.ltcg_used_this_fy),
            "--date", args.date,
        ]
        for isin in args.rebalance_isin:
            cmd.extend(["--isin", isin])
        s, e = _run_stage("tax-aware-rebalancer", cmd)
        stage_status["rebalance"], stage_errors["rebalance"] = s, e
        if s == "ok":
            notes_path = REBALANCE_ROOT / args.date / "exit_plan_notes.md"
            if notes_path.exists():
                rebalance_notes = notes_path.read_text()
    else:
        stage_status["rebalance"] = "not requested"

    # --- Stage 7: Synthesize report
    print("\n=== Stage: synthesize report ===", file=sys.stderr)
    holdings = _load_holdings()
    metrics = _load_metrics()
    overlap = _load_overlap()
    fundamentals_by_isin = _load_fundamentals_by_isin()

    sections = [
        render_headline(holdings, args.date, stage_status),
        render_allocation(holdings),
        render_per_fund_scorecard(holdings, metrics, fundamentals_by_isin),
        render_sell_candidates(holdings, metrics, overlap, fundamentals_by_isin),
        render_redundancy_map(overlap),
    ]

    if rebalance_notes:
        # Drop the rebalance notes' own H1 (we'll add our own H2),
        # then demote everything else one level (## → ###).
        lines = ["## Tax-aware exit plan"]
        for ln in rebalance_notes.splitlines():
            if ln.startswith("# "):
                continue  # drop the file's own title
            if ln.startswith("## "):
                lines.append("###" + ln[2:])
            else:
                lines.append(ln)
        sections.append("\n".join(lines) + "\n")

    sections.append(render_out_of_scope(holdings, EQUITY_CATEGORIES))
    sections.append(render_refresh_status(stage_status, stage_errors))

    out_dir = REPORTS_ROOT / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "portfolio_health.md"
    out_path.write_text("\n".join(sections))
    print(f"  ✓ wrote {out_path}", file=sys.stderr)

    failed = [k for k, v in stage_status.items() if v == "failed"]
    if failed:
        print(f"\nReport written, but these stages failed: {failed}", file=sys.stderr)
        return 1
    print(f"\nReport written to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

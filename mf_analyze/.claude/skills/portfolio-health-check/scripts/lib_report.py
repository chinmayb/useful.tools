"""Markdown rendering helpers for portfolio-health-check.

Pure functions — take DataFrames and return strings. No I/O.
"""

from __future__ import annotations

import pandas as pd


def rupees(x: float | None, *, signed: bool = False) -> str:
    """Format a rupee amount with Indian-style grouping (lakh/crore)."""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    sign = ""
    if signed and x > 0:
        sign = "+"
    if signed and x < 0:
        sign = ""  # negative sign comes from the number
    if abs(x) >= 1e7:
        return f"{sign}₹{x / 1e7:,.2f} Cr"
    if abs(x) >= 1e5:
        return f"{sign}₹{x / 1e5:,.2f} L"
    return f"{sign}₹{x:,.0f}"


def pct(x: float | None, decimals: int = 1) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x * 100:+.{decimals}f}%" if x else "0.0%"


def num(x: float | None, decimals: int = 2) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:.{decimals}f}"


def ascii_bar(value: float, width: int = 20, *, max_value: float = 100.0) -> str:
    """Simple monospace bar (uses block characters). value as 0..max_value."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    filled = int(round(width * min(max(value, 0), max_value) / max_value))
    return "█" * filled + "░" * (width - filled)


def md_table(headers: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    """Build a GitHub-flavored markdown table."""
    if align is None:
        align = ["left"] * len(headers)
    sep_map = {"left": ":---", "center": ":---:", "right": "---:"}
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(sep_map.get(a, "---") for a in align) + " |")
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_headline(holdings: pd.DataFrame, today: str, stage_status: dict[str, str]) -> str:
    invested = float(holdings["invested_amount"].sum())
    current = float(holdings["current_value"].sum())
    pnl = current - invested
    ret = pnl / invested if invested else 0.0
    fund_count = len(holdings)

    md = [f"# Portfolio Health Check — {today}\n"]
    md.append(f"- **Funds tracked:** {fund_count}")
    md.append(f"- **Invested:** {rupees(invested)}")
    md.append(f"- **Current value:** {rupees(current)}")
    md.append(f"- **P&L:** {rupees(pnl)}  ({pct(ret)})")
    md.append("")
    md.append(
        "_Stages this run: "
        + ", ".join(f"{k} ({v})" for k, v in stage_status.items())
        + "_\n"
    )
    return "\n".join(md)


def render_allocation(holdings: pd.DataFrame) -> str:
    agg = holdings.groupby("category", dropna=False).agg(
        funds=("isin", "count"),
        invested=("invested_amount", "sum"),
        current=("current_value", "sum"),
    )
    total_current = agg["current"].sum()
    agg["alloc_pct"] = agg["current"] / total_current * 100
    agg = agg.sort_values("current", ascending=False)

    md = ["## Allocation by category\n"]
    rows = []
    for cat, r in agg.iterrows():
        rows.append([
            cat or "(uncategorized)",
            int(r["funds"]),
            rupees(r["invested"]),
            rupees(r["current"]),
            f"{r['alloc_pct']:.1f}%",
            ascii_bar(r["alloc_pct"], width=18, max_value=agg["alloc_pct"].max()),
        ])
    md.append(md_table(
        ["Category", "#", "Invested", "Current", "Alloc %", ""],
        rows,
        align=["left", "right", "right", "right", "right", "left"],
    ))
    md.append("")
    return "\n".join(md)


def render_per_fund_scorecard(
    holdings: pd.DataFrame,
    metrics: pd.DataFrame | None,
    fundamentals_by_isin: dict[str, dict],
) -> str:
    """Wide table joining holdings × metrics × Tickertape signals."""
    md = ["## Per-fund scorecard\n"]
    md.append("Columns: our metrics (left) and Tickertape's (right). Sorted by current value.\n")

    h = holdings.sort_values("current_value", ascending=False).copy()
    metrics_by_isin = (
        {r["isin"]: r.to_dict() for _, r in metrics.iterrows()}
        if metrics is not None else {}
    )

    rows = []
    for _, hh in h.iterrows():
        isin = hh["isin"]
        m = metrics_by_isin.get(isin) or {}
        f = fundamentals_by_isin.get(isin) or {}
        sc = {s.get("name"): s for s in (f.get("scorecard") or [])}
        perf = sc.get("Performance") or {}
        risk = sc.get("Risk") or {}
        exp = f.get("expense_ratio_pct")
        rows.append([
            (hh.get("scheme_name") or "")[:36],
            (hh.get("category") or "")[:18],
            rupees(hh.get("current_value")),
            num(m.get("sortino_5y"), 2),
            pct(m.get("rolling_alpha_3y_median")),
            pct(m.get("beat_pct_3y"), 0),
            pct(m.get("max_drawdown_pct")),
            num(perf.get("score"), 1),
            num(risk.get("score"), 1),
            f"{exp:.2f}%" if exp is not None else "—",
            ((f.get("managers") or [{}])[0].get("name") or "")[:16],
        ])

    md.append(md_table(
        [
            "Fund", "Category", "Value",
            "Sortino", "α 3Y", "Beat %", "Max DD",
            "TT Perf", "TT Risk",
            "Exp", "Manager",
        ],
        rows,
        align=["left", "left", "right",
               "right", "right", "right", "right",
               "right", "right",
               "right", "left"],
    ))
    md.append("")
    return "\n".join(md)


def render_sell_candidates(
    holdings: pd.DataFrame,
    metrics: pd.DataFrame | None,
    overlap_pairs: pd.DataFrame | None,
    fundamentals_by_isin: dict[str, dict],
) -> str:
    """Find funds that look weak on metrics AND duplicate exposure."""
    md = ["## Sell candidates\n"]
    if metrics is None or metrics.empty:
        md.append("_No metrics available — run the metrics stage first._\n")
        return "\n".join(md)

    # 1. Negative-alpha + sub-50% beat-% on ACTIVE funds only.
    # Index funds are benchmarked to themselves — they lose by expense ratio
    # by construction, so "negative alpha" and "0% beat" are not sell signals.
    candidates: dict[str, list[str]] = {}
    for _, m in metrics.iterrows():
        isin = m["isin"]
        if (m.get("category") or "") == "Index Funds":
            continue
        reasons = []
        alpha = m.get("rolling_alpha_3y_median")
        beat = m.get("beat_pct_3y")
        if alpha is not None and alpha == alpha and alpha < 0:
            reasons.append(f"3Y alpha {pct(alpha)} (negative)")
        if beat is not None and beat == beat and beat < 0.5:
            reasons.append(f"beat-% {pct(beat, 0)} (under half)")
        if reasons:
            candidates[isin] = reasons

    # Enrich with overlap-flagged pairs
    if overlap_pairs is not None and not overlap_pairs.empty:
        flagged = overlap_pairs[overlap_pairs["redundant_flag"] == True]
        for _, p in flagged.iterrows():
            for isin_field in ("isin_a", "isin_b"):
                isin = p[isin_field]
                other = p["isin_b"] if isin_field == "isin_a" else p["isin_a"]
                other_name = p["name_b"] if isin_field == "isin_a" else p["name_a"]
                if isin in candidates:
                    candidates[isin].append(
                        f"redundant with {other_name[:30]!r} "
                        f"(corr={p['return_corr_5y']:.2f}, stk Jaccard={p['stock_jaccard']:.2f})"
                    )

    if not candidates:
        md.append("_No funds met the sell-candidate criteria (negative 3Y alpha + sub-50% beat-%)._\n")
        return "\n".join(md)

    # Render one paragraph per candidate
    name_by_isin = dict(zip(holdings["isin"], holdings["scheme_name"]))
    value_by_isin = dict(zip(holdings["isin"], holdings["current_value"]))
    for isin, reasons in candidates.items():
        name = name_by_isin.get(isin, isin)
        val = value_by_isin.get(isin)
        md.append(f"### {name}")
        md.append(f"  ISIN `{isin}` · current value {rupees(val)}\n")
        for r in reasons:
            md.append(f"- {r}")
        md.append("")

    return "\n".join(md)


def render_redundancy_map(overlap_pairs: pd.DataFrame | None) -> str:
    md = ["## Redundancy map (top 5 pairs)\n"]
    if overlap_pairs is None or overlap_pairs.empty:
        md.append("_No overlap data — run the overlap stage first._\n")
        return "\n".join(md)

    top = overlap_pairs.sort_values("redundancy_score", ascending=False).head(5)
    rows = []
    for _, p in top.iterrows():
        flag = "🚩" if p.get("redundant_flag") else ""
        rows.append([
            (p["name_a"] or "")[:28],
            (p["name_b"] or "")[:28],
            num(p.get("stock_jaccard"), 2),
            num(p.get("sector_cosine"), 2),
            num(p.get("return_corr_5y"), 2),
            num(p.get("redundancy_score"), 2),
            flag,
        ])
    md.append(md_table(
        ["Fund A", "Fund B", "Stk Jaccard", "Sec cos", "Ret corr 5Y", "Score", ""],
        rows,
        align=["left", "left", "right", "right", "right", "right", "center"],
    ))
    md.append("")
    md.append("_Flag fires when all of: stock Jaccard ≥ 0.30, sector cosine ≥ 0.85, return corr ≥ 0.90._\n")
    return "\n".join(md)


def render_out_of_scope(holdings: pd.DataFrame, in_scope_categories: set[str]) -> str:
    out = holdings[~holdings["category"].isin(in_scope_categories)]
    if out.empty:
        return ""
    md = ["## Out of v1 scope (not analyzed)\n"]
    md.append("These funds are skipped by `compute-core-metrics` and `portfolio-overlap-analyzer` because v1 is equity-only. Listed here for transparency.\n")
    rows = []
    for _, h in out.iterrows():
        rows.append([
            (h["scheme_name"] or "")[:42],
            (h["category"] or "")[:30],
            rupees(h["current_value"]),
            pct((h["current_value"] - h["invested_amount"]) / h["invested_amount"] if h["invested_amount"] else None),
        ])
    md.append(md_table(
        ["Fund", "Category", "Current value", "Return"],
        rows,
        align=["left", "left", "right", "right"],
    ))
    md.append("")
    return "\n".join(md)


def render_rebalance_section(rebalance_notes_path) -> str:
    """Inline the markdown notes from tax-aware-rebalancer."""
    from pathlib import Path
    p = Path(rebalance_notes_path)
    if not p.exists():
        return ""
    body = p.read_text()
    # The rebalance notes file starts with its own H1 — demote everything one level.
    demoted = body.replace("\n# ", "\n## ").replace("\n## ", "\n### ", 1)
    if demoted.startswith("# "):
        demoted = "## Tax-aware exit plan\n\n### " + demoted[len("# "):]
    md = ["## Tax-aware exit plan\n", body.split("\n", 1)[1] if body.startswith("# ") else body]
    return "\n".join(md)


def render_refresh_status(stage_status: dict[str, str], errors: dict[str, str]) -> str:
    md = ["## Refresh status\n"]
    rows = []
    for stage, status in stage_status.items():
        err = errors.get(stage, "")
        rows.append([stage, status, err[:80] if err else ""])
    md.append(md_table(["Stage", "Status", "Error"], rows))
    md.append("")
    return "\n".join(md)

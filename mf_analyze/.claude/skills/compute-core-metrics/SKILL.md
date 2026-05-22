---
name: compute-core-metrics
description: Computes the six benchmark-relative metrics that drive consolidation decisions for an Indian MF portfolio — Sortino ratio, rolling 3Y alpha (annualized excess return), max drawdown + recovery, downside capture, rolling 3Y beat-%, and beta. Reads cached NAVs and TRIs; emits one wide row per fund at data/metrics/<date>/per_fund_metrics.csv. Use whenever scoring funds, comparing performance vs benchmark, or refreshing the metrics that feed the consolidation decision. Don't use for debt or hybrid funds in v1.
---

# Compute Core Metrics

This is the **headline-value skill** for v1. Every consolidation decision flows from its output.

## When to use

- Refreshing the per-fund score sheet (typically after NAVs and TRIs have been re-cached).
- The user wants to know "is this fund worth keeping" or "which of these two funds should I drop".
- Updating the metrics section of the analysis notebook.

## When NOT to use

- For funds outside v1 scope (debt, hybrid, FoF Overseas, commodity FoF) — these are skipped automatically with a notice.
- When NAV or TRI cache is empty/stale for a fund — run `fetch-nav-history` and `benchmark-mapper` first.

## The six metrics

Defined in `CLAUDE.md` § "Core Metrics (v1)". Computed at the **monthly** frequency from end-of-month NAV (industry standard for MF analytics — less noise than daily, captures the same information).

| Metric | Lookback | Formula |
|---|---|---|
| **Sortino ratio** | 5Y | `(R_fund_annualized - R_target) / downside_std_annualized` |
| **Rolling 3Y alpha** | 7Y | median of (3Y fund CAGR − 3Y benchmark CAGR) across all monthly-stepped windows |
| **Max drawdown** | all available | min((NAV / running_max) − 1) |
| **Recovery months** | all available | months from trough back to peak; `null` if not yet recovered |
| **Downside capture** | 5Y | Σ R_fund on (R_bench < 0) months ÷ Σ R_bench on (R_bench < 0) months |
| **Rolling 3Y beat-%** | 7Y | % of monthly-stepped 3Y windows where fund CAGR > bench CAGR |

Plus three context columns:

- **Beta (5Y, monthly):** covariance(R_fund, R_bench) / variance(R_bench). Cheap to compute; useful when interpreting alpha.
- **Fund age years:** how long the fund has existed. Short funds get a warning.
- **Lookback warnings:** comma-separated string like `"sortino_lookback_clamped_to_3.1y;rolling_alpha_skipped_<3y"`.

## Inputs (read from disk)

| Path | Skill that writes it |
|---|---|
| `data/holdings/<latest>/holdings.csv` | zerodha-portfolio-sync |
| `data/nav/<scheme_code>.csv` | fetch-nav-history |
| `data/benchmarks/<slug>.csv` | benchmark-mapper |
| `data/amfi_scheme_master.csv` | fetch-nav-history |

## Procedure

### Step 1 — Load the holdings snapshot

Read the latest `data/holdings/<YYYY-MM-DD>/holdings.csv`. For each fund, decide whether it's in v1 scope using the same `EQUITY_CATEGORIES` set as `benchmark-mapper`. Out-of-scope rows are logged and skipped.

### Step 2 — Resolve benchmark per fund

Import `resolve_benchmark()` from `.claude/skills/benchmark-mapper/scripts/refresh_all_benchmarks.py` (single source of truth — don't duplicate the rules). Returns the niftyindices `name`, e.g., `NIFTY 500`. The corresponding TRI CSV is at `data/benchmarks/<slug>.csv` where `slug = name.lower().replace(" ", "_").replace(":", "_")`.

If the TRI is missing, log and skip the fund. Caller can re-run `benchmark-mapper` and retry.

### Step 3 — Load and align price series

For each fund:
1. Load NAV from `data/nav/<scheme_code>.csv` → end-of-month NAV → monthly returns.
2. Load TRI from `data/benchmarks/<slug>.csv` → end-of-month value → monthly returns.
3. Inner-join on month-end date. Drop any month where either side is missing.

The aligned monthly-returns DataFrame is the substrate for all metrics.

### Step 4 — Compute the six metrics

Implementation lives in `scripts/compute_metrics.py`. Functions:

- `sortino(returns, target_annual=0.07)` — uses downside-deviation (only negative-vs-target months contribute to the denominator). Annualized by `* sqrt(12)`.
- `max_drawdown_and_recovery(nav_series)` — returns `(mdd_pct, peak_date, trough_date, recovery_date_or_None)`. Recovery months = months between trough and recovery; `None` if not yet recovered.
- `rolling_3y_alpha_and_beat(fund_ret, bench_ret)` — monthly-stepped 3Y (36-month) windows; emits `median_alpha`, `recent_alpha`, `beat_pct`.
- `downside_capture(fund_ret, bench_ret)` — uses the standard ratio-of-sums definition.
- `beta(fund_ret, bench_ret)` — covariance / variance of monthly returns over the trailing 5Y.

### Step 5 — Emit `per_fund_metrics.csv`

One row per in-scope fund, schema:

```
isin, scheme_code, scheme_name, category, benchmark,
sortino_5y,
rolling_alpha_3y_median, rolling_alpha_3y_recent, beat_pct_3y,
max_drawdown_pct, max_drawdown_date, recovery_months,
downside_capture_5y, beta_5y,
fund_age_years, lookback_warnings
```

All percentage metrics expressed as decimals (0.45 = 45%) — formatting belongs to the notebook layer.

## Output

- **Files written:** `data/metrics/<YYYY-MM-DD>/per_fund_metrics.csv`.
- **Returned:** the DataFrame (same shape as the CSV).
- **Failure summary:** `data/metrics/<YYYY-MM-DD>/_errors.jsonl` if any fund failed.

## Caching

No internal cache — the inputs (NAV, TRI) are already cached by upstream skills. This skill is fast (<2 seconds for 10 funds, all pandas).

## Lookback Convention (from CLAUDE.md)

| Metric | Default lookback |
|---|---|
| Max drawdown, recovery | all available |
| Sortino, downside capture, beta | 5Y |
| Rolling 3Y alpha, beat-% | 7Y |

For funds with shorter history:
- Sortino/downside-capture: compute on available history, warn if `<5Y`.
- Rolling 3Y metrics: skip entirely if fund has `<3Y` of monthly returns. Warn.
- Max drawdown: always compute, however much history exists.

These conventions are encoded in `compute_metrics.py`'s `_clamp_lookback()` helper and surfaced via the `lookback_warnings` column.

## Error Handling

- **Missing NAV CSV:** log per-fund, skip. Caller re-runs `fetch-nav-history`.
- **Missing TRI CSV:** log per-fund, skip. Caller re-runs `benchmark-mapper`.
- **Fewer than 12 aligned months:** skip with warning. Anything less than a year of overlap is uninformative.
- **All-zero downside months for capture ratio:** rare — would mean benchmark never declined. Emit `inf` or `null` rather than divide-by-zero; downstream notebook handles display.

## Bundled Scripts

- `scripts/compute_metrics.py` — main script.
- `scripts/lib_metrics.py` — pure-function metric implementations (testable in isolation).

## Bundled References

- `references/formula_choices.md` — Why each formula was chosen over its alternatives (Sharpe vs Sortino, simple alpha vs Jensen's, etc.). Read before changing any formula.

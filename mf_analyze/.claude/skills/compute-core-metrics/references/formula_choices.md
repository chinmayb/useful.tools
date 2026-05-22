# Formula Choices

Why each metric is computed the way it is, in case future-you wants to change one.

## Sortino over Sharpe

Sharpe penalizes upside volatility (it's in the denominator). For equity mutual funds — which have positively-skewed returns and where investors don't actually mind upside swings — that's a meaningless penalty.

Sortino uses **downside deviation** (std of returns below the target rate) instead. Better aligns with how investors think about risk: "how much do I lose when things go wrong?"

Target return = the risk-free rate (default 7% pa in INR, current 10Y G-Sec ballpark). Configurable via `--risk-free`.

Annualization: monthly Sortino × √12. Standard convention.

## Simple excess-return alpha over Jensen's CAPM alpha

Jensen's alpha adjusts for the fund's beta: `α = R_f - (R_f + β × (R_b - R_f))`.

For 95% of Indian MF cases, β is in `[0.85, 1.15]`. The CAPM adjustment moves the alpha number by `(β - 1) × equity-risk-premium` — typically ±50 bps. Not worth the interpretive complexity for retail consolidation decisions.

We compute β separately as a side metric. If a fund has unusual beta (`<0.7` or `>1.3`), the analyst can interpret alpha with that context. For most decisions, **simple annualized excess return is what the user actually wants** to see.

## Rolling 3Y windows, monthly step

A single 3Y point estimate is noisy — a fund can look great or bad depending on which 3 years you pick. Rolling windows with monthly steps give you ~49 windows from a 7Y series, which is enough to compute:

- **Median alpha:** robust central tendency.
- **Recent alpha:** the most recent window — what's the fund doing *now*.
- **Beat-%:** in what fraction of windows did the fund beat its benchmark? `>= 0.6` (beat in ≥60% of windows) is the rough industry consistency bar.

Why 3Y windows and not 5Y? SEBI categorization changed in 2018 — funds older than that may have a different mandate today. 3Y windows let us include post-categorization data without diluting it with stale strategies.

## Max drawdown from NAV, not from monthly returns

Drawdown measured from monthly close-NAV underestimates intra-month peaks/troughs. Since we have daily NAV cached, use **daily** for drawdown — produces a tighter, truer figure. The cost is just a few more rows of pandas.

Recovery months = (recovery_date - trough_date) in months. `None` if not yet recovered to the pre-drawdown peak.

## Downside capture: ratio of sums, not average-of-ratios

Two ways to compute capture ratio:

1. **Ratio of sums:** `Σ R_fund | R_bench < 0` ÷ `Σ R_bench | R_bench < 0`. What Morningstar uses.
2. **Average of monthly ratios:** mean of `(R_fund / R_bench)` on down-months. Unstable when bench returns are small.

We use #1 (Morningstar convention). Below 100% = fund absorbed less of the downside than the benchmark — good. Above 100% = fund got hit harder than the benchmark in down months.

## Monthly returns from end-of-month NAV

`fund.resample("ME").last()` then `.pct_change()`. The `"ME"` resample picks the last NAV-available trading day of each month, which is what AMFI/Morningstar/Value Research use.

We don't forward-fill missing days — if a fund didn't report NAV on the last trading day, we use the nearest prior day in that month. This handles holidays cleanly.

## Why no Sharpe / Treynor / Information Ratio / Calmar / Omega in v1

These are all derivatives of return + volatility + benchmark — they correlate strongly with the metrics already in v1. For retail consolidation decisions, more metrics = more noise, not more signal. See `BACKLOG.md` for the deferred list.

## Why no factor decomposition (Treynor-Mazuy, Henriksson-Merton)

These decompose alpha into market-timing skill + stock-selection skill. Useful for fund-manager evaluation, but irrelevant for "should I keep this fund" — what matters is *whether* alpha exists, not its source. Defer.

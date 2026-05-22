# Backlog

Deferred work — not in v1. Listed here so it's not lost.

## v2.0 — Market-wide fund screener

Goal: evaluate funds you **don't own** to find replacements.

- Fetch NAV history for **full SEBI category** (100-200 funds per category), not just owned funds.
- **Peer-percentile ranking** — normalize each metric within category to a 0-100 percentile.
- **Composite scorer** with category-level normalization (the 35/20/20/10/8/7 weights from the original CLAUDE.md spec).
- New-fund onboarding flow: given a candidate fund, generate a one-page "should I buy?" report.

## Deferred advanced metrics

Re-enable only if v1's 6 metrics fail to discriminate between funds.

- **Treynor-Mazuy decomposition** — regression separating stock-picking α from market-timing γ. Wide confidence intervals on 3Y data; rarely statistically significant for retail funds.
- **Dual-beta model** — separate up-market and down-market betas. Capture spread (skill #5 indirectly proxies this).
- **Omega ratio** — full-distribution alternative to Sharpe. Correlated ~0.85+ with Sortino.
- **Ulcer Performance Index** — drawdown-weighted return. Correlated with max-DD + Calmar.
- **Calmar ratio** — return / max DD. Redundant with max DD + alpha shown separately.
- **Information Ratio** — alpha / tracking error. Useful for actively managed funds vs benchmark, but our rolling 3Y alpha already captures the active-return part.
- **Sharpe stability**, **alpha stability** — stddev of rolling Sharpe/alpha. Use only if the simple "rolling 3Y beat-%" doesn't separate consistent vs lucky funds.
- **Bear-market alpha** — alpha conditional on benchmark-negative quarters. Worth adding if downside capture alone misses the story.

## Deferred analytical features

- **Factor attribution** — decompose returns into size/value/momentum/quality factor exposures using factor proxy indices (e.g. Nifty 200 Quality 30, Nifty Midcap 150 Momentum 50). Hard data problem in Indian markets.
- **Active share** — % of holdings that differ from benchmark constituents. Requires fund holdings + benchmark constituent weights (paywalled for most indices).
- **Sector overlap** (in addition to stock-level overlap) — useful, but top-10 stock overlap is the higher-leverage signal first.
- **Style drift detection** — alert when a flexi-cap fund is suddenly 80% large-cap. Needs multi-quarter holdings history.
- **AUM-impact warning** — small-cap funds typically lose alpha above ~₹15-20k Cr AUM. Codify the rule and flag.

## Deferred fund categories

- **Debt funds** — different risk model (credit, duration, YTM). Out of v1 scope.
- **Hybrid / multi-asset funds** — need composite benchmarks. Out of v1 scope.
- **International funds** — currency exposure, different benchmarks. Out of v1 scope.

## Deferred reporting

- **Streamlit/Plotly dashboard** — alternative to the notebook for repeated use.
- **Email/Slack digest** — scheduled summary on portfolio changes.
- **PDF investor report** — exportable, shareable version of the notebook.

## Deferred data sources

- **Morningstar India** (paid) — cleanest fundamentals data, would replace VRO scraping.
- **Bloomberg / Refinitiv** (paid) — institutional-grade TRI, benchmark constituents, factor data.
- **NSE Bhav Copy** archive — historical index constituents for active share calculation.

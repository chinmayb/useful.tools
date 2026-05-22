# Indian Mutual Fund Portfolio Analyzer

## Goal

Analyze **my own 20+ Indian mutual fund holdings** to support **consolidation decisions** — i.e. identify which funds to sell and which to keep, with evidence.

This is a **personal portfolio tool**, not a market-wide screener. Screening funds I don't own is out of scope for v1 (see `BACKLOG.md` for v2.0).

## Decision Lens

A fund earns its place in the portfolio when it:

1. Delivers **risk-adjusted outperformance** vs its benchmark (not vs peers — see "scope" below).
2. Protects on the **downside** (limits max drawdown, recovers quickly).
3. Performs **consistently** (rolling windows, not lucky streaks).
4. Has a **stable manager** with a defensible track record.
5. Does **not duplicate** exposure I already have through another fund.
6. Justifies its **cost** (expense ratio, exit load) vs the marginal value it adds.

## Core Metrics (v1)

Six metrics, all benchmark-relative (not peer-percentile — we're not screening the market):

| Metric | Category | Why |
|---|---|---|
| **Sortino ratio** | Risk-adjusted | Penalizes only downside vol — better than Sharpe for skewed equity returns |
| **Rolling 3Y alpha vs benchmark** | Risk-adjusted | Captures excess return generation; rolling = robust to single windows |
| **Max drawdown** | Downside | Worst-case loss endured |
| **Recovery months** | Downside | How fast the fund climbed back from max DD |
| **Downside capture** | Downside | % of benchmark losses absorbed in down markets |
| **Rolling 3Y beat-%** | Consistency | % of rolling 3Y windows where fund beat its benchmark |

Plus qualitative inputs from `scrape-fund-fundamentals`:

- **Expense ratio**, **AUM trajectory**, **fund manager name + tenure**, **top-10 holdings**.

And one differentiation signal:

- **Pairwise holdings overlap** across my funds (highest-leverage signal for a 20+ fund portfolio).

> **Caveat:** Overlap is computed from **top-10 holdings only** (VRO/screener.in expose only the top-10 per scheme). The reported overlap % is therefore a **lower bound** — two funds showing 30% overlap on top-10 could be 50%+ on full portfolio. Full-portfolio holdings live in AMFI's monthly PDF disclosures and are deferred to v2.0.

## Lookback Windows

`fetch-nav-history` caches **all available history** from mfapi.in (typically 5-13 years per fund, depending on launch date). Storage is cheap (~60KB/fund); window decisions live in the metric skills, not the data layer.

`compute-core-metrics` (skill #5) MUST respect these defaults — they match Morningstar/Value Research industry convention:

| Metric | Lookback | Rationale |
|---|---|---|
| Max drawdown | **All available** | Older = more informative (captures COVID 2020, NBFC 2018, demonetization). |
| Recovery months | **All available** | Tied to max DD. |
| Sortino | **5 years** | Captures current volatility regime; older data risks mixing in a different fund (manager, AUM, mandate). |
| Rolling 3Y alpha | **7 years** | Needs ~3+ non-overlapping 3Y windows to be robust. |
| Rolling 3Y beat-% | **7 years** | Same. |
| Downside capture | **5 years** | Morningstar/VRO convention. |

Make `lookback_years` configurable per-run; defaults above. For funds with shorter history than the lookback, emit a per-fund warning (`"fund_age_years": 3.2, "lookback_requested": 5`) and compute on what's available — do not silently drop the fund or pad with zeros.

## Out of Scope (v1)

- **Peer-percentile ranking** across full SEBI category (requires fetching 100+ peer NAVs — defer to v2.0 market screener).
- **Advanced metrics**: Treynor-Mazuy decomposition, dual-beta, Omega ratio, Ulcer Performance Index, Calmar, Information Ratio. All correlated with Sortino/alpha for retail purposes; add only if v1 doesn't discriminate.
- **Factor attribution**, **active share**, **sector overlap** (top-10 stock overlap is enough for v1).
- **Debt and hybrid funds** — equity-only for v1.

See `BACKLOG.md` for the full deferred list.

## Data Sources

| Source | Used for | Cache TTL |
|---|---|---|
| AMFI bulk dump (`portal.amfiindia.com/spages/NAVAll.txt`) | Daily NAV, scheme master | 1 day |
| mfapi.in (`api.mfapi.in/mf/<code>`) | Per-scheme NAV history (5+ years) | 1 day |
| niftyindices.com daily TRI CSV | Benchmark TRI series | 1 day |
| Value Research Online (scrape) | Manager, expense, AUM, holdings | **14 days** |
| screener.in (scrape, supplemental) | Cross-check fundamentals | 14 days |
| Zerodha MCP | My live holdings | per session |

**Scraping fragility:** VRO/screener selectors will break when those sites redesign. Every scraping skill supports a manual-CSV-fallback (`data/fundamentals/<isin>.manual.json`) that overrides the scraped value. When scraping breaks, paste data from the website into the manual JSON and the pipeline keeps running.

## Output

Primary output is the **markdown report emitted by `portfolio-health-check`** (`data/reports/<date>/portfolio_health.md`) plus the per-skill CSV/JSON artifacts under `data/`. The report renders fine in any markdown viewer (GitHub, terminal `glow`, VS Code preview) so a notebook UI is not required for v1.

`MF_Portfolio_Analysis.ipynb` exists in the repo for ad-hoc charting/parameter sweeps; it's optional, not the canonical interface.

## Skill Plan — Final v1 scope

Skills live in `.claude/skills/<name>/SKILL.md`. **8 of 9 shipped; 1 left:**

**M1 — Data pipeline (4 skills)**
1. ✅ `fetch-nav-history`
2. ✅ `benchmark-mapper`
3. ✅ `zerodha-portfolio-sync`
4. ✅ `scrape-fund-fundamentals` *(Tickertape, not VRO — see BACKLOG.md for the pivot story)*

**M2 — Decision-grade analysis (2 skills)** — *the headline value lands here*
5. ✅ `compute-core-metrics`
6. ✅ `portfolio-overlap-analyzer`

**M3 — Tax/rebalance (1 skill)**
7. ✅ `tax-aware-rebalancer`

**M4 — Orchestration (1 skill)**
8. ⏭ `portfolio-health-check` (orchestrator) ← last v1 skill

**Deferred from original plan (now in BACKLOG.md):**
- `fund-manager-dossier` — manager data already lives in `data/fundamentals/<isin>.json` from the Tickertape scrape; no dedicated skill needed for v1.
- `notebook-section-writer` — `portfolio-health-check`'s markdown report is the primary surface; revisit only if interactive charting becomes a real need.

## Tax Assumptions

New regime (FY24-25 onward):
- **LTCG**: 12.5% on equity gains above ₹1.25L annual exemption (holding ≥1 year).
- **STCG**: 20% on equity gains (holding <1 year).
- **Exit load**: typically 1% if redeemed within 1 year of investment (varies by scheme).

`tax-aware-rebalancer` will treat these as config knobs, not hardcoded.

## Conventions

- **Canonical fund identifier:** ISIN in all in-memory DataFrames (it's what Zerodha returns). On-disk caches are keyed by `scheme_code` when the source uses scheme_code (AMFI, mfapi.in). The AMFI scheme master joins the two.
- **Column names** (used across all skills): `isin, scheme_code, scheme_name, category, units, avg_cost, current_nav, invested_amount, current_value, pnl` — matching `mf_analyzer.py`'s existing schema.
- **Dates:** ISO `YYYY-MM-DD` in all CSVs/JSON. IST is the implicit timezone.
- **₹ amounts:** `float64`, rounded to 2 decimal places.
- **Error logs:** JSON Lines (`*.jsonl`) — one error object per line, downstream-parseable.

## Integration Risks (resolved)

- ✅ `niftyindices.com` TRI endpoint — verified working at `getTotalReturnIndexString` (the originally-documented `getHistoricaldatatabletoString` returns the price index, not TRI; would have biased every alpha calculation by ~1.2% pa).
- ✅ `valueresearchonline.com` — Cloudflare-blocked; pivoted to Tickertape (Premium user account). See `scrape-fund-fundamentals/references/tickertape_endpoints.md` for the verified contract.

## Notes

- `mf_analyzer.py` and `zerodha_integration.py` are legacy library files; the analysis pipeline is the `.claude/skills/<name>/scripts/` modules. The notebook is optional.
- All Indian-specific conventions: ₹ (not $), INR, IST, financial year Apr-Mar.

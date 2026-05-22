---
name: scrape-fund-fundamentals
description: Pulls per-fund fundamentals (expense ratio, AUM, fund manager + tenure, stated benchmark, risk classification, Tickertape scorecard) for Indian mutual funds via Tickertape's server-side-rendered fund pages. Reads the JWT from ~/.config/mf_analyze/tickertape.env. Use whenever fundamentals are needed for composite scoring, manager dossier, or any analysis that goes beyond pure NAV-based metrics. Honors a 14-day cache TTL because fundamentals change slowly. Don't use for fully-real-time data — the data reflects last monthly disclosure.
---

# Scrape Fund Fundamentals

Pulls qualitative + ratings data that NAV history can't reveal. Tickertape is the data source — chosen after smoke-testing showed every other public source (Value Research, screener.in, moneycontrol) is Cloudflare-gated or has no MF coverage.

## When to use

- Composite scoring (need expense ratio + manager info).
- Manager dossier (need manager name + tenure).
- Cross-check against `benchmark-mapper` (fund's stated benchmark vs SEBI category default).
- Whenever Tickertape's proprietary 5-dim scorecard would augment the consolidation decision.

## When NOT to use

- For pure return-based metrics (Sortino, max DD, alpha) — those need only NAV.
- For real-time NAV (use AMFI / `fetch-nav-history`).
- For full top-N stock holdings — Tickertape's SSR'd page exposes sector breakdown but not the individual top-10 stock weights. Holdings data is loaded via a separate XHR on the portfolio tab and is **deferred for v1** (see `BACKLOG.md`).

## Inputs

A list of ISINs, or `--portfolio` to read the latest holdings snapshot.

## Authentication

Tickertape requires a Premium subscription for full data access. The JWT lives at `~/.config/mf_analyze/tickertape.env` (chmod 600, never committed). The token has a **24-hour TTL** and must be refreshed by:

1. Logging into https://www.tickertape.in
2. Opening DevTools → Network → Fetch/XHR
3. Picking any `api.tickertape.in` or `ecosystem.api.tickertape.in` request → right-click → **Copy as cURL (bash)**
4. Extracting the `jwt=...` from `-b` and the `x-csrf-token` header value
5. Updating `~/.config/mf_analyze/tickertape.env` with both values

The skill detects an expired token (HTTP 401) and prints exactly these instructions if it fires.

## Architecture

Two endpoints, two access modes:

| Source | URL pattern | Auth needed? | Data |
|---|---|---|---|
| **SSR'd fund page** | `https://www.tickertape.in/mutualfunds/<slug>-<sid>` | **No** | Everything below in one shot via `__NEXT_DATA__` embedded JSON |
| **Search API** | `https://api.tickertape.in/search?text=<q>&types=mutualfund` | **Yes** | ISIN → SID resolution only |

The page is fully SSR'd by Next.js — the 335KB of `pageProps` JSON embedded in the HTML contains scorecard, manager, expense ratio, AUM, peers, CAGR series, exit load, tax meta. **No auth needed for the page itself** — auth is only needed once per fund to resolve ISIN → SID via the search API.

## Output Schema

For each fund, write `data/fundamentals/<isin>.json`:

```json
{
  "isin": "INF879O01027",
  "tickertape_sid": "M_PARO",
  "scheme_name": "Parag Parikh Flexi Cap Fund",
  "amc": "PPFAS Asset Management Pvt. Ltd.",
  "plan": "Direct",
  "option": "Growth",
  "subsector": "Flexi Cap Fund",
  "risk_classification": "Very High",
  "stated_benchmark": "NIFTY 500 - TRI",
  "nav_close": 90.614,
  "expense_ratio_pct": 0.53,
  "category_expense_ratio_pct": 1.35,
  "aum_cr": 160596.28,
  "exit_load_pct": 2,
  "exit_load_remarks": "Nil upto 10% of units. For remaining units 2% on or before 365D...",
  "lock_in_months": 0,
  "managers": [
    {"name": "Rajeev Thakkar", "fm_code": 474, "experience_years": 18, "qualification": "B.Com, CA, CFA, ICWA"}
  ],
  "scorecard": [
    {"name": "Performance", "tag": "High", "color": "green", "score": 6.76, "rank": 7, "peers": 45},
    {"name": "Risk",        "tag": "Low",  "color": "green", "score": ..., ...}
  ],
  "cagr_series": [{"yearDiff": 0.5, "value_pct": -4.03}, {"yearDiff": 1, "value_pct": 1.04}, ...],
  "scraped_at": "2026-05-23T00:25:00+05:30",
  "source": "tickertape"
}
```

Manual overrides at `data/fundamentals/<isin>.manual.json` always win (same schema; set `"source": "manual"`).

## Procedure

### Step 1 — Manual override check

If `data/fundamentals/<isin>.manual.json` exists, return it immediately. No scrape.

### Step 2 — Cache check

If `data/fundamentals/<isin>.json` exists and its mtime is < 14 days old, return cache. Fundamentals follow the monthly disclosure cycle; 14 days = ~2× per disclosure.

### Step 3 — Resolve ISIN → Tickertape SID

ISIN doesn't appear in Tickertape's search response, so resolution is by **name match**:

1. Look up the AMFI scheme name from `data/amfi_scheme_master.csv` (joined on ISIN).
2. Strip the trailing " - Direct Plan - Growth" / "-Direct-Growth" suffixes and normalize.
3. `GET https://api.tickertape.in/search?text=<query>&types=mutualfund` (auth required).
4. Filter `items[]` for `option == "Growth"` and pick the one whose `fullname` best matches the AMFI name.

The resolved SID is stored in the cached JSON; subsequent runs skip search.

### Step 4 — Fetch and parse the SSR'd page

`GET https://www.tickertape.in/mutualfunds/<sid>` — Tickertape redirects bare SID URLs to the canonical `<slug>-<sid>` URL automatically. **No auth needed.**

Parse `__NEXT_DATA__`:

```python
import re, json
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html, re.DOTALL)
data = json.loads(m.group(1))
page_props = data['props']['pageProps']
```

Read from these `page_props` substructures:

| Field | Path in pageProps |
|---|---|
| ISIN | `securitySummary.meta.isin` |
| Plan/Option | `securitySummary.meta.plan` / `.option` |
| AMC | `securitySummary.meta.amc` |
| Stated benchmark | `securitySummary.meta.benchmarkIndex` |
| Risk classification | `securitySummary.meta.riskClassification` |
| NAV close | `securityInfo.navClose` |
| Expense ratio | `securitySummary.keyRatios[]` where `backL == "expRatio"` |
| Category expense ratio | `securitySummary.keyRatios[]` where `backL == "catExpRatio"` |
| AUM (Cr) | `securitySummary.amcDetails.aum` |
| Exit load + remarks | `securitySummary.schemeInfo[]` where `backL == "exitLoad"` |
| Lock-in (months) | `securitySummary.schemeInfo[]` where `backL == "lockInPeriod"` |
| Managers | `fundManagers[]` |
| Scorecard | `scorecard[]` |
| CAGR series | `securitySummary.cagrSeries[]` |

### Step 5 — Write per-ISIN JSON

Write to `data/fundamentals/<isin>.json`. On any error, write a partial record with `"scrape_status": "partial"` and continue — downstream skills check `scrape_status` and fall back gracefully.

## Error Handling

| Failure | Detection | Recovery |
|---|---|---|
| Expired JWT | HTTP 401 on search | Print refresh instructions (see "Authentication"), exit nonzero |
| Tickertape down | HTTP 5xx or timeout | Log + skip that ISIN; continue with others |
| ISIN not found in search | search `total == 0` | Log; check for `<isin>.manual.json`; otherwise skip |
| Multiple ambiguous matches | search returns >1 Growth result | Use rapidfuzz on AMFI name vs each `fullname`; pick highest score >0.85; else skip |
| `__NEXT_DATA__` missing | regex no-match | Tickertape may have changed page structure — alert with selector path; fall back to manual JSON |
| Page returns 404 | HTTP 404 | Cached search SID is stale — clear cache, re-resolve, retry once |

## Caching

| Artifact | TTL | Notes |
|---|---|---|
| Per-ISIN JSON | 14 days | Disclosure cycle is monthly |
| ISIN → SID mapping | embedded in JSON | Survives until JSON cache is cleared |
| Manual override | ∞ | Never expires |

## Out of scope (v1) — top-N stock holdings

Tickertape's portfolio tab loads top-N stock weights via a separate authenticated XHR that the SSR'd page does not include. Skipping this for v1 means `portfolio-overlap-analyzer` will use return-correlation as a proxy for holdings overlap (correlated funds → likely overlapping). True top-N stock overlap is deferred — see `BACKLOG.md`.

## Bundled Scripts

- `scripts/scrape_tickertape.py` — main scraper. CLI: per-ISIN or `--portfolio`.
- `scripts/lib_tickertape.py` — pure helpers (auth-header construction, page parser, ISIN/SID resolver).

## Bundled References

- `references/tickertape_endpoints.md` — endpoint contracts (search auth, page URL pattern, response-shape reference).

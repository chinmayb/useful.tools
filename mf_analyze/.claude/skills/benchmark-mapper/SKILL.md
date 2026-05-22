---
name: benchmark-mapper
description: Maps an Indian mutual fund's SEBI category to its correct Total Return Index (TRI) benchmark and fetches daily TRI history from niftyindices.com. Use whenever computing alpha, capture ratios, beat-%, or any benchmark-relative metric. Always use this skill before any return comparison — choosing the wrong benchmark silently biases every downstream metric. Don't use for debt or hybrid funds in v1.
---

# Benchmark Mapper

Resolves the right Total Return Index (TRI) for each fund category and fetches its daily history. TRI matters — price-only indices (what yfinance returns) systematically understate benchmark returns by ~1-1.5% annualized, biasing alpha upward.

## When to use

- Computing **any** benchmark-relative metric (alpha, beat-%, downside/upside capture, tracking error).
- The user adds a new fund and we need to know which index it's measured against.
- Refreshing TRI history (daily cache).

## When NOT to use

- For absolute return metrics that don't need a benchmark (Sortino, max DD, recovery months).
- For debt/hybrid funds in v1 — benchmark mapping is more involved and out of scope.

## Inputs

A fund's category string (SEBI category name, e.g. `Small Cap`, `Flexi Cap`, `ELSS`, `Mid Cap`).

## The Mapping

Use `references/category_to_benchmark.md` as the canonical lookup. Summary for equity funds:

| SEBI Category | TRI Benchmark | niftyindices code |
|---|---|---|
| Large Cap | Nifty 100 TRI | `NIFTY 100 TRI` |
| Large & Mid Cap | Nifty Large Midcap 250 TRI | `NIFTY LARGEMIDCAP 250 TRI` |
| Flexi Cap / Multi Cap | Nifty 500 TRI | `NIFTY 500 TRI` |
| Mid Cap | Nifty Midcap 150 TRI | `NIFTY MIDCAP 150 TRI` |
| Small Cap | Nifty Smallcap 250 TRI | `NIFTY SMALLCAP 250 TRI` |
| ELSS | Nifty 500 TRI | `NIFTY 500 TRI` |
| Focused | Nifty 500 TRI | `NIFTY 500 TRI` |
| Value / Contra | Nifty 500 TRI | `NIFTY 500 TRI` |
| Dividend Yield | Nifty Dividend Opportunities 50 TRI | `NIFTY DIVIDEND OPPORTUNITIES 50 TRI` |
| Index (Nifty 50) | Nifty 50 TRI | `NIFTY 50 TRI` |

If a fund's stated benchmark in its SID/factsheet differs (e.g. a Flexi Cap fund benchmarked to BSE 500), **trust the fund's own benchmark** — log a note and use the fund-specified one.

> **Run-order dependency:** The fund-override path only works if `scrape-fund-fundamentals` has already populated `data/fundamentals/<isin>.json` with `stated_benchmark`. When orchestrated together, fundamentals must run **before** benchmark-mapper. If fundamentals is unavailable for a fund, fall back to the category-based mapping above.

## Procedure

### Step 1 — Resolve the benchmark

- Look up the SEBI category in the mapping table.
- If the fund overrides via its own benchmark (from `scrape-fund-fundamentals` output), use that instead. Log the override.
- For unknown categories: write to stderr and skip the fund. Do not fall back to "Nifty 50 TRI" silently — that's the kind of default that biases analysis.

### Step 2 — Check the TRI cache

- Cache path: `data/benchmarks/<index_code_slug>.csv` with columns `date, value`.
- Cache TTL: 1 day. Skip fetch if fresh.

### Step 3 — Fetch missing TRI series

> ⚠️ **Unverified endpoint.** The niftyindices.com historical TRI endpoint described below is documented from memory and **has not been smoke-tested**. Before relying on this skill in the pipeline, run `scripts/smoke_test_tri.py` against a known index (e.g. `NIFTY 50 TRI`) and confirm the response shape. If the endpoint differs, update this section and the script. If it's gone entirely, the manual-CSV fallback (Step 4) is the recovery path.

`niftyindices.com` exposes historical data via (best understanding):

```
POST https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString
Body (JSON, form-encoded): {"name": "<INDEX NAME>", "startDate": "DD-MMM-YYYY", "endDate": "DD-MMM-YYYY"}
```

Response: JSON array of `{HistoricalDate, TotalReturnsIndex}` rows. Date format `DD MMM YYYY` (e.g. `15 Jan 2024`); normalize to ISO `YYYY-MM-DD`. The endpoint typically caps each request to ~1 year — chunk longer ranges.

Implementation lives in `scripts/fetch_tri.py`.

### Step 4 — Manual-CSV fallback

If the niftyindices fetch fails (HTTP error, anti-scraping HTML response, empty JSON), check for `data/benchmarks/<slug>.manual.csv` with columns `date, value`. If present, use it. If neither works, log a clear error and skip that benchmark — caller can decide how to proceed.

### Step 5 — Return benchmark series

Return a DataFrame:

```
date       | benchmark_code        | value
2024-01-15 | NIFTY SMALLCAP 250 TRI | 18472.34
```

## Output

- **Files written:** `data/benchmarks/<slug>.csv` per index.
- **Returned:** DataFrame as above.
- **Helper function:** `get_benchmark_for_fund(scheme_code) -> (benchmark_code, tri_series)`.

## Caching

| Artifact | TTL |
|---|---|
| Benchmark TRI CSV | 1 day |

niftyindices.com has no public rate limit documented; 1 req/sec is courteous.

## Error Handling

- **Unknown category:** stderr + skip. Caller must decide how to proceed without a benchmark.
- **niftyindices POST returns HTML (anti-scraping):** the request shape changed. Fall back to the manual CSV at `data/benchmarks/<slug>.manual.csv` if present. If neither works, skip with a clear error.
- **TRI series has gaps:** acceptable (NSE non-trading days). Don't forward-fill in this skill — let downstream skills decide.
- **Fund's stated benchmark not in the mapping table:** log + use Nifty 500 TRI as a best-effort default for flexi/multi-style funds, but mark the result as `benchmark_confidence: low` in the output.

## Bundled Scripts

- `scripts/fetch_tri.py` — fetches one TRI series from niftyindices.
- `scripts/refresh_all_benchmarks.py` — refreshes all cached benchmarks in `data/benchmarks/`.

See `references/category_to_benchmark.md` for the full mapping (including debt/hybrid placeholders marked "v2.0 — out of scope").

## A Note on Why TRI Matters

Indian equity indices have a typical dividend yield of ~1.2%. A price-only index drops dividends; TRI reinvests them. Over 5 years that's ~6-7% understated benchmark return — enough to make a fund look alpha-generative when it's actually flat to benchmark. Never compute alpha vs a price index in this project.

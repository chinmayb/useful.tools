---
name: benchmark-mapper
description: Maps an Indian mutual fund's SEBI category to its correct Total Return Index (TRI) benchmark and fetches daily TRI history from niftyindices.com. Use whenever computing alpha, capture ratios, beat-%, or any benchmark-relative metric. Always use this skill before any return comparison — choosing the wrong benchmark silently biases every downstream metric. Don't use for debt or hybrid funds in v1.
---

# Benchmark Mapper

Resolves the right Total Return Index (TRI) for each fund and fetches its daily history. TRI matters — price-only indices (what yfinance returns for `^NSEI`) systematically understate benchmark returns by ~1.2% annualized, which biases alpha upward.

## When to use

- Computing **any** benchmark-relative metric (alpha, beat-%, downside/upside capture, tracking error).
- The user adds a new fund and we need its benchmark.
- Refreshing TRI history (daily cache).

## When NOT to use

- For absolute return metrics that don't need a benchmark (Sortino, max DD, recovery months).
- For debt, hybrid, FoF Overseas, or commodity FoF funds in v1 — these are skipped automatically by `refresh_all_benchmarks.py` with a notice.

## Inputs

A holdings snapshot (`data/holdings/<YYYY-MM-DD>/holdings.csv`) with `category` and `scheme_name` columns. The orchestrator reads the latest snapshot by default.

## Mapping

The mapping table lives in `references/category_to_benchmark.md`. Three resolution tiers:

1. **Category default** (Large Cap → Nifty 100 TRI, Small Cap → Nifty Smallcap 250 TRI, etc.).
2. **Scheme-name substring match** for Index funds (AMFI lumps all index funds under `Index Funds`) and Sectoral/Thematic funds (each tracks its own sector index).
3. **Fund override** — if `scrape-fund-fundamentals` has populated `data/fundamentals/<isin>.json` with `stated_benchmark`, that wins.

> **Run-order:** if you want fund-level overrides, `scrape-fund-fundamentals` must run **before** `benchmark-mapper`. Without fundamentals, the category-based mapping is used everywhere.

## Procedure

### Step 1 — Resolve the benchmark for each fund

`refresh_all_benchmarks.py` loops over `holdings.csv` and calls `resolve_benchmark(category, scheme_name)`:

- In-scope equity categories use the table in `category_to_benchmark.md`.
- Out-of-scope categories (debt, hybrid, FoF Overseas, commodity FoF) are skipped with a notice — not silently dropped.
- Unrecognized Index/Sectoral schemes log a warning; sectoral funds fall back to `NIFTY 500` with `benchmark_confidence: low`.

### Step 2 — Check the TRI cache

- Cache path: `data/benchmarks/<slug>.csv` with columns `date, value`.
- Cache TTL: 1 day. Fresh cache → skip the fetch.

### Step 3 — Fetch missing TRI series

Calls `scripts/fetch_tri.py` per index. The verified endpoint and payload contract are documented in `references/niftyindices_endpoint.md` — read it before changing the script:

- Endpoint: `POST https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString` (note: **not** the price-index endpoint `getHistoricaldatatabletoString`).
- Required headers: Referer, Origin, X-Requested-With, browser UA. Without them, the server hangs (no 4xx).
- Body: `{"cinfo": "<stringified-JSON-with-single-quotes>"}`, inner keys `name` / `startDate` / `endDate` / `indexName`.
- Response: `{"d": "<stringified-array>"}` — `d` requires a second `json.loads`. Rows have `Date` (DD MMM YYYY), `TotalReturnsIndex` (string float).
- Chunking: 365-day chunks with 1-second courtesy delay between chunks.

### Step 4 — Manual-CSV fallback

If all chunks fail (HTTP error, anti-scraping HTML, persistent timeouts), `fetch_tri.py` looks for `data/benchmarks/<slug>.manual.csv` with columns `date, value`. If present, it's used. If neither path works, the index is logged to `_errors.jsonl` and the orchestrator continues with the rest.

### Step 5 — Return benchmark series

Each cached CSV is the persistent return value. Downstream skills (`compute-core-metrics`) read these directly via `pd.read_csv("data/benchmarks/<slug>.csv")`.

## Output

- **Files written:** `data/benchmarks/<slug>.csv` per index; `data/benchmarks/_errors.jsonl` on failure.
- **Returned:** the script writes files and prints a summary; downstream loads from disk.

## Caching

| Artifact | TTL |
|---|---|
| Benchmark TRI CSV | 1 day |

niftyindices has no documented rate limit; 1 req/sec between chunks is courteous.

## Error Handling

- **Unknown category:** stderr + skip with the fund name listed. Caller decides whether to proceed.
- **niftyindices request hangs / 5xx:** retry path is the manual-CSV fallback (Step 4). Log the failed range to `_errors.jsonl`.
- **Empty `d` response:** widen the date range — this usually means the range hit only market holidays.
- **Sectoral fund name doesn't match any pattern:** falls back to `NIFTY 500` with a low-confidence log line.

## Bundled Scripts

- `scripts/fetch_tri.py` — fetches one TRI series from niftyindices with chunking + cache.
- `scripts/refresh_all_benchmarks.py` — orchestrator that resolves all benchmarks for the latest holdings snapshot and fetches each.

## Bundled References

- `references/niftyindices_endpoint.md` — full endpoint contract (verified 2026-05-22).
- `references/category_to_benchmark.md` — canonical SEBI category → TRI mapping + sectoral substring rules + v1/v2 scope.

## Why TRI Matters

Indian equity indices have ~1.2% trailing dividend yield. Over 5 years that compounds to ~6-7% — enough to make a fund look alpha-generative when it's actually flat to benchmark. Never compute alpha vs a price index in this project.

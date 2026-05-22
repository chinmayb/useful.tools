---
name: fetch-nav-history
description: Fetches and caches daily NAV history for Indian mutual funds from AMFI and mfapi.in. Use whenever the user wants to fetch, refresh, download, update, or cache NAV data — including phrases like "get fund NAV", "pull historical prices", "refresh the fund cache", or any analysis workflow that needs price history. Always use this skill before computing any return-based metric. Honors a 1-day cache TTL so repeat calls are cheap.
---

# Fetch NAV History

Pulls daily NAV (Net Asset Value) history for Indian mutual fund schemes and caches it to `data/nav/`. Foundational data skill — every metric in this project depends on its output.

## When to use

- The user wants to fetch, refresh, or cache NAV data for one or more funds.
- Starting any analysis workflow that needs price history (returns, drawdowns, alpha, etc.).
- The cache is stale (>1 day old) or missing for any fund being analyzed.

## When NOT to use

- The user only wants the *latest* NAV (not history). Hit AMFI's NAVAll.txt directly for that.
- For non-Indian funds (this skill is AMFI/mfapi-specific).

## Inputs

A list of scheme identifiers. Accept either:
- **AMFI scheme codes** (preferred — 6-digit integer, e.g. `120586`).
- **ISINs** (e.g. `INF200K01VK5`) — resolve to scheme codes via the AMFI scheme master.

Optional: `--force-refresh` to bypass cache.

## Procedure

### Step 1 — Ensure the scheme master is current

The scheme master maps ISINs ↔ scheme codes ↔ scheme names ↔ category.

- Cache location: `data/amfi_scheme_master.csv`.
- Source: `https://portal.amfiindia.com/spages/NAVAll.txt` (pipe-delimited, parsed into a CSV).
- Refresh if missing or older than 1 day:
  ```
  python scripts/refresh_scheme_master.py
  ```

### Step 2 — Resolve any ISINs to scheme codes

For each input identifier:
- If it looks like an ISIN (`INF*`), look it up in `data/amfi_scheme_master.csv` and resolve to `scheme_code`.
- If it's already a 6-digit code, pass through.
- If unresolvable, write the failing ISIN to stderr and continue with the rest. Do not abort the whole run.

### Step 3 — Check cache freshness per scheme

For each scheme code:
- Cache path: `data/nav/<scheme_code>.csv` with columns `date, nav`.
- If file exists and mtime is <1 day old (and `--force-refresh` not set), skip the fetch.

### Step 4 — Fetch missing/stale NAVs

For each scheme needing a fetch:
- `GET https://api.mfapi.in/mf/<scheme_code>` returns JSON with a `data` array of `{date, nav}` (date in `DD-MM-YYYY`).
- Parse dates to ISO `YYYY-MM-DD`, sort ascending, drop duplicates, write to `data/nav/<scheme_code>.csv`.
- Rate-limit: 3 requests/second (mfapi.in is community-hosted but has no documented limit; 3 rps for ~20 funds finishes in <10s without being abusive).
- On HTTP error: append a JSON object to `data/nav/_errors.jsonl` (one error per line: `{"scheme_code": "...", "error": "...", "ts": "..."}`) and continue.

### Step 5 — Return combined DataFrame

Return a long-format pandas DataFrame:

```
isin         | scheme_code | scheme_name | category   | date       | nav
INF200K01VK5 | 120586      | SBI Small.. | Small Cap  | 2024-01-15 | 142.85
```

`isin` is the canonical key for joining with `zerodha-portfolio-sync` output. `scheme_code` is kept as the cache filename anchor.

Joined with the scheme master so `scheme_name`, `category`, and `isin` are all available downstream.

## Output

- **Files written:** `data/nav/<scheme_code>.csv` per scheme; `data/amfi_scheme_master.csv`; optional `data/nav/_errors.jsonl`.
- **Returned:** long-format DataFrame as above.

## Caching

| Artifact | TTL | Refresh rule |
|---|---|---|
| Scheme master | 1 day | mtime check on `data/amfi_scheme_master.csv` |
| Per-scheme NAV CSV | 1 day | mtime check on `data/nav/<code>.csv` |

`--force-refresh` overrides both. Use sparingly; mfapi.in is community infra.

## Error Handling

- **AMFI master fetch fails:** abort. Without it, ISIN resolution is impossible.
- **Single scheme NAV fetch fails:** log to `_errors.jsonl`, continue with others. Caller should check the log.
- **ISIN not found in master:** log + skip; common for very new funds (master lags by ~1 day).
- **Empty NAV response:** treat as fetch failure (don't overwrite a good cache with empty data).

## Output Format Notes

- All dates as ISO `YYYY-MM-DD`.
- NAV as `float64`, rounded to 4 decimal places.
- DataFrame index is **not** the date — keep `date` as a column so multi-scheme joins are trivial.

## Bundled Scripts

- `scripts/refresh_scheme_master.py` — pulls AMFI NAVAll.txt, parses to CSV, writes scheme master.
- `scripts/fetch_nav.py` — fetches one or more scheme codes from mfapi.in.

See `references/amfi_format.md` for the AMFI pipe-delimited format details.

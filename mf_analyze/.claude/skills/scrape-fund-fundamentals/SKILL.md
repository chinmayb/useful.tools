---
name: scrape-fund-fundamentals
description: Scrapes Value Research Online and screener.in for Indian mutual fund fundamentals (expense ratio, AUM, fund manager + tenure, top-10 holdings, fund's stated benchmark) with manual-CSV-fallback. Use whenever fundamentals are needed for analysis, manager dossier, or overlap work — including phrases like "fetch fund fundamentals", "get expense ratio", "who manages this fund", "what does this fund hold". Always use this skill before composite scoring or overlap analysis. Honors a 7-day cache TTL because fundamentals change slowly (monthly disclosure cycle).
---

# Scrape Fund Fundamentals

Pulls qualitative + holdings data that NAV history can't reveal: expense ratio, AUM, manager name and tenure, top-10 holdings, fund's stated benchmark. Source order is VRO → screener.in → manual override.

## When to use

- Composite scoring (need expense ratio + manager info).
- Manager dossier (need manager name + tenure).
- Overlap analyzer (need top-10 holdings per fund).
- Benchmark mapper sanity check (does the fund use a different benchmark than the SEBI category default?).

## When NOT to use

- For pure return-based metrics (Sortino, max DD, alpha) — those need only NAV.
- For real-time NAV (use AMFI / `fetch-nav-history`).

## Inputs

A list of ISINs (preferred) or fund names. ISIN is more reliable; fund names are ambiguous (Direct/Regular, Growth/IDCW variants).

## Output Schema

For each fund, write `data/fundamentals/<isin>.json`:

```json
{
  "isin": "INF200K01VK5",
  "scheme_name": "SBI Small Cap Fund - Direct Plan - Growth",
  "category": "Small Cap",
  "fund_house": "SBI Mutual Fund",
  "expense_ratio_pct": 0.68,
  "aum_cr": 28450,
  "aum_as_of": "2026-04-30",
  "manager": {
    "primary": "R. Srinivasan",
    "since": "2013-11-01",
    "co_managers": []
  },
  "stated_benchmark": "Nifty Smallcap 250 TRI",
  "top_holdings": [
    {"company": "Kalpataru Projects", "weight_pct": 3.85, "sector": "Construction"},
    ...
  ],
  "holdings_as_of": "2026-04-30",
  "source": "vro",
  "scraped_at": "2026-05-22T10:23:00+05:30"
}
```

## Procedure

### Step 1 — Check for manual override first

If `data/fundamentals/<isin>.manual.json` exists, **prefer it over any scrape**. This is the fallback when scrapers break — the user pastes a hand-curated JSON and the pipeline keeps moving.

Manual files use the same schema; set `"source": "manual"`.

### Step 2 — Check the cache

Otherwise check `data/fundamentals/<isin>.json` mtime. If < 14 days old, use cache. Fundamentals change on monthly disclosure cycle (~T+30); a 14-day TTL refreshes ~2× per disclosure cycle and minimizes scraping load.

### Step 3 — Scrape Value Research Online (primary)

VRO URL pattern: `https://www.valueresearchonline.com/funds/<vro_slug>/`.

> ⚠️ **Unverified endpoint.** The ISIN → vro_slug lookup is documented here as a VRO autocomplete endpoint (`/api/v2/funds/search-suggestions/`) **from memory** — it has not been smoke-tested. Before relying on this skill, run `scripts/smoke_test_scrapers.py` against a known ISIN (e.g. `INF200K01VK5`). If the endpoint differs, update `references/vro_selectors.md` and the script. If it's gone entirely, the **manual-CSV-fallback** (Step 1) keeps the pipeline running.

Selectors to extract (see `references/vro_selectors.md` for the full set — these change occasionally):

- Expense ratio
- AUM
- Fund manager + start date
- Top-10 holdings table
- Stated benchmark

### Step 4 — Cross-check with screener.in (supplemental)

For each fund, also fetch `https://www.screener.in/mutual-funds/<screener_slug>/` if available. Use it to:

- Sanity-check AUM and expense ratio (mismatch >5% → log warning).
- Get sector breakdown if VRO blocks the holdings table.

screener.in is more equity-focused; MF coverage is partial. Treat its data as supplemental, not authoritative.

### Step 5 — Write the JSON

Write to `data/fundamentals/<isin>.json`. Set `"source": "vro"` or `"vro+screener"` accordingly.

If both scrapers fail and no manual override exists, write a stub with `"scrape_status": "failed"` and a clear error message in `data/fundamentals/_errors.log`. **Do not silently skip** — downstream skills need to know.

## Caching

| Source | TTL | Rationale |
|---|---|---|
| Manual override | ∞ | User-curated; never expires |
| VRO/screener scrape | 14 days | Monthly disclosure cycle; reduces breakage exposure |

`--force-refresh` overrides cache (use sparingly, manually).

## Error Handling — the scraping reality check

These sites *will* redesign. When they do:

1. **VRO selector returns empty** → fall back to screener.in for that field.
2. **Both return empty** → check if `<isin>.manual.json` exists. If yes, use it. If no, write a stub + error log entry like:
   ```
   INF200K01VK5: VRO selector .fund-header__expense returned empty. Likely VRO layout changed. Update selectors in references/vro_selectors.md OR paste a manual JSON at data/fundamentals/INF200K01VK5.manual.json.
   ```
3. **HTTP 403 / cloudflare challenge** → both sites have anti-bot. Sleep 2s between requests; rotate a small set of user-agent strings (see `scripts/scrape_vro.py`).
4. **Top-10 holdings sum to >100% or <70%** → data quality issue. Log and exclude that holdings list from overlap analysis.

### The smoke test

`scripts/smoke_test_scrapers.py` fetches one known-good fund (`INF200K01VK5`) from each source and asserts all expected fields parse. Run weekly via `refresh-cache.sh`. When it fails, you know which selector broke before the analysis pipeline does.

## Output

- **Files written:** `data/fundamentals/<isin>.json` per fund; optional `data/fundamentals/_errors.log`.
- **Returned:** dict keyed by ISIN.

## Bundled Scripts

- `scripts/scrape_vro.py` — single-fund VRO scrape.
- `scripts/scrape_screener.py` — single-fund screener.in scrape.
- `scripts/refresh_cache.sh` — weekly batch refresh; gated on cache age.
- `scripts/smoke_test_scrapers.py` — selector health check.

## Bundled References

- `references/vro_selectors.md` — current VRO CSS selectors + last-verified date.
- `references/screener_selectors.md` — current screener.in selectors.
- `references/manual_template.json` — copy-paste template for `<isin>.manual.json`.

## A Note on Robustness

Scraping is the most fragile layer in this project. The 14-day cache + manual override design is deliberate: when scrapers break, the user can keep working by pasting data from the website. The pipeline degrades gracefully, not catastrophically.

## A Note on Top-10 Holdings

VRO/screener only expose the **top-10 holdings** per scheme. Full-portfolio data lives in AMFI's monthly PDF disclosures and is deferred to v2.0. This means:

- **`portfolio-overlap-analyzer` reports a lower bound on overlap.** Two funds showing 30% overlap on top-10 could be 50%+ on full portfolio. Use the overlap matrix as a "definitely-at-least" floor, not a precise number.
- **Sector and factor exposure** are not captured here (also deferred).

This caveat is also stated in `CLAUDE.md` so it doesn't surprise the analysis downstream.

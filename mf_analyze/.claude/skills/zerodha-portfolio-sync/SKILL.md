---
name: zerodha-portfolio-sync
description: Pulls live mutual fund holdings via the Zerodha MCP, aggregates positions across folios, and normalizes the result to the project's standard DataFrame. Use whenever the user wants to sync, refresh, fetch, or pull their actual portfolio from Zerodha — including phrases like "load my portfolio", "what do I own", "refresh holdings", or any analysis workflow that starts from real holdings rather than sample data. Always use this skill before any per-fund analysis that needs current positions.
---

# Zerodha Portfolio Sync

Canonical procedure for pulling live mutual fund holdings from Zerodha Kite via the Zerodha MCP, normalizing them, and joining against the AMFI scheme master so category and benchmark resolution work downstream.

## When to use

- The user wants their **real** portfolio loaded (not sample data).
- Starting any analysis run via `portfolio-health-check`.
- Refreshing holdings after a recent transaction (SIP installment, manual purchase, redemption).

## When NOT to use

- The user explicitly asks for the sample data demo.
- Zerodha MCP is unavailable — fall back to a manual CSV at `data/holdings/manual_holdings.csv` (see "Manual fallback" below).

## Inputs

None — Zerodha MCP handles authentication and identification.

## Procedure

### Step 1 — Confirm MCP availability

Check that the Zerodha MCP tools are loaded in the current session. If not, prompt the user with:

> The Zerodha MCP is not available. Either enable it for this session, or paste your holdings into `data/holdings/manual_holdings.csv` (template at `assets/manual_holdings_template.csv`) and I'll proceed from there.

### Step 2 — Authenticate

Call the Zerodha MCP login flow. Zerodha requires interactive login the first time per day; subsequent calls reuse the session.

### Step 3 — Fetch MF holdings

Call the Zerodha MCP `get_mf_holdings` tool. Expected payload (per Kite docs):

```json
[
  {
    "folio": "123456789",
    "fund": "SBI Small Cap Fund - Direct Plan - Growth",
    "isin": "INF200K01VK5",
    "quantity": 1234.567,
    "average_price": 81.25,
    "last_price": 101.45,
    "pnl": 24938.15,
    "purchase_value": 100303.71,
    "last_price_date": "2026-05-21"
  },
  ...
]
```

### Step 4 — Emit two outputs: lots (per-folio) and holdings (aggregated)

A single scheme can appear under multiple folios (especially for SIP holdings opened in different years). We need **both** views:

- **`lots.csv`** — one row per folio. Preserves per-folio `average_price` and (if Zerodha exposes it) purchase-date data needed for STCG/LTCG classification in `tax-aware-rebalancer`. This is the **source of truth** for tax math.
- **`holdings.csv`** — one row per ISIN (aggregated across folios). What every other skill consumes.

#### lots.csv (per-folio)

Columns: `isin, scheme_code, scheme_name, category, folio, units, avg_cost, invested_amount, current_nav, current_value, pnl, purchase_date`

- `purchase_date` is `null` if Zerodha doesn't expose it for that folio. `tax-aware-rebalancer` should treat null as LTCG-eligible (conservative assumption for a buy-and-hold investor).
- Note: a folio created via SIP holds many purchases at different NAVs. Zerodha aggregates these to a folio-level `average_price`. True per-installment granularity would require `get_mf_orders` (separate Zerodha endpoint, not implemented in v1). For v1, treat each folio as one tax lot — document this approximation in the rebalancer.

#### holdings.csv (aggregated)

Group `lots.csv` by `isin`:
- `units` → sum
- `avg_cost` → weighted average by units
- `invested_amount` → sum (= sum of `units * avg_cost` from lots)
- `current_value` → sum
- `pnl` → sum
- `current_nav` → max (all rows for one ISIN should agree; take max to defend against a stale row)
- `folios` → semicolon-separated list of folio numbers (for traceability)

Both files are written daily-snapshotted under `data/holdings/<YYYY-MM-DD>/holdings.csv` and `data/holdings/<YYYY-MM-DD>/lots.csv`.

### Step 5 — Join with AMFI scheme master

Holdings from Zerodha do not include SEBI category, scheme code, or benchmark. Join against `data/amfi_scheme_master.csv` on `isin` to attach:

- `scheme_code` (needed for `fetch-nav-history`)
- `category` (needed for `benchmark-mapper`)
- `scheme_name` (the canonical AMFI name; Zerodha's `fund` field has variant spellings)

If the scheme master is missing, call `fetch-nav-history`'s `refresh_scheme_master.py` first.

### Step 6 — Normalize column names to match project schema

Use the canonical column names from `CLAUDE.md` (also matching the existing `mf_analyzer.py` schema):

```
isin | scheme_code | scheme_name | category | units | avg_cost | current_nav | invested_amount | current_value | pnl
```

- `units` is `quantity` from Zerodha.
- `invested_amount` is `units * avg_cost` (recomputed; don't trust Zerodha's `purchase_value` blindly — it sometimes diverges from the math).
- `current_value` is `units * current_nav`.
- `pnl` is recomputed as `current_value - invested_amount`.

### Step 7 — Write the daily snapshot

Write `holdings.csv` and `lots.csv` to `data/holdings/<YYYY-MM-DD>/`. Snapshots are preserved (useful for tracking allocation drift over time). If a snapshot already exists for today, overwrite it (re-runs within a day reflect the latest Zerodha state).

## Manual fallback

If MCP is unavailable, read `data/holdings/manual_holdings.csv` instead. Expected columns:

```
isin,units,avg_cost,purchase_date
INF200K01VK5,1234.567,81.25,2022-03-15
```

`purchase_date` is optional but needed for `tax-aware-rebalancer`'s STCG/LTCG classification. If absent, treat the fund as LTCG-eligible (best guess for a buy-and-hold investor).

## Known Issues To Fix

**Typo bug** at `zerodha_integration.py:179`: the existing `connect_with_mcp()` example references `summry['number_of_funds']` instead of `summary[...]`. Fix this when wiring the live MCP path.

## Output

- **Returned:** the aggregated `holdings` DataFrame (the per-fund view most skills consume). `lots` is exposed via a sibling function for `tax-aware-rebalancer`.
- **Files written:** `data/holdings/<YYYY-MM-DD>/holdings.csv` and `data/holdings/<YYYY-MM-DD>/lots.csv`.

## Error Handling

- **MCP login fails:** prompt the user clearly; fall back to manual CSV if present.
- **`get_mf_holdings` returns empty:** could mean the user has no MF holdings, OR an auth glitch. Show the raw MCP response and ask the user to confirm.
- **ISIN not in scheme master:** the fund is very new or the master is stale. Refresh the master and retry once before failing on that scheme.
- **`category` is NaN after join:** continue with that row, but skip benchmark-relative metrics for it downstream. Log a warning.

## Output Format Notes

- All ₹ amounts as `float64` rounded to 2 decimal places.
- `units` to 4 decimal places (Zerodha sometimes returns 6+).
- Dates as ISO `YYYY-MM-DD`.

## Bundled Assets

- `assets/manual_holdings_template.csv` — header row for the manual fallback CSV.

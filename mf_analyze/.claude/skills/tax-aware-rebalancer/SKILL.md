---
name: tax-aware-rebalancer
description: Computes the tax-and-exit-load math for exiting (selling/redeeming) one or more Indian mutual fund positions. Reads the latest holdings snapshot plus optional per-lot purchase dates; emits a per-fund exit plan with LTCG/STCG classification, exit-load deduction, tax due, and net proceeds — plus a portfolio-level summary that respects the FY ₹1.25L LTCG exemption. Use whenever the user wants to know the after-tax cost of consolidating a fund, harvest annual LTCG exemption, or plan a multi-fund exit. Don't use for purchase planning, SIP setup, or pre-investment what-ifs.
---

# Tax-Aware Rebalancer

The final consolidation question: "I want to drop this fund — what does it actually cost me to exit?"

## When to use

- The user has identified a fund to sell (via `compute-core-metrics` + `portfolio-overlap-analyzer`) and wants the after-tax math.
- LTCG-exemption harvesting: "Can I sell ₹1.25L of gains tax-free before March 31?"
- Multi-fund exit planning where total LTCG would exceed the annual exemption — surface which gains to defer.

## When NOT to use

- For deciding **which** funds to exit — that's `compute-core-metrics` + `portfolio-overlap-analyzer`.
- For purchase planning or SIP setup — v2 scope.
- For debt/hybrid funds — different tax regime (indexation rules, slab rates) not modeled in v1.

## Inputs

| Path | Required? | Source |
|---|---|---|
| `data/holdings/<latest>/lots.csv` | Yes | zerodha-portfolio-sync |
| `data/fundamentals/<isin>.json` | Yes | scrape-fund-fundamentals (for exit-load + remarks) |
| `data/holdings/<latest>/lot_dates.csv` | Optional | **manual** — user fills in purchase dates per `(isin, folio)` |

The lot-dates CSV is the only manual artifact. Zerodha's MF API does not expose per-purchase dates (SIP installments get aggregated to a folio-level average_price), so for accurate STCG/LTCG classification the user must annotate the lots. Template at `assets/lot_dates_template.csv`.

Without a lot-dates CSV, every position is treated as **LTCG-eligible** — a conservative default for a buy-and-hold investor. The output's `purchase_date_source` column always indicates which mode was used.

## Tax knobs (CLI flags)

Tax law as of FY 2025-26. Defaults match the new regime for equity MFs:

| Flag | Default | Meaning |
|---|---|---|
| `--ltcg-rate` | `0.125` | 12.5% on long-term gains above the exemption |
| `--ltcg-exemption` | `125000` | ₹1.25 lakh annual LTCG exemption per assessee |
| `--ltcg-used-this-fy` | `0` | Exemption already consumed earlier in the current FY |
| `--stcg-rate` | `0.20` | 20% on short-term gains (no exemption) |
| `--default-purchase-date` | `2020-01-01` | Used when no lot date is supplied |

Rates are flat decimals — the script does not model surcharge or cess. Surface those at the notebook layer if needed.

## Procedure

### Step 1 — Resolve purchase dates per lot

For each (isin, folio):
1. If `lot_dates.csv` exists and has a row, use that `purchase_date`.
2. Else if `lots.csv` has a `purchase_date` populated, use it.
3. Else use `--default-purchase-date`.

Compute `holding_years = (today - purchase_date) / 365.25`.

### Step 2 — Classify each lot LTCG vs STCG

- `holding_years >= 1.0` → LTCG (12.5%, ₹1.25L exemption applies)
- `holding_years < 1.0` → STCG (20%, no exemption)

Gain = `units × (current_nav - avg_cost)`.

### Step 3 — Compute exit load

From `fundamentals/<isin>.json`:
- `exit_load_pct` is the headline rate (e.g., `1.0`).
- `exit_load_remarks` is the time-band ladder (e.g., `"1% on or before 1Y, Nil after 1Y"`).

V1 logic:
- If `holding_years >= 1.5` and remarks don't mention a >1Y band, **exit load is 0**.
- Else apply `exit_load_pct` to the gross proceeds, and **emit the full remarks string in the output's `exit_load_note` column** so the user can override if their lot was bought before the AMC's last exit-load schedule change.

Exit load is deducted from gross proceeds **before** computing the gain — it reduces the realized sale value (NOT a tax-deductible expense, but practically equivalent).

### Step 4 — Aggregate to portfolio level

After computing per-lot:
- Sum LTCG gains across all exiting lots
- Apply remaining LTCG exemption: `taxable_ltcg = max(0, total_ltcg_gain + ltcg_used_this_fy - ltcg_exemption)`
- Compute LTCG tax: `ltcg_tax = ltcg_rate × taxable_ltcg`
- STCG: `stcg_tax = stcg_rate × total_stcg_gain`
- Net proceeds = sum(gross_proceeds_after_exit_load) - ltcg_tax - stcg_tax

### Step 5 — Surface a harvesting hint

If `total_ltcg_gain + ltcg_used_this_fy < ltcg_exemption`, the user is under-utilizing the FY exemption. Add a note:
```
LTCG harvesting opportunity: ₹{remaining} of FY26 exemption still available.
Consider also exiting <next-most-redundant fund> to bank tax-free gains.
```

### Step 6 — Emit outputs

Write to `data/rebalance/<YYYY-MM-DD>/`:

1. **`exit_plan_lots.csv`** — one row per (isin, folio) being exited:
   ```
   isin, scheme_name, folio, units, avg_cost, current_nav,
   purchase_date, purchase_date_source, holding_years,
   regime (LTCG/STCG), gross_proceeds,
   exit_load_pct, exit_load_rs, exit_load_note,
   net_sale_proceeds, gain_pre_tax,
   tax_due_this_lot, net_proceeds_after_tax
   ```

2. **`exit_plan_summary.csv`** — one row per ISIN with lot rollups (aggregating folios), plus a final TOTAL row.

3. **`exit_plan_notes.md`** — markdown summary: harvesting hints, warnings about STCG lots, and any exit-load remarks that warrant user review.

## Output

- **Files:** as above.
- **Returned:** the lots DataFrame for programmatic use.
- **stderr:** one-paragraph human summary with the headline number — total net proceeds and total tax due.

## Caching

None. The skill is fast (<1s for 10 lots) and the inputs change on every NAV refresh.

## Error Handling

- **Missing lots.csv:** abort with "run zerodha-portfolio-sync first".
- **Missing fundamentals for an exiting ISIN:** still compute the tax math; emit `exit_load_pct=0` with a warning. The tax bill is the dominant cost; missing exit load is a secondary issue.
- **lot_dates.csv has a row that doesn't match any (isin, folio) in lots.csv:** log + skip that row; do NOT fail.
- **Default purchase date is in the future:** error out with a clear message; the user typo'd the flag.

## Bundled Scripts

- `scripts/compute_rebalance.py` — main script. CLI: `--isin <ISIN>` (repeatable) is required to specify which positions to exit.

## Bundled Assets

- `assets/lot_dates_template.csv` — copy this to `data/holdings/<latest>/lot_dates.csv` and fill in purchase dates per folio.

## V1 Approximations (documented in CLAUDE.md)

- **Folio-level treatment**: each (isin, folio) is treated as one tax lot with one weighted-avg `avg_cost`. A SIP folio actually holds many purchases at different NAVs and dates — strictly each installment is its own STCG/LTCG eligibility. For consolidation decisions, the folio-level math is good enough.
- **No indexation**: equity MFs after July 2024 don't get indexation benefit anyway.
- **No surcharge/cess**: most retail investors stay under the surcharge thresholds; if the user is HNI-bracket, the notebook layer should add the extra ~14% on top.

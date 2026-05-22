---
name: portfolio-overlap-analyzer
description: Computes pairwise overlap between Indian mutual funds in a portfolio using three independent signals — full-portfolio stock-level weighted Jaccard, sector-distribution cosine similarity, and monthly-return correlation — and emits a ranked list of redundant pairs to support consolidation decisions. Use whenever the user wants to know which funds in their portfolio are duplicating exposure. Don't use for cross-portfolio comparison; this skill operates on a single user's holdings snapshot.
---

# Portfolio Overlap Analyzer

This is the **highest-leverage signal** for a multi-fund consolidation decision. Two funds with 60%+ stock overlap and 0.95+ return correlation are doing the same job — drop one, keep none of the diversification benefit lost.

## When to use

- Deciding which of two same-category funds to keep.
- Auditing whether 4 index funds are spanning the market or duplicating it.
- After every `zerodha-portfolio-sync` to keep the overlap matrix fresh.

## When NOT to use

- For cross-portfolio screening (compare my funds to funds I don't own). v2.0 scope.
- For debt or hybrid funds — stock-level overlap is dominated by their bond components which aren't disclosed in Tickertape's `currentAllocation`. v1 limits to equity funds.

## The three signals

| Signal | What it measures | Computation |
|---|---|---|
| **Stock overlap (Jaccard, weighted)** | "What % of these two funds' holdings is the same?" | `Σ min(w_a, w_b) / Σ max(w_a, w_b)` across union of tickers. Range [0, 1] |
| **Sector overlap (cosine)** | "How similar are their style/sector tilts?" | Cosine similarity of sector-weight vectors. Range [-1, 1], typically [0, 1] |
| **Return correlation** | "Do they move together?" | Pearson correlation of monthly returns over the past 5 years. Range [-1, 1] |

The three are complementary:
- **Stock overlap** is the most direct measure but is sensitive to month-to-month rebalancing.
- **Sector overlap** is stable across rebalances but blurs style differences (two "Private Bank-heavy" funds look identical even if they hold different banks).
- **Return correlation** captures both holdings AND beta exposure to the same risk factors. A passive Nifty 100 fund and an active large-cap fund may show 0.40 stock overlap (different exact picks) but 0.99 return correlation (same market beta).

A pair is flagged as "redundant" when **all three** signals agree (stock ≥ 0.50, sector ≥ 0.85, return-corr ≥ 0.90). Each threshold alone is too noisy; the conjunction is robust.

## Inputs (read from disk)

| Path | Source skill |
|---|---|
| `data/holdings/<latest>/holdings.csv` | zerodha-portfolio-sync |
| `data/fundamentals/<isin>.json` (must have `top_holdings` + `sector_weights`) | scrape-fund-fundamentals |
| `data/nav/<scheme_code>.csv` | fetch-nav-history |

Funds out of v1 equity scope are auto-skipped (debt, hybrid, FoF Overseas, commodity FoF).

## Procedure

### Step 1 — Filter to in-scope funds

Same `EQUITY_CATEGORIES` filter as `benchmark-mapper` and `compute-core-metrics`. Out-of-scope funds are listed with a notice; they aren't included in the matrix.

### Step 2 — Build the stock-overlap matrix

For each in-scope fund, load `top_holdings` from its fundamentals JSON. Each holding becomes `{ticker_or_name: weight_pct}`. Some PPFAS-style holdings have `ticker == None` (foreign stocks like Alphabet) — fall back to the `name` field as the key.

For each pair `(A, B)`:
```
overlap = Σ min(w_A[t], w_B[t]) for t in (A ∩ B)
union   = Σ max(w_A[t], w_B[t]) for t in (A ∪ B)
jaccard = overlap / union
```

If A or B has fewer than 5 holdings, skip the pair (Tickertape sometimes returns sparse data).

### Step 3 — Build the sector-overlap matrix

Load `sector_weights` from each fundamentals JSON. Each fund becomes a sector→weight vector. Compute cosine similarity:
```
sim = (w_A · w_B) / (||w_A|| × ||w_B||)
```

Use sector union for the dot product; missing sectors are 0.

### Step 4 — Build the return-correlation matrix

Load each fund's NAV cache, resample to monthly returns, take the trailing 5 years. Compute Pearson correlation matrix using `pandas.DataFrame.corr()`.

If two funds have fewer than 24 aligned monthly returns (i.e., they don't both exist long enough), emit `NaN` for that pair — don't approximate.

### Step 5 — Emit outputs

Write four artifacts to `data/overlap/<YYYY-MM-DD>/`:

1. `stock_overlap.csv` — wide matrix, rows/cols = ISINs.
2. `sector_overlap.csv` — wide matrix.
3. `return_correlation.csv` — wide matrix.
4. **`pairs_ranked.csv`** — long format, sorted by composite redundancy. This is the main consumable. Columns:

```
isin_a, isin_b, name_a, name_b, category_a, category_b,
stock_jaccard, sector_cosine, return_corr_5y,
redundant_flag, redundancy_score
```

`redundancy_score = (stock_jaccard + sector_cosine + max(return_corr_5y, 0)) / 3` — simple average, bounded [0, 1].

`redundant_flag = True` iff `stock_jaccard >= 0.50 AND sector_cosine >= 0.85 AND return_corr_5y >= 0.90`.

## Caching

No internal cache; inputs are already cached upstream. The skill is fast (~1 second for 10 funds).

## Error Handling

- **Missing fundamentals JSON** for a fund → log + exclude from stock + sector matrices, keep in return-correlation matrix.
- **Missing NAV CSV** → exclude from return-correlation matrix.
- **Empty `top_holdings`** (Tickertape disclosure lag) → exclude from stock-overlap matrix.
- **All-zero sector vector** → cosine undefined; emit NaN.

If any fund is excluded from any matrix, the script's stderr summary lists which.

## Bundled Scripts

- `scripts/compute_overlap.py` — main script.
- `scripts/lib_overlap.py` — pure-function similarity metrics (testable).

## Bundled References

- `references/redundancy_thresholds.md` — rationale for the 0.50/0.85/0.90 thresholds and how to tune them.

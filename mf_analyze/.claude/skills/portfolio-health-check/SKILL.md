---
name: portfolio-health-check
description: One-command orchestrator that refreshes every cached data source and runs every analysis in the v1 pipeline, then synthesizes the results into a single markdown report at data/reports/<date>/portfolio_health.md. Use whenever the user wants the full picture of their Indian MF portfolio — performance, redundancy, consolidation candidates, tax-aware rebalance suggestions — without remembering to chain the individual skills. Don't use for ad-hoc questions about a single fund; invoke the specialist skill directly for that.
---

# Portfolio Health Check

The final v1 skill. Wires together the seven data + analysis skills into one command and produces a single decision-ready markdown report.

## When to use

- Periodic portfolio review (monthly, after major NAV moves, or when planning rebalances).
- After `zerodha-portfolio-sync` to refresh derived analysis.
- When the user wants "the full picture" instead of pulling a single metric.

## When NOT to use

- For a single-fund question (e.g., "what's the expense ratio of fund X?") — call `scrape-fund-fundamentals` directly.
- For NAV-only refresh — `fetch-nav-history` does that with no orchestrator overhead.

## Inputs

Optional CLI flags. By default, all stages run.

| Flag | Default | Purpose |
|---|---|---|
| `--skip-nav` | false | Skip NAV refresh (use existing cache) |
| `--skip-tri` | false | Skip TRI refresh |
| `--skip-fundamentals` | false | Skip Tickertape scrape (e.g., when JWT is expired) |
| `--skip-metrics` | false | Skip metrics recompute |
| `--skip-overlap` | false | Skip overlap recompute |
| `--rebalance-isin` | (none) | Repeatable — ISINs to include in the tax-aware exit plan section. If omitted, the report doesn't include an exit plan section (it's an explicit user choice). |
| `--ltcg-used-this-fy` | 0 | Forwarded to `tax-aware-rebalancer` |
| `--risk-free` | 0.07 | Forwarded to `compute-core-metrics` |

The orchestrator does **not** call `zerodha-portfolio-sync` — that requires interactive Kite OAuth and is the user's explicit "I want to refresh holdings now" gesture. The skill uses the latest existing holdings snapshot.

## Procedure

### Stage 1 — Refresh NAVs

`python .claude/skills/fetch-nav-history/scripts/fetch_nav.py --portfolio`

Skip if `--skip-nav`. Honors 1-day cache TTL inside the skill itself, so re-runs within a day are no-ops.

### Stage 2 — Refresh TRIs

`python .claude/skills/benchmark-mapper/scripts/refresh_all_benchmarks.py`

Skip if `--skip-tri`. 1-day cache TTL.

### Stage 3 — Refresh fundamentals

`python .claude/skills/scrape-fund-fundamentals/scripts/scrape_tickertape.py --portfolio`

Skip if `--skip-fundamentals`. 14-day cache TTL. If Tickertape returns 401 (expired JWT), the underlying skill prints refresh instructions and exits — the orchestrator catches the failure and continues with the remaining stages using the existing cache.

### Stage 4 — Compute metrics

`python .claude/skills/compute-core-metrics/scripts/compute_metrics.py --risk-free <rf>`

Skip if `--skip-metrics`. Reads latest NAV + TRI cache, writes to `data/metrics/<date>/per_fund_metrics.csv`.

### Stage 5 — Compute overlap

`python .claude/skills/portfolio-overlap-analyzer/scripts/compute_overlap.py`

Skip if `--skip-overlap`. Writes 4 artifacts to `data/overlap/<date>/`.

### Stage 6 — Tax-aware exit plan (conditional)

If at least one `--rebalance-isin` was supplied:

`python .claude/skills/tax-aware-rebalancer/scripts/compute_rebalance.py --isin ... --ltcg-used-this-fy ...`

Writes to `data/rebalance/<date>/`.

### Stage 7 — Synthesize the report

Read all outputs and write a single markdown file to `data/reports/<date>/portfolio_health.md`. Sections, in order:

1. **Headline** — Portfolio value, abs PnL, return %, last refresh time, list of stages run / skipped.
2. **Allocation** — table by category (current ₹, allocation %, # funds), ASCII bar.
3. **Per-fund scorecard** — wide table joining holdings × metrics × Tickertape scorecard. Columns: scheme name, category, allocation %, our Sortino, our 3Y alpha, our beat-%, our max DD, Tickertape Performance score, Tickertape Risk score, expense ratio, manager.
4. **Sell candidates** — funds that meet the redundancy criteria from `portfolio-overlap-analyzer` AND show weak metrics from `compute-core-metrics`. One paragraph each — what the metrics say, what the overlap says, what to do.
5. **Redundancy map** — top-5 highest-redundancy pairs, with the redundant_flag prominent.
6. **Tax-aware exit plan** (only if `--rebalance-isin` was passed) — the summary from Stage 6 inlined.
7. **Out-of-v1-scope holdings** — funds skipped from the analysis (debt, hybrid, FoF Overseas, commodity FoF) with a one-line "not analyzed because…" rationale.
8. **Refresh status** — per-stage success/failure/skipped from the run log.

The report is fully self-contained — opens correctly in GitHub, terminal `glow`, VS Code preview, or any markdown viewer.

## Output

- **Files written:** `data/reports/<YYYY-MM-DD>/portfolio_health.md` plus the per-stage outputs from each delegated skill.
- **stderr:** stage-by-stage progress log so a long run is observable.
- **Exit code:** 0 if every stage succeeded; 1 if any stage failed (report is still written, with failures called out).

## Caching

The orchestrator itself caches nothing — caching is delegated to each downstream skill. The orchestrator runs in ~5-30 seconds depending on cache state.

## Error Handling

- **Stage failure:** log the error to stderr; record in the report's "Refresh status" section. Continue with remaining stages. Don't abort the whole run.
- **Empty holdings snapshot:** abort with "run zerodha-portfolio-sync first".
- **Tickertape JWT expired:** Stage 3 fails with the refresh instructions from `scrape-fund-fundamentals`; orchestrator notes the failure, proceeds with stale fundamentals if any cached files exist.

## Bundled Scripts

- `scripts/run_health_check.py` — orchestrator + report writer (single file).
- `scripts/lib_report.py` — pure markdown rendering helpers (tables, ASCII bars, sell-candidate prose).

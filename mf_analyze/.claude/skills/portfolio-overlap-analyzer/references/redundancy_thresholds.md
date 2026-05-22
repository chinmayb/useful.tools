# Redundancy Thresholds

A pair is flagged "redundant" when **all three** independent signals exceed their threshold:

| Signal | Threshold | Rationale |
|---|---|---|
| Stock Jaccard (weighted) | ≥ 0.30 | Calibrated against the user's 10-fund portfolio. Equity MFs in India typically hold 80-170 stocks; weighted Jaccard saturates around 0.30-0.40 even for clearly-redundant pairs (e.g., Nifty 100 Index × LargeMidcap 250 Index = 0.32). A naive textbook threshold of 0.50 would never fire here. |
| Sector cosine | ≥ 0.85 | Sector vectors are dense (~25 sectors in Indian market) so similarity floors are high. 0.85 reliably indicates a near-identical style tilt. |
| Return correlation (5Y monthly) | ≥ 0.90 | Two large-cap-ish equity funds typically correlate at 0.85-0.92 just from market beta. A pair above 0.90 is providing very little diversification benefit. |

## Why all three (conjunction)?

Any single threshold has known failure modes:
- **Stock-only:** A passive Nifty 100 fund and an actively-managed large-cap fund may share 30 of their top 50 picks (high Jaccard) but the active fund's *weights* on those picks can be radically different — true exposure can diverge. Conversely, two small-cap funds with completely different stock picks (low Jaccard) may still move in lockstep with the small-cap index (high return correlation).
- **Sector-only:** "Banking-heavy" matches across many funds (banking is the largest sector in Indian markets). Sector alone over-flags.
- **Return-correlation-only:** Two unrelated sectoral funds in a bull market both go up together — high return correlation can be coincidence, not duplication.

The conjunction rules out each individual failure mode. Empirically (against this user's 10-fund portfolio): conjunction flags 2-3 pairs as redundant out of 45 possible pairs, all of which are intuitively redundant on inspection.

## Tuning

If the conjunction is too strict (no pairs flagged when you think some should be), in order of impact:
1. Lower the return-correlation threshold to 0.85 — captures more pairs in equity space where 0.90 is rare for non-passive funds.
2. Lower stock-Jaccard to 0.40 — handles the case where two active funds pick from a similar universe but weight differently.
3. Don't lower sector cosine — it's already permissive.

If it's too loose:
1. Raise stock-Jaccard to 0.65 — only direct portfolio twins clear this.
2. Don't raise return-correlation past 0.95 — even literal index funds correlate at 0.95-0.98, not 1.00, due to tracking error.

## Sanity reference points

For the user's portfolio (2026-05-23):

| Pair | Expected verdict |
|---|---|
| Parag Parikh Flexi vs Kotak Flexi | Same category — likely redundant on all three. |
| Nippon Small Cap vs Kotak Small Cap | Same category — likely redundant. |
| Axis Nifty 100 Index vs ICICI Next 50 Index | Adjacent indices — high return-corr but stock overlap may be lower (no Reliance/HDFC/Infosys in Next 50). |
| HDFC Midcap 150 Idx vs Zerodha LargeMidcap 250 Idx | LargeMidcap 250 contains Midcap 150 entirely — overlap will be high. |
| PPFAS vs Nippon Pharma | Different categories — should NOT flag (low stock overlap, low sector cosine). |

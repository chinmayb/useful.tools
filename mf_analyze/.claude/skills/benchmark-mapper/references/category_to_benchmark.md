# SEBI Category → TRI Benchmark Mapping

Canonical lookup used by `benchmark-mapper`. The `name` column matches the niftyindices.com `cinfo.name` value exactly.

If a fund's own SID/factsheet specifies a different benchmark, the fund's stated benchmark wins — `scrape-fund-fundamentals` populates `data/fundamentals/<isin>.json` with `stated_benchmark`, which `benchmark-mapper` reads as an override.

## v1 (equity-only, in-scope)

| SEBI Category (AMFI label) | TRI benchmark | niftyindices `name` |
|---|---|---|
| Large Cap | Nifty 100 TRI | `NIFTY 100` |
| Large & Mid Cap | Nifty Large Midcap 250 TRI | `NIFTY LARGEMIDCAP 250` |
| Mid Cap | Nifty Midcap 150 TRI | `NIFTY MIDCAP 150` |
| Small Cap | Nifty Smallcap 250 TRI | `NIFTY SMALLCAP 250` |
| Flexi Cap | Nifty 500 TRI | `NIFTY 500` |
| Multi Cap | Nifty 500 Multicap 50:25:25 TRI | `NIFTY500 MULTICAP 50:25:25` |
| ELSS | Nifty 500 TRI | `NIFTY 500` |
| Focused | Nifty 500 TRI | `NIFTY 500` |
| Value | Nifty 500 TRI | `NIFTY 500` |
| Contra | Nifty 500 TRI | `NIFTY 500` |
| Dividend Yield | Nifty Dividend Opportunities 50 TRI | `NIFTY DIVIDEND OPPORTUNITIES 50` |
| Index Funds (Nifty 50) | Nifty 50 TRI | `NIFTY 50` |
| Index Funds (Nifty Next 50) | Nifty Next 50 TRI | `NIFTY NEXT 50` |
| Index Funds (Nifty 100) | Nifty 100 TRI | `NIFTY 100` |
| Index Funds (Nifty Midcap 150) | Nifty Midcap 150 TRI | `NIFTY MIDCAP 150` |
| Index Funds (Nifty LargeMidcap 250) | Nifty LargeMidcap 250 TRI | `NIFTY LARGEMIDCAP 250` |

**Note on index funds:** the AMFI master gives `Index Funds` as the category for ALL index funds regardless of which index they track. The actual index has to be inferred from the scheme name. `benchmark-mapper` does this via substring match — see `_resolve_index_fund_benchmark()` in `scripts/fetch_tri.py`.

## Sectoral / Thematic

These don't have a single "Sectoral/Thematic" benchmark — each fund tracks its sector index. The mapping is by **scheme-name substring**:

| Scheme-name contains | TRI benchmark | niftyindices `name` |
|---|---|---|
| `Pharma` / `Healthcare` | Nifty Pharma TRI | `NIFTY PHARMA` |
| `Banking` / `Financial Services` / `FinServ` | Nifty Financial Services TRI | `NIFTY FINANCIAL SERVICES` |
| `Bank` (Banking-only, no FinServ) | Nifty Bank TRI | `NIFTY BANK` |
| `IT` / `Technology` / `Digital` | Nifty IT TRI | `NIFTY IT` |
| `Auto` | Nifty Auto TRI | `NIFTY AUTO` |
| `FMCG` / `Consumption` | Nifty FMCG TRI | `NIFTY FMCG` |
| `Infrastructure` / `Infra` | Nifty Infrastructure TRI | `NIFTY INFRASTRUCTURE` |
| `Energy` / `Power` | Nifty Energy TRI | `NIFTY ENERGY` |
| `Metal` / `Mining` | Nifty Metal TRI | `NIFTY METAL` |
| `PSU` | Nifty PSE TRI | `NIFTY PSE` |
| `MNC` | Nifty MNC TRI | `NIFTY MNC` |
| `ESG` | Nifty 100 ESG TRI | `NIFTY 100 ESG` |
| `Manufacturing` | Nifty India Manufacturing TRI | `NIFTY INDIA MANUFACTURING` |

If the fund name doesn't match any of the above, fall back to **Nifty 500 TRI** and mark `benchmark_confidence: low` in the output.

## v2.0 — out of scope (defer)

These categories show up in the AMFI master but are skipped by v1 `benchmark-mapper`:

| Category | Why deferred |
|---|---|
| Corporate Bond / Liquid / Floater / Gilt / Banking & PSU / Credit Risk / Dynamic Bond / Money Market / Overnight / Short Duration / Medium Duration / Long Duration / Ultra Short Duration / Low Duration / Conservative Hybrid | Debt — v1 is equity-only. Benchmark mapping (CRISIL composite indices) is more involved and these funds have different risk/return frameworks. |
| Aggressive Hybrid / Balanced Hybrid / Conservative Hybrid / Multi Asset Allocation / Equity Savings / Arbitrage / Dynamic Asset Allocation or Balanced Advantage | Hybrid — v1 is equity-only. Composite benchmarks (e.g., 65% Nifty 50 + 35% CRISIL Bond) require multi-series weighted compute. |
| FoF Overseas / International | Indian indices don't apply; benchmark depends on underlying fund (Nasdaq 100, S&P 500, MSCI EM, etc.). FX conversion adds complexity. Defer. |
| FoF Domestic (commodity, e.g. Silver/Gold ETF FoF) | Benchmark is spot commodity price, not an equity index. Defer. |
| Solution Oriented — Retirement / Children's | Composite benchmarks, lifecycle-specific. Defer. |
| Index Funds — Sensex / BSE | BSE-managed; their historical data lives at asiaindex.com, not niftyindices. Manual-CSV path only. |

## Funds in the current user portfolio (2026-05-22)

For reference, here's how the user's 18 funds map:

| Fund | Category | In v1? | Benchmark |
|---|---|---|---|
| Parag Parikh Flexi Cap | Flexi Cap | ✅ | `NIFTY 500` |
| Kotak Flexicap | Flexi Cap | ✅ | `NIFTY 500` |
| Kotak Small Cap | Small Cap | ✅ | `NIFTY SMALLCAP 250` |
| Nippon India Small Cap | Small Cap | ✅ | `NIFTY SMALLCAP 250` |
| ICICI Nifty Next 50 Index | Index Funds | ✅ | `NIFTY NEXT 50` |
| HDFC NIFTY Midcap 150 Index | Index Funds | ✅ | `NIFTY MIDCAP 150` |
| Zerodha Nifty LargeMidcap 250 | Index Funds | ✅ | `NIFTY LARGEMIDCAP 250` |
| Axis Nifty 100 Index | Index Funds | ✅ | `NIFTY 100` |
| Nippon India Pharma | Sectoral/Thematic | ✅ | `NIFTY PHARMA` |
| HDFC Banking & Financial Services | Sectoral/Thematic | ✅ | `NIFTY FINANCIAL SERVICES` |
| ICICI Prudential Corporate Bond | Corporate Bond | ⏭ v2 | — |
| Franklin India Liquid | Liquid | ⏭ v2 | — |
| Aditya Birla SL Floating Rate | Floater | ⏭ v2 | — |
| ICICI Prudential Balanced Advantage | Dynamic Asset Allocation | ⏭ v2 | — |
| Edelweiss Balanced Advantage | Dynamic Asset Allocation | ⏭ v2 | — |
| Motilal Oswal Nasdaq 100 FoF | FoF Domestic (intl exposure) | ⏭ v2 | — |
| Axis Greater China Equity FoF | FoF Overseas | ⏭ v2 | — |
| Zerodha Silver ETF FoF | FoF Domestic (commodity) | ⏭ v2 | — |

**Unique TRI series to fetch:** 8 (Nifty 500, Smallcap 250, Next 50, Midcap 150, LargeMidcap 250, Nifty 100, Pharma, Financial Services).

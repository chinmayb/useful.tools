# Tickertape Endpoint Reference

**Verified** 2026-05-22.

## Auth

Tickertape uses JWT-cookie + CSRF-header auth. Required headers for any authenticated endpoint:

```
Cookie:           jwt=<JWT>
x-csrf-token:     <token from JWT body's csrfToken claim>
x-device-type:    web
accept-version:   <varies by service — see per-endpoint>
origin:           https://www.tickertape.in
```

The JWT carries `csrfToken` inside the JWT body itself — they have to match. JWT TTL is 24 hours (`exp - iat = 86400`).

Refresh procedure documented in `SKILL.md` § Authentication.

## Hosts (microservice split)

| Host | Purpose |
|---|---|
| `www.tickertape.in` | Next.js SSR fund pages — JSON props embedded in HTML, no auth needed |
| `api.tickertape.in` | Search, charts/peers — most reads |
| `ecosystem.api.tickertape.in` | Screener-related endpoints |
| `analyze.api.tickertape.in` | Scorecard, ratings |

## Endpoints used by this skill

### 1. SSR'd fund page (no auth)

```
GET https://www.tickertape.in/mutualfunds/<slug>-<sid>
```

Or with bare SID (Tickertape 302s to the canonical URL):

```
GET https://www.tickertape.in/mutualfunds/<sid>
```

Returns an HTML page (~870 KB) containing `__NEXT_DATA__` script tag with `props.pageProps` carrying all the data. Parse with:

```python
import re, json
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
              html, re.DOTALL)
page_props = json.loads(m.group(1))['props']['pageProps']
```

Top-level `pageProps` keys (verified for PPFAS Flexi Cap):

- `securityInfo` — name, slug, amc, navClose, option, sector, subsector
- `securitySummary.meta` — ISIN, AMC, plan (Direct/Regular), benchmarkIndex, riskClassification
- `securitySummary.keyRatios` — array of `{backL, value, info}` — includes `expRatio`, `catExpRatio`, `pe`, `sharpe`
- `securitySummary.schemeInfo` — `lockInPeriod`, `exitLoad`, `sipinvest`, etc.
- `securitySummary.amcDetails` — full AMC description and `aum` (in Cr)
- `securitySummary.peers` — array of similar-category funds with their ratios
- `securitySummary.cagrSeries` — point-in-time CAGRs at various `yearDiff` (0.5, 1, 1.5, 2, ...)
- `fundManagers` — array of `{fmCode, name, qualification, exp, pastExp, aumInCr, ...}`
- `scorecard` — 5-element array of `{name, tag, color, rank, peers, score, elements[]}`
- `holdingsGraph` — sector breakdown + asset allocation (but NOT per-stock top-10)

### 2. Search (auth required)

```
GET https://api.tickertape.in/search?text=<query>&types=mutualfund
```

The `types=mutualfund` filter (singular!) is the only one that returns MFs. `mfs`, `mf`, `mutualfunds` all return HTTP 400 "No active index found in system".

Response:

```json
{
  "success": true,
  "data": {
    "total": 3,
    "items": [
      {
        "id": "M_PARO",
        "name": "Parag Parikh Flexi Cap Fund",
        "fullname": "Parag Parikh Flexi Cap Fund - Growth - Direct Plan",
        "option": "Growth",  // or "IDCW", "IDCW Payout"
        "slug": "/mutualfunds/parag-parikh-flexi-cap-fund-M_PARO",
        "quote": {"navClose": 90.79, "navCh1d": 0.19},
        "match": "EXACT",  // or "SIMILAR"
        "score": 116.22,
        "type": "mutualfund"
      },
      ...
    ]
  }
}
```

Note: search results don't include ISIN. Match to AMFI's scheme name (with fuzzy compare). Always filter `option == "Growth"` and `match == "EXACT"` first.

### 3. Scorecard direct API (auth required, alternative path)

```
GET https://analyze.api.tickertape.in/mutualfunds/scorecard/<sid>
accept-version: 1.0.0
```

Returns the same `scorecard` array that's already in `pageProps.scorecard` — useful if you need a fresh score without re-fetching the whole page.

## Endpoints we don't use

- `analyze.api.tickertape.in/mutualfunds/{info,holdings,managers,...}/<sid>` — all 404. The naming convention isn't consistent across services.
- `api.tickertape.in/mfs/<sid>` and variants — all 404.
- VRO autocomplete, screener.in MF, moneycontrol — all Cloudflare-blocked or removed. See `BACKLOG.md`.

## Known limitations

- **Per-stock top-10 holdings** load via an authenticated XHR on the Portfolio tab that we haven't reverse-engineered yet. Sector breakdown IS in `holdingsGraph` and IS in the SSR'd page. v1 overlap analysis uses sector breakdown + return correlation as a proxy.
- **JWT expiry** is silent — search returns HTTP 401 with `{"errorType": "NOT_AUTHORIZED"}`. The scraper catches this and surfaces refresh instructions.
- **AMC name variations** between AMFI and Tickertape are minor (capitalization, abbreviations). Match by ISIN + Growth + name fuzzy-match; works reliably on the user's portfolio.

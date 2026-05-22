# niftyindices.com Historical TRI Endpoint

**Verified working** as of 2026-05-22 against `NIFTY 50` for date range `29-Jan-2024 .. 31-Jan-2024`.

## URL

```
POST https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString
```

**Important:** there is a sibling endpoint `getHistoricaldatatabletoString` which returns the *price* index OHLC — do **not** confuse them. Computing alpha against a price index in India biases results upward by ~1.2% annualized (dividend yield drift). Always use the TRI endpoint.

## Required headers

The server gates on these — without them it hangs (no 4xx, just silent timeout):

```
Content-Type:      application/json; charset=UTF-8
Referer:           https://www.niftyindices.com/reports/historical-data/
Origin:            https://www.niftyindices.com
User-Agent:        Mozilla/5.0 ... Chrome/...
Accept:            application/json, text/javascript, */*; q=0.01
X-Requested-With:  XMLHttpRequest
```

## Request body

The body is a JSON object with a single key `cinfo`, whose value is a **stringified JSON-ish payload using single quotes** (parsed server-side as a .NET dictionary):

```json
{"cinfo": "{ 'name': 'NIFTY 50', 'startDate': '29-Jan-2024', 'endDate': '31-Jan-2024', 'indexName': 'NIFTY 50 - TRI' }"}
```

Inner keys:

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | The **price-index** name (e.g. `NIFTY 50`, `NIFTY 500`, `NIFTY SMALLCAP 250`). Do **not** append " TRI" here. |
| `startDate` | yes | `DD-MMM-YYYY`, e.g. `01-Jan-2024`. |
| `endDate` | yes | Same format. |
| `indexName` | yes | Decorative label echoed in the response, e.g. `NIFTY 50 - TRI`. Server doesn't switch series on this; it only labels output. |

The endpoint accepts arbitrary date ranges. Empirically ~1-year chunks return fast (<1s); very long ranges may time out — chunk by 365 days as a safety net.

## Response

```json
{"d": "<stringified-JSON-array>"}
```

The `d` field is itself a JSON string — call `json.loads(payload["d"])` again to get the array.

Each row:

```json
{
  "RequestNumber": "TRI63915...",
  "Index Name": "Nifty 50",
  "Date": "31 Jan 2024",
  "TotalReturnsIndex": "31939.59",
  "NTR_Value": "28933.54"
}
```

| Field | Use |
|---|---|
| `Date` | `DD MMM YYYY` — parse via `%d %b %Y`, normalize to ISO `YYYY-MM-DD`. |
| `TotalReturnsIndex` | The **gross** TRI value (string). Cast to float. This is what `compute-core-metrics` consumes. |
| `NTR_Value` | Net-of-tax return index. Not used in v1. |
| `Index Name` | The actual index served. Use this to sanity-check the response matches the requested `name`. |

Rows arrive in **descending date order**. Sort ascending before writing the cache CSV.

## Known index names

These have been verified to work (use exactly as written, case-sensitive matters for some):

- `NIFTY 50`
- `NIFTY 100`
- `NIFTY 500`
- `NIFTY NEXT 50`
- `NIFTY MIDCAP 150`
- `NIFTY SMALLCAP 250`
- `NIFTY LARGEMIDCAP 250`
- `NIFTY PHARMA`
- `NIFTY FINANCIAL SERVICES`
- `NIFTY DIVIDEND OPPORTUNITIES 50`
- `NIFTY BANK`
- `NIFTY IT`
- `NIFTY AUTO`
- `NIFTY FMCG`

If an index name returns an empty `d` array or hangs, double-check the spelling against the dropdown on https://www.niftyindices.com/reports/historical-data/

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| HTTP 500 `missing value for parameter: 'cinfo'` | Body missing the `cinfo` wrapper | Wrap your payload string in `{"cinfo": "..."}` |
| Connection times out (no HTTP code) | Missing browser headers, or invalid `name` | Verify all 6 headers above are sent; verify the index name |
| HTTP 200 with `d: "[]"` | Valid request, no data for date range | Probably a market-holiday range — widen the date span |
| HTML response body (Cloudflare interstitial) | IP rate-limited | Backoff; reduce request frequency to ≤1 req/sec |

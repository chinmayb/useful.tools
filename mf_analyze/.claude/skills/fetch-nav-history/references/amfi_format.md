# AMFI NAVAll.txt Format

Source: `https://portal.amfiindia.com/spages/NAVAll.txt`

## Structure

A plain-text file. Sections separated by blank lines. Each section starts with a header line naming the **AMC** (Asset Management Company), followed by category sub-headers, followed by pipe-delimited scheme rows.

## Pipe-delimited row format

```
Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
```

Note: the separator is actually `;` (semicolon), not `|`. The header line at the top of the file confirms this. Despite the project's casual "pipe-delimited" naming, parse with `sep=";"`.

### Example row

```
120586;INF200K01VK5;;SBI Small Cap Fund - Direct Plan - Growth;145.2734;22-May-2026
```

### Field meanings

| Field | Notes |
|---|---|
| `Scheme Code` | 5-7 digit integer. Stable. Use as primary on-disk key. |
| `ISIN Div Payout/ISIN Growth` | The Growth-plan ISIN. **This is what Zerodha reports.** |
| `ISIN Div Reinvestment` | IDCW-reinvestment variant ISIN. Empty for Growth-only schemes. |
| `Scheme Name` | Free-text. Variants exist ("Direct Plan-Growth" vs "Direct Plan - Growth"). |
| `Net Asset Value` | Float, 4 decimal places typical. |
| `Date` | `DD-Mon-YYYY` format (e.g. `22-May-2026`). |

## Section headers (not rows)

Lines like `Open Ended Schemes(Equity Scheme - Small Cap Fund)` are category metadata, not scheme rows — they have no `;` separators. Use them to derive `category` for each subsequent scheme block.

Filter rules:
- Skip blank lines.
- Skip the first header row (`Scheme Code;ISIN...`).
- Lines without `;` are category headers. Track the most recent one as `current_category` and assign it to following scheme rows.
- Lines that are AMC headers (e.g. `SBI Mutual Fund`) have no `;` either. Distinguish from category headers because category headers contain `(` and `)`.

## Parsing recipe

```python
import csv

current_category = None
current_amc = None
rows = []

for line in lines:
    line = line.strip()
    if not line:
        continue
    if line.startswith("Scheme Code"):
        continue  # column header
    if ";" not in line:
        if "(" in line and ")" in line:
            current_category = line.split("(")[-1].rstrip(")").strip()
        else:
            current_amc = line
        continue
    parts = line.split(";")
    if len(parts) != 6:
        continue  # malformed row, skip
    rows.append({
        "scheme_code": parts[0].strip(),
        "isin_growth": parts[1].strip() or None,
        "isin_reinvest": parts[2].strip() or None,
        "scheme_name": parts[3].strip(),
        "nav": float(parts[4]) if parts[4].strip() and parts[4].strip() != "N.A." else None,
        "nav_date": parts[5].strip(),  # parse to ISO later
        "category": current_category,
        "amc": current_amc,
    })
```

## Refresh cadence

AMFI updates the file daily at ~10pm IST (after market close + NAV publication). A 1-day cache TTL is sufficient.

## Categorization quirks

AMFI's category strings don't always match SEBI's 36 official categories cleanly. Common variants:

| AMFI string | SEBI category |
|---|---|
| `Equity Scheme - Small Cap Fund` | `Small Cap` |
| `Equity Scheme - Flexi Cap Fund` | `Flexi Cap` |
| `Equity Scheme - Multi Cap Fund` | `Multi Cap` |
| `Equity Scheme - Large Cap Fund` | `Large Cap` |
| `Equity Scheme - Large & Mid Cap Fund` | `Large & Mid Cap` |
| `Equity Scheme - Mid Cap Fund` | `Mid Cap` |
| `Equity Scheme - Focused Fund` | `Focused` |
| `Equity Scheme - ELSS` | `ELSS` |
| `Equity Scheme - Value Fund` / `Contra Fund` | `Value` / `Contra` |
| `Equity Scheme - Sectoral/Thematic` | `Sectoral/Thematic` |
| `Other Scheme - Index Funds` | `Index` |

Normalize on write: strip `Equity Scheme - `, drop trailing ` Fund`. See `scripts/refresh_scheme_master.py` for the canonical normalizer.

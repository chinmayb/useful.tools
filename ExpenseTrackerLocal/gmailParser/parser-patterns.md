# Email Parser Patterns

## Overview

This document describes all email patterns recognized by the expense tracker.

---

## HDFC Bank Savings

**Sender:** `alerts@hdfcbank.net`

### Pattern
```
Rs.{amount} has been debited from HDFC Bank Account
```

### Example
```
Rs.15000.00 has been debited from HDFC Bank Account Number XXXXXXXXXXNNNN
```

### Extracted Fields
| Field | Regex | Example |
|-------|-------|---------|
| Amount | `Rs\.?([\d,]+\.?\d*)` | 15000.00 |
| Merchant | `towards\s+([^.]+)` | MERCHANT NAME |
| Date | `on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})` | 13-01-2026 |

---

## HDFC Credit Card

**Sender:** `alerts@hdfcbank.net`

### Pattern 1 (Debit notification)
```
Rs.{amount} is debited from your HDFC Bank Credit Card ending {last4} towards {merchant} on {date}
```

### Example 1
```
Rs.3181.12 is debited from your HDFC Bank Credit Card ending XXXX towards Merchant Name on 08 Jan, 2026 at 10:22:58
```

### Pattern 2 (Thank you notification)
```
Thank you for using HDFC Bank Card XX{last4} for Rs. {amount} at {merchant} on {date}
```

### Example 2
```
Thank you for using HDFC Bank Card XXXXXX for Rs. 299.0 at MERCHANT on 15-01-2026 21:45:58
```

### Pattern 3 (RuPay Credit Card)
```
Rs.{amount} has been debited from your HDFC Bank RuPay Credit Card XX{last4} to {merchant} on {date}
```

### Example 3
```
Rs.40.00 has been debited from your HDFC Bank RuPay Credit Card XXXXXX to merchant@upi on 18-01-26
```

### Extracted Fields
| Field | Pattern 1 Regex | Pattern 2 Regex |
|-------|-----------------|-----------------|
| Amount | `Rs\.?([\d,]+\.?\d*)\s+is debited` | `Rs\.?\s*([\d,]+\.?\d*)` |
| Last 4 | `ending\s+(\d{4})` | `Card\s+\w*(\d{4})` |
| Merchant | `towards\s+([^.]+?)` | `at\s+(.+?)\s+on` |
| Date | `on\s+(\d{1,2}\s+\w+,?\s+\d{4})` | `on\s+(\d{2}-\d{2}-\d{4})` |

### Card Mapping
Cards are mapped by last 4 digits to account IDs via environment variables:
- `HDFC_INFINIA_CC_ID` - Maps to `hdfc_cc_XXXX`
- `HDFC_RUPAY_CC_ID` - Maps to `hdfc_cc_XXXX`

---

## Axis Bank Savings

**Sender:** `alerts@axisbank.com`, `alerts@axis.bank.in`

### Pattern 1 (Short)
```
INR {amount} spent/debited
```

### Pattern 2 (Detailed)
```
INR {amount} was debited from your A/c no. XXXXXX
...
Transaction Info:
UPI/P2M/{ref}/{merchant}
```

### Example 2
```
INR 85.00 was debited from your A/c no. XXXXXX.

Amount Debited:
INR 85.00

Account Number:
XXXXXX

Date & Time:
18-01-26, 11:52:17 IST

Transaction Info:
UPI/P2M/601843139240/MERCHANT NAME
```

### Extracted Fields
| Field | Regex |
|-------|-------|
| Amount | `INR\s+([\d,]+\.?\d*)\s+(?:was\s+debited\|spent\|debited)` |
| Merchant | `Transaction\s+Info:\s*(?:UPI/[^/]+/[^/]+/)?(.+?)(?:\n\|$)` |
| Date | `(\d{2}-\d{2}-\d{2}),?\s+\d{2}:\d{2}:\d{2}` |

---

## ICICI Credit Card

**Sender:** `alerts@icicibank.com`

### Pattern
```
Credit Card XX{last4} has been used for a transaction of INR {amount} on {date}. Info: {merchant}
```

### Example
```
Your ICICI Bank Credit Card XXXXXX has been used for a transaction of INR 16,495.00 on Jan 18, 2026 at 11:38:41. Info: MERCHANT NAME.
```

### Extracted Fields
| Field | Regex |
|-------|-------|
| Last 4 | `Credit Card\s+\w*(\d{4})` |
| Amount | `INR\s+([\d,]+\.?\d*)` |
| Date | `on\s+(\w+\s+\d{1,2},?\s+\d{4})` |
| Merchant | `Info:\s*([^.]+)` |

### Card Mapping
Cards are mapped by last 4 digits via `ICICI_AMAZON_CC_ID` environment variable.

---

## HDFC NACH (Investments)

**Sender:** `nachautoemailer@hdfcbank.net`

### Pattern
```
Rs.{amount} has been debited from HDFC Bank Account...towards {merchant}
```

### Example
```
Rs.15000.00 has been debited from HDFC Bank Account Number XXXXXXXXXXNNNN towards ZERODHA BROKING LTD/XXXXXX
```

### Behavior
- If merchant contains "ZERODHA" → Log to Zerodha account (via `ZERODHA_KITE_ID`)
- Otherwise → Treat as regular HDFC savings debit

---

## Vested (US Investments)

**Sender:** `no-reply@alerts.vestedfinance.com`

**Currency:** USD

### Pattern 1 (Dividend)
```
You have received a ${amount} dividend payout...for your investment in {stock}
```

### Example 1
```
You have received a $0.25 dividend payout ($1.2/share) for your investment in Stock Name (TICKER).

Dividend Details:
Stock/ETF Name: Stock Name (TICKER)
Dividend Amount: $0.25
Payout Date: 16/1/2026
```

### Pattern 2 (Buy Order)
```
Your buy order for {stock} for ${amount} has been successfully completed
```

### Example 2
```
Your buy order for Stock Name for $1,000 has been successfully completed.

You can view the details of this transaction below:
Name of Vest: Stock Name
Amount: $1,000
Transaction Date: 07:02 pm 21/10/2025 IST
```

### Extracted Fields
| Field | Dividend Regex | Buy Order Regex |
|-------|----------------|-----------------|
| Amount | `\$([\\d,]+\\.?\\d*)` | `\$([\\d,]+\\.?\\d*)` |
| Stock | `investment in\\s+([^.]+?)` | `buy order for\\s+(.+?)\\s+for` |
| Date | `Payout Date:\\s*(\\d{1,2}/\\d{1,2}/\\d{4})` | `Transaction Date:.*?(\\d{1,2}/\\d{1,2}/\\d{4})` |

### Transaction Types
| Pattern | Type | Merchant Format |
|---------|------|-----------------|
| Dividend | income | `Dividend: Stock Name` |
| Buy Order | expense | `Buy: Stock Name` |

---

## Not Tracked

| Source | Sender | Reason |
|--------|--------|--------|
| CDSL Demat | `services@cdslindia.co.in` | Units only, no rupee amount. Money already tracked via NACH. |

---

## Adding New Patterns

1. Collect sample emails from the new source
2. Identify the regex patterns for amount, merchant, date
3. Add sender to `WATCHED_SENDERS` in `expense_tracker.py`
4. Create a new `parse_xxx()` function
5. Add routing logic in `parse_email()`
6. Add environment variable for account ID
7. Test with `DRY_RUN=true`

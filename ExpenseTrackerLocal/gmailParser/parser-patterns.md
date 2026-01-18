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
Rs.15000.00 has been debited from HDFC Bank Account Number XXXXXXXXXX4551
```

### Extracted Fields
| Field | Regex | Example |
|-------|-------|---------|
| Amount | `Rs\.?([\d,]+\.?\d*)` | 15000.00 |
| Merchant | `towards\s+([^.]+)` | ZERODHA BROKING LTD |
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
Rs.3181.12 is debited from your HDFC Bank Credit Card ending 3114 towards Agoda Company PTE LTD on 08 Jan, 2026 at 10:22:58
```

### Pattern 2 (Thank you notification)
```
Thank you for using HDFC Bank Card XX{last4} for Rs. {amount} at {merchant} on {date}
```

### Example 2
```
Thank you for using HDFC Bank Card XX3114 for Rs. 299.0 at YOUTUBEGOOGLE on 15-01-2026 21:45:58
```

### Extracted Fields
| Field | Pattern 1 Regex | Pattern 2 Regex |
|-------|-----------------|-----------------|
| Amount | `Rs\.?([\d,]+\.?\d*)\s+is debited` | `Rs\.?\s*([\d,]+\.?\d*)` |
| Last 4 | `ending\s+(\d{4})` | `Card\s+\w*(\d{4})` |
| Merchant | `towards\s+([^.]+?)` | `at\s+(.+?)\s+on` |
| Date | `on\s+(\d{1,2}\s+\w+,?\s+\d{4})` | `on\s+(\d{2}-\d{2}-\d{4})` |

### Card Mapping
| Last 4 | Card | Account ID |
|--------|------|------------|
| 3114 | HDFC Infinia | `e16a880d-be99-4c41-ab8e-54287d2291d0` |
| TBD | HDFC Rupay | `f142a58b-280c-407a-b205-0ac9290fc13b` |

---

## Axis Bank Savings

**Sender:** `alerts@axisbank.com`, `alerts@axis.bank.in`

### Pattern 1 (Short)
```
INR {amount} spent/debited
```

### Pattern 2 (Detailed)
```
INR {amount} was debited from your A/c no. XX{last4}
...
Transaction Info:
UPI/P2M/{ref}/{merchant}
```

### Example 2
```
INR 85.00 was debited from your A/c no. XX1817.

Amount Debited:
INR 85.00

Account Number:
XX1817

Date & Time:
18-01-26, 11:52:17 IST

Transaction Info:
UPI/P2M/601843139240/K VENKATESH
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
Your ICICI Bank Credit Card XX0018 has been used for a transaction of INR 16,495.00 on Jan 18, 2026 at 11:38:41. Info: AMAZON PAY IN E COMMERCE.
```

### Extracted Fields
| Field | Regex |
|-------|-------|
| Last 4 | `Credit Card\s+\w*(\d{4})` |
| Amount | `INR\s+([\d,]+\.?\d*)` |
| Date | `on\s+(\w+\s+\d{1,2},?\s+\d{4})` |
| Merchant | `Info:\s*([^.]+)` |

### Card Mapping
| Last 4 | Card | Account ID |
|--------|------|------------|
| 0018 | ICICI Amazon | `fdcc2636-6b28-4df5-a998-2f38820f3a74` |

---

## HDFC NACH (Zerodha)

**Sender:** `nachautoemailer@hdfcbank.net`

### Pattern
```
Rs.{amount} has been debited from HDFC Bank Account...towards ZERODHA
```

### Example
```
Rs.15000.00 has been debited from HDFC Bank Account Number XXXXXXXXXX4551 towards ZERODHA BROKING LTD/ZJ0604
```

### Behavior
- If merchant contains "ZERODHA" → Log to Zerodha Kite account
- Otherwise → Treat as regular HDFC savings debit

---

## Not Tracked

| Source | Sender | Reason |
|--------|--------|--------|
| CDSL Demat | `services@cdslindia.co.in` | Units only, no rupee amount. Money already tracked via NACH. |
| Zerodha Coin SIP | TBD | Covered by NACH debit |

---

## Account ID Reference

| Account | ID |
|---------|-----|
| HDFC Savings | `fdecba37-33b5-45cf-bc82-3fc1df875d02` |
| Axis Savings | `85f3400d-db52-4300-8a19-fdfaf2385e7d` |
| HDFC Infinia CC (3114) | `e16a880d-be99-4c41-ab8e-54287d2291d0` |
| HDFC Rupay CC | `f142a58b-280c-407a-b205-0ac9290fc13b` |
| Axis Rewards CC | `dbbb79c2-e381-4c88-8c2b-d68073959a3d` |
| ICICI Amazon CC (0018) | `fdcc2636-6b28-4df5-a998-2f38820f3a74` |
| Zerodha Coin | `6ebd2d4f-a105-4225-839f-d4d7f781f16e` |
| Zerodha Kite | `07699932-dddf-45a0-995e-ec736faabde2` |

### Pattern 3 (RuPay Credit Card)
```
Rs.{amount} has been debited from your HDFC Bank RuPay Credit Card XX{last4} to {merchant} on {date}
```

### Example 3
```
Rs.40.00 has been debited from your HDFC Bank RuPay Credit Card XX2398 to paytm.s1faoa0@pty DAIVIK HANUMANTHARAJU JAGADISH on 18-01-26
```

### Updated Card Mapping
| Last 4 | Card | Account ID |
|--------|------|------------|
| 3114 | HDFC Infinia | `e16a880d-be99-4c41-ab8e-54287d2291d0` |
| 2398 | HDFC Rupay | `f142a58b-280c-407a-b205-0ac9290fc13b` |

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
You have received a $0.25 dividend payout ($1.2/share) for your investment in Intuit Inc.(INTU).

Dividend Details:
Stock/ETF Name: Intuit Inc.(INTU)
Dividend Amount: $0.25
Payout Date: 16/1/2026
```

### Pattern 2 (Buy Order)
```
Your buy order for {stock} for ${amount} has been successfully completed
```

### Example 2
```
Your buy order for Moat for $1,000 has been successfully completed.

You can view the details of this transaction below:
Name of Vest: Moat
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
| Dividend | income | `Dividend: Intuit Inc.(INTU)` |
| Buy Order | expense | `Buy: Moat` |

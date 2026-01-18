# Expense Tracker

Automated expense tracking from bank/CC transaction emails to a finance API.

## Supported Alerts

Currently parses transaction emails from:

### Banks (India)
- **HDFC Bank** - Savings account debits, NACH/auto-debit
- **Axis Bank** - Savings account debits, UPI transactions
- **ICICI Bank** - Credit card transactions

### Credit Cards (India)
- **HDFC Credit Cards** - Multiple card formats supported (Infinia, Rupay, etc.)
- **ICICI Amazon** - Co-branded Amazon card

### Investments
- **Zerodha** - NACH debits for Coin (MF) and Kite (stocks)
- **Vested** - US stock dividends and buy orders

> **Adding new sources**: See [Adding New Parsers](#adding-new-parsers) section. PRs welcome!

## Supported Sources

| Source | Email Sender | Transactions |
|--------|--------------|--------------|
| HDFC Savings | `alerts@hdfcbank.net` | Debits |
| HDFC Credit Card | `alerts@hdfcbank.net` | Multiple card patterns |
| HDFC NACH | `nachautoemailer@hdfcbank.net` | Investments (Zerodha) |
| Axis Savings | `alerts@axisbank.com` | Debits, UPI |
| ICICI Credit Card | `alerts@icicibank.com` | Card transactions |
| Vested | `no-reply@alerts.vestedfinance.com` | Dividends, Buy orders |

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Gmail account with App Password
- Finance API running (or use DRY_RUN mode)

### 2. Setup

```bash
# Clone/copy files to your machine
cd gmailParser

# Create config from template
cp config.env.example config.env

# Edit config with your credentials
nano config.env
```

**Required config.env values:**
```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-16-char-app-password
SURE_API_KEY=your-api-key
SURE_API_URL=http://your-api-server:3001

# Account IDs (get from your finance app)
HDFC_SAVINGS_ID=your-uuid
AXIS_SAVINGS_ID=your-uuid
# ... (see config.env.example for full list)
```

### 3. Test Locally (Dry Run)

```bash
# Install dependencies
pip install -r requirements.txt

# Test without posting to API
DRY_RUN=true \
EMAIL_ADDRESS=your-email@gmail.com \
EMAIL_PASSWORD=your-app-password \
python expense_tracker.py
```

Expected output:
```
2026-01-18 15:00:00 - INFO - Starting expense tracker...
2026-01-18 15:00:00 - INFO - Dry run mode: True
2026-01-18 15:00:01 - INFO - Connecting to imap.gmail.com...
2026-01-18 15:00:02 - INFO - Connected successfully
2026-01-18 15:00:02 - INFO - Found 3 unread emails from alerts@hdfcbank.net
2026-01-18 15:00:03 - INFO - Parsed: 299.0 - MERCHANT_NAME (2026-01-15)
2026-01-18 15:00:03 - INFO - [DRY RUN] Would post transaction
2026-01-18 15:00:03 - INFO - Done! Processed: 3, Failed: 0
```

### 4. Test with API

```bash
# Test with actual posting
EMAIL_ADDRESS=your-email@gmail.com \
EMAIL_PASSWORD=your-app-password \
SURE_API_KEY=your-api-key \
SURE_API_URL=http://your-api-server:3001 \
python expense_tracker.py
```

### 5. Deploy with Docker

```bash
# Build and run (builds locally, supports ARM/Raspberry Pi)
docker compose up -d --build

# View logs
docker logs -f expense-tracker

# Stop
docker compose down
```

> **Note**: The image is built locally on each deployment. This ensures ARM compatibility (Raspberry Pi) without needing a container registry.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_ADDRESS` | Yes | - | Gmail address |
| `EMAIL_PASSWORD` | Yes | - | Gmail App Password (16 chars) |
| `SURE_API_KEY` | Yes* | - | API key (*unless DRY_RUN=true) |
| `SURE_API_URL` | No | `http://localhost:3001` | API URL |
| `IMAP_HOST` | No | `imap.gmail.com` | IMAP server |
| `DRY_RUN` | No | `false` | Test mode (no API calls) |
| `CRON_SCHEDULE` | No | `*/5 * * * *` | Docker cron schedule |

### Account ID Variables

You need to set account IDs for each bank/card you want to track:

| Variable | Description |
|----------|-------------|
| `HDFC_SAVINGS_ID` | HDFC Bank savings account |
| `AXIS_SAVINGS_ID` | Axis Bank savings account |
| `HDFC_INFINIA_CC_ID` | HDFC Infinia credit card |
| `HDFC_RUPAY_CC_ID` | HDFC Rupay credit card |
| `AXIS_REWARDS_CC_ID` | Axis Rewards credit card |
| `ICICI_AMAZON_CC_ID` | ICICI Amazon credit card |
| `ZERODHA_COIN_ID` | Zerodha Coin (MF) |
| `ZERODHA_KITE_ID` | Zerodha Kite (stocks) |
| `VESTED_ID` | Vested (US investments) |

## How It Works

1. Connects to Gmail via IMAP
2. Fetches unread emails from watched senders
3. Parses transaction details (amount, merchant, date)
4. Posts to finance API
5. Marks email as read
6. Runs every 5 minutes via cron (in Docker)

## Troubleshooting

### "Could not parse email from..."
- Email format may have changed
- Check `parser-patterns.md` for expected formats
- Add new regex pattern to `expense_tracker.py`

### "Failed to post transaction"
- Check API is running: `curl http://your-api-server:3001/api/health`
- Verify API key is correct
- Check account IDs exist in your finance app

### "LOGIN failed"
- Verify Gmail App Password (not regular password)
- Enable IMAP in Gmail settings
- Check for 2FA issues

### Emails not being processed
- Ensure emails are UNREAD
- Check sender is in `WATCHED_SENDERS` list
- Verify email format matches patterns

## Files

```
gmailParser/
├── expense_tracker.py   # Main script
├── Dockerfile           # Container build
├── docker-compose.yml   # Orchestration
├── entrypoint.sh        # Cron setup
├── config.env.example   # Config template
├── config.env           # Your credentials (git-ignored)
├── requirements.txt     # Python deps
├── parser-patterns.md   # Email pattern docs
└── README.md            # This file
```

## Adding New Parsers

1. Get sample email from new source
2. Add sender to `WATCHED_SENDERS`
3. Create `parse_xxx()` function with regex
4. Add routing in `parse_email()`
5. Document in `parser-patterns.md`
6. Test with `DRY_RUN=true`

## Customizing Card Mappings

The script uses the last 4 digits of credit cards to map to account IDs. To add a new card:

1. Add environment variable: `MY_CARD_CC_ID=your-uuid`
2. Update `ACCOUNT_IDS` dict in `expense_tracker.py`:
   ```python
   "my_card_cc_XXXX": os.getenv("MY_CARD_CC_ID", ""),
   ```
3. Update the parser to extract and use the last 4 digits

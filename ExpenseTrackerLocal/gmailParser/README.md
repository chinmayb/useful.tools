# Expense Tracker

Automated expense tracking from bank/CC transaction emails to Sure Finance.

## Supported Sources

| Source | Email Sender | Transactions |
|--------|--------------|--------------|
| HDFC Savings | `alerts@hdfcbank.net` | Debits |
| HDFC Credit Card | `alerts@hdfcbank.net` | Infinia (3114), Rupay (2398) |
| HDFC NACH | `nachautoemailer@hdfcbank.net` | Zerodha investments |
| Axis Savings | `alerts@axisbank.com` | Debits, UPI |
| ICICI Credit Card | `alerts@icicibank.com` | Amazon (0018) |
| Vested | `no-reply@alerts.vestedfinance.com` | Dividends, Buy orders |

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Gmail account with App Password
- Sure Finance running at `http://192.168.0.9:3001`

### 2. Setup

```bash
# Clone/copy files to your machine
cd expense-tracker

# Create config from template
cp config.env.example config.env

# Edit config with your credentials
nano config.env
```

**Required config.env values:**
```env
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-16-char-app-password
SURE_API_KEY=your-sure-api-key
```

### 3. Test Locally (Dry Run)

```bash
# Install dependencies
pip install -r requirements.txt

# Test without posting to Sure
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
2026-01-18 15:00:03 - INFO - Parsed: 299.0 - YOUTUBEGOOGLE (2026-01-15)
2026-01-18 15:00:03 - INFO - [DRY RUN] Would post transaction
2026-01-18 15:00:03 - INFO - Done! Processed: 3, Failed: 0
```

### 4. Test with Sure API

```bash
# Test with actual posting (one email)
EMAIL_ADDRESS=your-email@gmail.com \
EMAIL_PASSWORD=your-app-password \
SURE_API_KEY=your-api-key \
python expense_tracker.py
```

### 5. Deploy with Docker

```bash
# Build and run
docker compose up -d --build

# View logs
docker logs -f expense-tracker

# Stop
docker compose down
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_ADDRESS` | Yes | - | Gmail address |
| `EMAIL_PASSWORD` | Yes | - | Gmail App Password (16 chars) |
| `SURE_API_KEY` | Yes* | - | Sure Finance API key (*unless DRY_RUN=true) |
| `SURE_API_URL` | No | `http://192.168.0.9:3001` | Sure Finance URL |
| `IMAP_HOST` | No | `imap.gmail.com` | IMAP server |
| `DRY_RUN` | No | `false` | Test mode (no API calls) |
| `CRON_SCHEDULE` | No | `*/5 * * * *` | Docker cron schedule |

## How It Works

1. Connects to Gmail via IMAP
2. Fetches unread emails from watched senders
3. Parses transaction details (amount, merchant, date)
4. Posts to Sure Finance API
5. Marks email as read
6. Runs every 5 minutes via cron (in Docker)

## Troubleshooting

### "Could not parse email from..."
- Email format may have changed
- Check `parser-patterns.md` for expected formats
- Add new regex pattern to `expense_tracker.py`

### "Failed to post transaction"
- Check Sure API is running: `curl http://192.168.0.9:3001/api/health`
- Verify API key is correct
- Check account IDs exist in Sure

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
expense-tracker/
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

## Account IDs

| Account | Last 4 | ID |
|---------|--------|-----|
| HDFC Savings | - | `fdecba37-33b5-45cf-bc82-3fc1df875d02` |
| Axis Savings | - | `85f3400d-db52-4300-8a19-fdfaf2385e7d` |
| HDFC Infinia | 3114 | `e16a880d-be99-4c41-ab8e-54287d2291d0` |
| HDFC Rupay | 2398 | `f142a58b-280c-407a-b205-0ac9290fc13b` |
| Axis Rewards | 0022 | `dbbb79c2-e381-4c88-8c2b-d68073959a3d` |
| ICICI Amazon | 0018 | `fdcc2636-6b28-4df5-a998-2f38820f3a74` |
| Zerodha Coin | - | `6ebd2d4f-a105-4225-839f-d4d7f781f16e` |
| Zerodha Kite | - | `07699932-dddf-45a0-995e-ec736faabde2` |
| Vested | - | `2e99c4a1-e8cf-45a5-a718-d29775439317` |

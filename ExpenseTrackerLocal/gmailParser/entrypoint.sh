#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-0 */4 * * *}"

printenv | grep -E '^(IMAP_|EMAIL_|SURE_|DRY_|READ_ALL_|START_|MAX_|HDFC_|AXIS_|ICICI_|ZERODHA_|VESTED_|PROCESSED_)' > /app/env.sh
sed -i 's/^/export /' /app/env.sh

echo "$CRON_SCHEDULE /bin/bash -c 'source /app/env.sh && cd /app && python expense_tracker.py >> /app/logs/cron.log 2>&1'" > /etc/cron.d/expense-tracker
chmod 0644 /etc/cron.d/expense-tracker
crontab /etc/cron.d/expense-tracker

mkdir -p /app/logs
touch /app/logs/cron.log

echo "Starting expense tracker with schedule: $CRON_SCHEDULE"
echo "Running initial check..."
python expense_tracker.py

cron -f

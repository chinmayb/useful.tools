#!/bin/bash

set -e

echo "🚀 Starting Expense Tracker with Docker Compose"
echo "================================================"

if [ ! -f "config.env" ]; then
    echo "❌ Error: config.env file not found!"
    echo "Please create config.env from config.env.example and add your credentials."
    exit 1
fi

required_vars=("EMAIL_ADDRESS" "EMAIL_PASSWORD" "SURE_API_KEY")
for var in "${required_vars[@]}"; do
    if ! grep -q "^${var}=" config.env || grep -q "^${var}=your-" config.env; then
        echo "❌ Error: ${var} is not properly configured in config.env"
        exit 1
    fi
done

echo "✅ Configuration file found and validated"
echo ""

echo "📋 Current Settings:"
echo "-------------------"
grep -E "^(DRY_RUN|READ_ALL_EMAILS|START_DATE|MAX_EMAILS)" config.env || true
echo ""

read -p "Do you want to proceed with posting transactions to Sure Finance? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "🔨 Building Docker image..."
docker-compose build

echo ""
echo "🚀 Starting container..."
docker-compose up -d

echo ""
echo "✅ Container started successfully!"
echo ""
echo "📊 Showing initial run output (press Ctrl+C to stop watching):"
echo "================================================================"
docker-compose logs -f expense-tracker
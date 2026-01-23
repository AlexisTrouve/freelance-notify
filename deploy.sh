#!/bin/bash
# Deployment script for codeur-notify

set -e

echo "=== Codeur-notify Deployment ==="

# Install dependencies
echo "[1/4] Installing Python dependencies..."
pip3 install -r requirements.txt --quiet

# Check config
if [ ! -f config.json ]; then
    echo "[2/4] Creating config from template..."
    cp config.example.json config.json
    echo ">>> EDIT config.json with your Discord webhook URL!"
else
    echo "[2/4] Config exists, skipping..."
fi

# Test run
echo "[3/4] Testing scraper (dry-run)..."
python3 scraper.py --dry-run

# Setup cron
echo "[4/4] Setting up cron job..."
CRON_CMD="*/30 * * * * cd $(pwd) && /usr/bin/python3 scraper.py >> $(pwd)/cron.log 2>&1"

# Check if cron already exists
if crontab -l 2>/dev/null | grep -q "codeur-notify"; then
    echo "Cron job already exists"
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "Cron job added"
fi

echo ""
echo "=== Deployment complete ==="
echo "1. Edit config.json with your Discord webhook"
echo "2. Run: python3 scraper.py --dry-run"
echo "3. Cron will run every 30 minutes"
echo ""
echo "Logs: tail -f $(pwd)/cron.log"

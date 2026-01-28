#!/usr/bin/env python3
"""
Upwork Scraper Service (NSSM)
Background service that scrapes Upwork periodically.
Designed to run as Windows Service via NSSM.
"""

import asyncio
import time
import random
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from upwork_adapter import UpworkAdapter

# =============================================================================
# CONFIGURATION - Edit these values
# =============================================================================
CHECK_INTERVAL_HOURS = 3        # Base interval (randomized +/- 30min)
QUERIES = [
    "VBA Excel automation",
    "Python scripting automation",
    "API integration REST",
    "Discord bot",
]
NUM_PAGES_MIN = 3               # Min pages per query
NUM_PAGES_MAX = 10              # Max pages per query (randomized each run)
DELAY_BETWEEN_QUERIES = 60      # Seconds between queries (randomized +/- 20s)
# =============================================================================

# Paths
SERVICE_DIR = Path(__file__).parent
LOG_FILE = SERVICE_DIR / "upwork_service.log"
STATE_FILE = SERVICE_DIR / "upwork_service_state.json"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
running = True


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False


def load_state() -> dict:
    """Load service state from file"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_state(state: dict):
    """Save service state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def run_scrape():
    """Execute one scraping cycle"""
    logger.info("=" * 60)
    logger.info("Starting Upwork scrape cycle (Camoufox)")
    logger.info("=" * 60)

    adapter = UpworkAdapter()
    total_notified = 0

    for i, query in enumerate(QUERIES):
        if not running:
            logger.info("Shutdown requested, stopping scrape")
            break

        # Random number of pages (3-10) for human-like behavior
        num_pages = random.randint(NUM_PAGES_MIN, NUM_PAGES_MAX)
        num_jobs = num_pages * 10  # ~10 jobs per page

        logger.info(f"[{i+1}/{len(QUERIES)}] Scraping: {query} ({num_pages} pages)")

        try:
            # Run async scrape
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Camoufox bypasses Cloudflare in headless mode
            jobs = loop.run_until_complete(
                adapter.scrape_and_notify(query, num_jobs, headless=True, num_pages=num_pages)
            )
            loop.close()

            if jobs:
                total_notified += len(jobs)
                logger.info(f"  -> {len(jobs)} jobs sent to Discord")
            else:
                logger.info(f"  -> No qualifying jobs found")

        except Exception as e:
            logger.error(f"  -> Error: {e}")

        # Random delay between queries
        if i < len(QUERIES) - 1 and running:
            delay = DELAY_BETWEEN_QUERIES + random.uniform(-20, 20)
            logger.info(f"  Waiting {delay:.0f}s before next query...")
            time.sleep(delay)

    logger.info("-" * 60)
    logger.info(f"Scrape cycle complete. Notified: {total_notified} jobs")
    logger.info("-" * 60)

    return total_notified


def main():
    """Main service loop"""
    global running

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("Upwork Scraper Service Starting")
    logger.info(f"Check interval: {CHECK_INTERVAL_HOURS}h (+/- 30min)")
    logger.info(f"Queries: {len(QUERIES)}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 60)

    state = load_state()
    last_check_str = state.get('last_check')

    if last_check_str:
        try:
            last_check = datetime.fromisoformat(last_check_str)
            logger.info(f"Last check was: {last_check}")
        except:
            last_check = None
    else:
        last_check = None

    # Initial delay (5 min) to let system settle after boot
    if last_check is None:
        logger.info("First run - waiting 5 minutes before first scrape...")
        for _ in range(30):  # 30 x 10s = 5min
            if not running:
                return
            time.sleep(10)

    while running:
        now = datetime.now()

        # Calculate interval with jitter
        base_interval = CHECK_INTERVAL_HOURS * 3600
        jitter = random.uniform(-1800, 1800)  # +/- 30 min
        interval = base_interval + jitter

        # Check if it's time to scrape
        should_scrape = False
        if last_check is None:
            should_scrape = True
        else:
            elapsed = (now - last_check).total_seconds()
            if elapsed >= interval:
                should_scrape = True
            else:
                remaining = interval - elapsed
                next_check = now + timedelta(seconds=remaining)
                logger.debug(f"Next check at: {next_check.strftime('%H:%M')}")

        if should_scrape:
            try:
                run_scrape()
            except Exception as e:
                logger.error(f"Scrape cycle failed: {e}")

            last_check = datetime.now()
            state['last_check'] = last_check.isoformat()
            save_state(state)

            next_run = last_check + timedelta(seconds=interval)
            logger.info(f"Next scrape around: {next_run.strftime('%Y-%m-%d %H:%M')}")

        # Sleep for 1 minute before checking again
        for _ in range(6):  # 6 x 10s = 1min
            if not running:
                break
            time.sleep(10)

    logger.info("Service stopped gracefully")


if __name__ == "__main__":
    main()

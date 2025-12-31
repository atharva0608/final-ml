"""
Scraper Scheduler

Runs the static data scraper on a schedule (e.g., hourly or daily).
Uses APScheduler for cron-like scheduling.
"""

import sys
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Add scraper to path
sys.path.insert(0, str(Path(__file__).parent))

from fetch_static_data import main as fetch_data


def run_scraper():
    """Wrapper to run the scraper with error handling"""
    try:
        print(f"\n[{datetime.now()}] Running scheduled scraper...")
        fetch_data()
        print(f"[{datetime.now()}] Scraper completed successfully")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Scraper failed: {e}")


def main():
    """Start the scheduler"""
    print("="*80)
    print("SPOT OPTIMIZER - SCRAPER SCHEDULER")
    print("="*80)
    print(f"Start Time: {datetime.now()}")
    print("Schedule: Every 6 hours")
    print("="*80)

    scheduler = BlockingScheduler()

    # Run immediately on startup
    print("\n🚀 Running initial scrape...")
    run_scraper()

    # Schedule to run every 6 hours
    scheduler.add_job(
        run_scraper,
        CronTrigger(hour='*/6'),  # Every 6 hours
        id='spot_data_scraper',
        name='Spot Data Scraper',
        replace_existing=True
    )

    print(f"\n✅ Scheduler started. Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{datetime.now()}] Scheduler stopped by user")


if __name__ == "__main__":
    main()

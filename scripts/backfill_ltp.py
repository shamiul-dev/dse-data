"""
Historical LTP & Clean Day-End Backfill Tool.
Iterates over monthly date windows against /api/live/data-archive/day-end
to backfill LTP, close, volume, and session_status across all securities.
Rate-limited at 1.0s + jitter per request with raw_fetch audit provenance.
"""

import argparse
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import random
import sys
import time
from typing import List, Tuple

# Add repository root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.parsers.archive_parser import parse_day_end_response
from dse_scraper.storage.alchemy.database import DatabaseManager
from dse_scraper.storage.alchemy.models import RawFetchModel
from dse_scraper.storage.alchemy.postgres_storage import PostgresAlchemyStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger(__name__)


def generate_month_ranges(start_date: date, end_date: date) -> List[Tuple[date, date]]:
    """Generates monthly [start, end] date slices."""
    ranges = []
    curr = start_date
    while curr <= end_date:
        # End of current month
        # Move to next month day 1 minus 1 day
        if curr.month == 12:
            next_month = date(curr.year + 1, 1, 1)
        else:
            next_month = date(curr.year, curr.month + 1, 1)
        month_end = min(next_month - timedelta(days=1), end_date)
        ranges.append((curr, month_end))
        curr = next_month
    return ranges


def run_ltp_backfill(start_date: date, end_date: date, dry_run: bool = False):
    config = DSEConfig()
    client = ResilientClient(config=config)
    storage = PostgresAlchemyStorage(config.postgres_url)
    db = DatabaseManager(config.postgres_url)

    month_ranges = generate_month_ranges(start_date, end_date)
    logger.info("Starting LTP backfill from %s to %s across %d monthly windows...", start_date, end_date, len(month_ranges))

    total_records_ingested = 0

    for idx, (m_start, m_end) in enumerate(month_ranges, 1):
        from_str = m_start.isoformat()
        to_str = m_end.isoformat()
        logger.info("[%d/%d] Fetching window: %s -> %s", idx, len(month_ranges), from_str, to_str)

        page = 1
        total_pages = 1

        while page <= total_pages:
            url = f"{config.modern_base_url}/api/live/data-archive/day-end?from={from_str}&to={to_str}&page={page}"
            res = client.get(url)

            if not res.is_success:
                logger.error("Failed to fetch %s (status %d)", url, res.status)
                time.sleep(2.0)
                continue

            records, total, reported_pages = parse_day_end_response(res.body)
            total_pages = reported_pages

            if not records:
                logger.info("  No records returned for page %d (total reported: %d). Ending window.", page, total)
                break

            if not dry_run:
                # Record raw fetch audit
                with db.session() as sess:
                    rf = RawFetchModel(
                        feed_name="day_end_archive",
                        request_url=url,
                        session_date=m_end,
                        fetched_at=datetime.now(),
                        http_status=res.status,
                        record_count=len(records),
                    )
                    sess.add(rf)
                    sess.flush()
                    fetch_id = rf.fetch_id

                storage.save_daily_eod(records, fetch_id=fetch_id)

            total_records_ingested += len(records)
            logger.info("  Page %d/%d: ingested %d records (window total: %d)", page, total_pages, len(records), total)
            page += 1

            # Polite jitter
            time.sleep(1.0 + random.uniform(0.1, 0.4))

    logger.info("Backfill complete! Ingested/updated a total of %d historical records.", total_records_ingested)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill LTP and clean EOD bars from DSE day-end archive.")
    parser.add_argument("--start", type=str, default="2026-10-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-11-10", help="End date (YYYY-MM-DD)")
    parser.add_argument("--full", action="store_true", help="Run full 2-year backfill from 2024-11-10")
    parser.add_argument("--dry-run", action="store_true", help="Fetch without saving to DB")
    args = parser.parse_args()

    if args.full:
        s_date = date(2024, 11, 10)
        e_date = date.today()
    else:
        s_date = date.fromisoformat(args.start)
        e_date = date.fromisoformat(args.end)

    run_ltp_backfill(s_date, e_date, dry_run=args.dry_run)

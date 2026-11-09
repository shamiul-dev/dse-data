"""
Historical data service.
Queries and backfills daily OHLCV prices across date ranges and instruments
with streaming page-level persistence, checkpointing, and anti-bot breathers.
"""

from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import List, Optional

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.models.history import DailyEOD
from dse_scraper.parsers.archive_parser import parse_day_end_response
from dse_scraper.storage.base import BaseStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """Service to fetch and backfill historical Day-End OHLCV prices."""

    def __init__(
        self,
        client: Optional[ResilientClient] = None,
        storage: Optional[BaseStorage] = None,
        config: Optional[DSEConfig] = None,
    ):
        self.config = config or DSEConfig()
        self.client = client or ResilientClient(self.config)
        self.storage = storage or SQLiteStorage(self.config.sqlite_db_path)

    def fetch_history(
        self,
        from_date: str,
        to_date: str,
        symbol: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> List[DailyEOD]:
        """
        Fetches historical records for a date range and optional symbol.
        Automatically handles pagination.
        """
        all_records: List[DailyEOD] = []
        page = 1

        while True:
            params = f"from={from_date}&to={to_date}&page={page}"
            if symbol:
                params += f"&inst={symbol.strip()}"

            url = f"{self.config.modern_base_url}/api/live/data-archive/day-end?{params}"
            response = self.client.get(
                url,
                headers={"Accept": "application/json"},
                referer=f"{self.config.modern_base_url}/data-archives",
            )

            if not response.is_success:
                logger.error("Failed to fetch historical page %d from %s", page, url)
                break

            records, total_records, total_pages = parse_day_end_response(response.body)
            if not records:
                break

            all_records.extend(records)
            logger.info(
                "Fetched page %d/%d (%d records, cumulative: %d)",
                page, total_pages, len(records), len(all_records)
            )

            if page >= total_pages or (max_pages and page >= max_pages):
                break

            page += 1

        return all_records

    def backfill(
        self,
        from_date: str,
        to_date: str,
        symbol: Optional[str] = None,
        resume: bool = True,
        batch_breather_interval: int = 50,
        breather_seconds: float = 3.0,
    ) -> int:
        """
        Fetches and persists historical records into configured storage.
        Streams directly to database page-by-page with checkpointing and adaptive breathers.
        """
        checkpoint_file = Path(".eod_backfill_checkpoint.json")
        start_page = 1

        if resume and checkpoint_file.exists():
            try:
                ckpt = json.loads(checkpoint_file.read_text(encoding="utf-8"))
                if ckpt.get("from_date") == from_date and ckpt.get("to_date") == to_date and ckpt.get("symbol") == symbol:
                    start_page = ckpt.get("next_page", 1)
                    logger.info("Resuming historical backfill from page %d", start_page)
            except Exception:
                start_page = 1
        elif not resume and checkpoint_file.exists():
            checkpoint_file.unlink(missing_ok=True)

        total_saved = 0
        page = start_page

        while True:
            params = f"from={from_date}&to={to_date}&page={page}"
            if symbol:
                params += f"&inst={symbol.strip()}"

            url = f"{self.config.modern_base_url}/api/live/data-archive/day-end?{params}"
            response = self.client.get(
                url,
                headers={"Accept": "application/json"},
                referer=f"{self.config.modern_base_url}/data-archives",
            )

            if not response.is_success:
                logger.error("Failed to fetch historical page %d from %s", page, url)
                break

            records, total_records, total_pages = parse_day_end_response(response.body)
            if not records:
                break

            # Persist this page immediately to database
            self.storage.save_daily_eod(records)
            total_saved += len(records)

            logger.info(
                "Persisted EOD page %d/%d (%d records on page, %d total in this run)",
                page, total_pages, len(records), total_saved
            )

            # Update checkpoint
            checkpoint_file.write_text(
                json.dumps({
                    "from_date": from_date,
                    "to_date": to_date,
                    "symbol": symbol,
                    "next_page": page + 1,
                    "total_pages": total_pages,
                    "total_saved": total_saved,
                }, indent=2),
                encoding="utf-8"
            )

            if page >= total_pages:
                checkpoint_file.unlink(missing_ok=True)
                logger.info("Historical backfill completed across all %d pages!", total_pages)
                break

            # Adaptive batch breather every 50 pages
            if page % batch_breather_interval == 0:
                logger.info("Taking a brief %.1fs breather after page %d...", breather_seconds, page)
                time.sleep(breather_seconds)

            page += 1

        return total_saved

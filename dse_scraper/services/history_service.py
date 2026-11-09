"""
Historical data service.
Queries and backfills daily OHLCV prices across date ranges and instruments.
"""

from datetime import date, datetime, timedelta, timezone
import logging
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
    ) -> int:
        """
        Fetches and persists historical records into configured storage.
        Returns the number of records saved.
        """
        records = self.fetch_history(from_date=from_date, to_date=to_date, symbol=symbol)
        if records:
            self.storage.save_daily_eod(records)
            logger.info("Successfully persisted %d historical records.", len(records))
        return len(records)


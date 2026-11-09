"""
DSE Scraper — High-reliability, modular data scraper for the Dhaka Stock Exchange.
"""

from typing import Optional

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.models import (
    CompanyProfile,
    DailyEOD,
    IndexQuote,
    Instrument,
    InstrumentQuote,
    LiveSnapshot,
    MarketTotals,
)
from dse_scraper.services.company_service import CompanyProfileService
from dse_scraper.services.history_service import HistoricalDataService
from dse_scraper.services.live_service import LiveMarketService
from dse_scraper.storage.base import BaseStorage
from dse_scraper.storage.memory_storage import MemoryStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage
from dse_scraper.storage.alchemy.postgres_storage import PostgresAlchemyStorage


class DSEScraper:
    """
    Main orchestrator for DSE scraping operations.
    Provides unified access to Live, Historical, and Company services.
    """

    def __init__(
        self,
        storage: Optional[BaseStorage] = None,
        config: Optional[DSEConfig] = None,
    ):
        self.config = config or DSEConfig()
        self.storage = storage or SQLiteStorage(self.config.sqlite_db_path)
        self.client = ResilientClient(self.config)

        # Domain Services
        self.live = LiveMarketService(client=self.client, storage=self.storage, config=self.config)
        self.history = HistoricalDataService(client=self.client, storage=self.storage, config=self.config)
        self.company = CompanyProfileService(client=self.client, storage=self.storage, config=self.config)


__all__ = [
    "DSEScraper",
    "DSEConfig",
    "BaseStorage",
    "SQLiteStorage",
    "MemoryStorage",
    "PostgresAlchemyStorage",
    "Instrument",
    "IndexQuote",
    "InstrumentQuote",
    "LiveSnapshot",
    "MarketTotals",
    "DailyEOD",
    "CompanyProfile",
]


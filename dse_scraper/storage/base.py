"""
Abstract storage repository interface for the DSE Scraper.
Decouples scrapers and parsers from underlying database technologies.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.models.history import DailyEOD
from dse_scraper.models.instrument import Instrument
from dse_scraper.models.quote import InstrumentQuote
from dse_scraper.models.snapshot import LiveSnapshot


class BaseStorage(ABC):
    """Abstract Base Class for DSE persistence engines."""

    @abstractmethod
    def save_snapshot(self, snapshot: LiveSnapshot) -> None:
        """Persist a live market snapshot (indices + quotes + totals)."""
        pass

    @abstractmethod
    def save_instruments(self, instruments: List[Instrument]) -> None:
        """Upsert master instrument definitions."""
        pass

    @abstractmethod
    def save_daily_eod(self, records: List[DailyEOD]) -> None:
        """Upsert historical daily price records."""
        pass

    @abstractmethod
    def save_company_profile(self, profile: CompanyProfile) -> None:
        """Upsert company fundamentals and shareholding."""
        pass

    @abstractmethod
    def get_instruments(self) -> List[Instrument]:
        """Retrieve all known instruments."""
        pass

    @abstractmethod
    def get_latest_quotes(self) -> List[InstrumentQuote]:
        """Retrieve latest quotes for all instruments."""
        pass


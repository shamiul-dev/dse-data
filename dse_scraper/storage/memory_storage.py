"""
In-memory storage adapter.
Useful for unit tests, ephemeral runs, and piping data directly to analytics memory.
"""

from typing import Dict, List, Optional
from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.models.history import DailyEOD
from dse_scraper.models.instrument import Instrument
from dse_scraper.models.quote import InstrumentQuote
from dse_scraper.models.snapshot import LiveSnapshot
from dse_scraper.storage.base import BaseStorage


class MemoryStorage(BaseStorage):
    """Stores scraped entities in memory dictionaries."""

    def __init__(self):
        self.snapshots: List[LiveSnapshot] = []
        self.instruments: Dict[str, Instrument] = {}
        self.latest_quotes: Dict[str, InstrumentQuote] = {}
        self.daily_eod: Dict[tuple[str, str], DailyEOD] = {}
        self.profiles: Dict[str, CompanyProfile] = {}

    def save_snapshot(self, snapshot: LiveSnapshot) -> None:
        self.snapshots.append(snapshot)
        for quote in snapshot.quotes:
            self.latest_quotes[quote.symbol] = quote
            # Auto-register instrument if missing
            if quote.symbol not in self.instruments:
                self.instruments[quote.symbol] = Instrument(
                    symbol=quote.symbol,
                    category=quote.category,
                    board=quote.board,
                    sector=quote.sector,
                    asset_type=quote.asset_type,
                )

    def save_instruments(self, instruments: List[Instrument]) -> None:
        for inst in instruments:
            self.instruments[inst.symbol] = inst

    def save_daily_eod(self, records: List[DailyEOD]) -> None:
        for rec in records:
            key = (rec.symbol, rec.date.isoformat())
            self.daily_eod[key] = rec

    def save_company_profile(self, profile: CompanyProfile) -> None:
        self.profiles[profile.symbol] = profile

    def get_instruments(self) -> List[Instrument]:
        return list(self.instruments.values())

    def get_latest_quotes(self) -> List[InstrumentQuote]:
        return list(self.latest_quotes.values())


from datetime import date as dt_date, datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from dse_scraper.models.quote import IndexQuote, InstrumentQuote


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketTotals(BaseModel):
    """Aggregate market turnover and statistics."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    trades: Optional[int] = Field(0, description="Total market trades")
    volume: Optional[int] = Field(0, description="Total market volume")
    turnover_mn: Optional[float] = Field(0.0, description="Total turnover in Millions BDT")
    market_cap: Optional[float] = Field(None, description="Total market capitalization in BDT")
    trade_time_raw: Optional[str] = Field(None, description="Raw exchange trade time string")
    exchange_trade_time: Optional[datetime] = Field(None, description="Parsed exchange trade timestamp (UTC)")


class LiveSnapshot(BaseModel):
    """Complete snapshot of the market at a point in time."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    timestamp: datetime = Field(default_factory=utc_now)
    exchange_trade_time: Optional[datetime] = Field(None, description="Exchange clock timestamp (UTC)")
    session_date: Optional[dt_date] = Field(None, description="Session date from feed")
    feed_date: Optional[dt_date] = Field(None, description="Active trading date from feed")
    indices: List[IndexQuote] = Field(default_factory=list)
    totals: Optional[MarketTotals] = None
    quotes: List[InstrumentQuote] = Field(default_factory=list)

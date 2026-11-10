from datetime import date as dt_date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class IndexQuote(BaseModel):
    """Represents a benchmark index (DSEX, DSES, DS30)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    key: str = Field(..., description="Index code, e.g. DSEX, DS30, DSES")
    value: float = Field(..., description="Current index points")
    change: float = Field(0.0, description="Absolute points change")
    percent: float = Field(0.0, description="Percentage change")
    prev: Optional[float] = Field(None, description="Previous session closing points")


class InstrumentQuote(BaseModel):
    """Represents real-time or latest session quote for a single instrument."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    symbol: str = Field(..., description="Trading code, e.g. GP")
    ltp: Optional[float] = Field(None, description="Last Traded Price")
    ycp: Optional[float] = Field(None, description="Yesterday's Closing Price")
    open: Optional[float] = Field(None, description="Opening price")
    high: Optional[float] = Field(None, description="High price during session")
    low: Optional[float] = Field(None, description="Low price during session")
    close: Optional[float] = Field(None, description="Closing price")
    volume: Optional[int] = Field(0, description="Total traded volume / share count")
    value_mn: Optional[float] = Field(0.0, description="Total traded value in Millions BDT")
    trades: Optional[int] = Field(0, description="Number of trades executed")
    change: Optional[float] = Field(None, description="Price change (LTP - YCP)")
    percent: Optional[float] = Field(None, description="Percentage change")
    category: Optional[str] = Field(None, description="Category: A, B, N, Z")
    board: Optional[str] = Field(None, description="Board: PUBLIC, DEBT, etc.")
    sector: Optional[str] = Field(None, description="Sector")
    asset_type: Optional[str] = Field(None, description="Asset type")
    exchange_trade_time: Optional[datetime] = Field(None, description="Exchange trade timestamp (UTC)")
    session_date: Optional[dt_date] = Field(None, description="Session date from feed")
    feed_date: Optional[dt_date] = Field(None, description="Active trading date from feed")
    fetch_id: Optional[int] = Field(None, description="Raw fetch audit identifier")


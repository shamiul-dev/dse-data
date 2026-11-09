from datetime import date as dt_date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DailyEOD(BaseModel):
    """End-Of-Day historical price bar for an instrument."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    symbol: str = Field(..., description="Trading code")
    date: dt_date = Field(..., description="Trading session date")
    open: Optional[float] = Field(None, description="Opening price")
    high: Optional[float] = Field(None, description="Day high")
    low: Optional[float] = Field(None, description="Day low")
    close: Optional[float] = Field(None, description="Day closing price")
    ycp: Optional[float] = Field(None, description="Previous day closing price")
    volume: Optional[int] = Field(0, description="Volume traded")
    value_mn: Optional[float] = Field(0.0, description="Value traded in Millions BDT")
    trades: Optional[int] = Field(0, description="Number of trades")

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Instrument(BaseModel):
    """Represents a listed security on the Dhaka Stock Exchange."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    symbol: str = Field(..., description="Trading code, e.g. GP, BATBC")
    name: Optional[str] = Field(None, description="Full company / security name")
    sector: Optional[str] = Field(None, description="Industrial sector, e.g. Telecommunication")
    category: Optional[str] = Field(None, description="DSE category: A, B, N, Z")
    board: Optional[str] = Field("PUBLIC", description="Trading board: PUBLIC, DEBT, SME, ATB")
    asset_type: Optional[str] = Field("EQ", description="Asset type: EQ (Equity), MF (Mutual Fund), TB (Treasury Bond)")
    face_value: Optional[float] = Field(None, description="Face value per share")
    market_lot: Optional[int] = Field(1, description="Standard market lot size")
    listing_year: Optional[int] = Field(None, description="Year of listing on DSE")


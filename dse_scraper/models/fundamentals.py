from datetime import date as dt_date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CompanyProfile(BaseModel):
    """Company fundamental information, balance sheet, and shareholding pattern."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    symbol: str = Field(..., description="Trading code")
    name: Optional[str] = Field(None, description="Full name of company")
    sector: Optional[str] = Field(None, description="Sector")
    authorized_capital: Optional[float] = Field(None, description="Authorized capital in mn BDT")
    paid_up_capital: Optional[float] = Field(None, description="Paid-up capital in mn BDT")
    market_lot: Optional[int] = Field(1, description="Market lot size")
    face_value: Optional[float] = Field(None, description="Face value per share")
    listing_year: Optional[int] = Field(None, description="Year of listing")

    # Financial Ratios
    eps: Optional[float] = Field(None, description="Earnings Per Share")
    nav_per_share: Optional[float] = Field(None, description="Net Asset Value per share")
    pe_ratio: Optional[float] = Field(None, description="Price to Earnings ratio")

    # Shareholding Distribution (%)
    shareholding_sponsor: Optional[float] = Field(None, description="Sponsor / Director holding %")
    shareholding_govt: Optional[float] = Field(None, description="Government holding %")
    shareholding_institute: Optional[float] = Field(None, description="Institutional holding %")
    shareholding_foreign: Optional[float] = Field(None, description="Foreign holding %")
    shareholding_public: Optional[float] = Field(None, description="Public holding %")
    as_of_date: Optional[dt_date] = Field(None, description="Data reporting date")

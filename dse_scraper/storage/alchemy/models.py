"""
SQLAlchemy 2.0 ORM Declarative Models for DSE data architecture.
"""

from datetime import date, datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, foreign


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RawFetchModel(Base):
    """Audit and provenance table tracking raw scrape invocations."""
    __tablename__ = "raw_fetches"

    fetch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feed_name: Mapped[str] = mapped_column(String(50), nullable=False)
    request_url: Mapped[str] = mapped_column(Text, nullable=False)
    session_date: Mapped[Optional[date]] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_sha256: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        Index("idx_raw_fetches_feed_date", "feed_name", "session_date"),
    )


class SecurityModel(Base):
    """Master Security Registry with immutable surrogate integer ID."""
    __tablename__ = "securities"

    security_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    current_symbol: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    isin: Mapped[Optional[str]] = mapped_column(String(12), unique=True, nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    first_listed_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    attributes_history: Mapped[List["SecurityAttributeHistoryModel"]] = relationship(back_populates="security")


class SecurityAttributeHistoryModel(Base):
    """Slowly Changing Dimensions (SCD Type 2) tracking attribute changes over time."""
    __tablename__ = "security_attributes_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="RESTRICT"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(10))
    board: Mapped[Optional[str]] = mapped_column(String(50), default="PUBLIC")
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    is_marginable: Mapped[bool] = mapped_column(Boolean, default=False)
    operation_status: Mapped[str] = mapped_column(String(50), default="Active")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    security: Mapped["SecurityModel"] = relationship(back_populates="attributes_history")

    __table_args__ = (
        Index("idx_sec_attr_lookup", "security_id", "valid_from", "valid_to"),
        Index("idx_sec_attr_current", "security_id", "is_current"),
    )


class InstrumentModel(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    category: Mapped[Optional[str]] = mapped_column(String(10))
    board: Mapped[Optional[str]] = mapped_column(String(50), default="PUBLIC")
    asset_type: Mapped[Optional[str]] = mapped_column(String(20), default="EQ")
    is_marginable: Mapped[bool] = mapped_column(Boolean, default=False)
    operation_status: Mapped[str] = mapped_column(String(50), default="Active")
    closed_effective_date: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships (No cascade delete-orphan to protect historical records)
    quotes: Mapped[List["QuoteModel"]] = relationship(back_populates="instrument")
    circuit_breakers: Mapped[List["CircuitBreakerModel"]] = relationship(back_populates="instrument")
    financial_filings: Mapped[List["FinancialFilingModel"]] = relationship(back_populates="instrument")
    news_items: Mapped[List["NewsModel"]] = relationship(
        "NewsModel",
        primaryjoin="foreign(NewsModel.symbol) == InstrumentModel.symbol",
        back_populates="instrument",
    )


class QuoteModel(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(30), ForeignKey("instruments.symbol", ondelete="RESTRICT"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    exchange_trade_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    session_date: Mapped[Optional[date]] = mapped_column(Date)
    feed_date: Mapped[Optional[date]] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    fetch_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("raw_fetches.fetch_id", ondelete="SET NULL"), nullable=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="SET NULL"), nullable=True)

    ltp: Mapped[Optional[float]] = mapped_column(Float)
    ycp: Mapped[Optional[float]] = mapped_column(Float)
    open: Mapped[Optional[float]] = mapped_column(Float)
    high: Mapped[Optional[float]] = mapped_column(Float)
    low: Mapped[Optional[float]] = mapped_column(Float)
    close: Mapped[Optional[float]] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    value_mn: Mapped[float] = mapped_column(Float, default=0.0)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    change: Mapped[Optional[float]] = mapped_column(Float)
    percent: Mapped[Optional[float]] = mapped_column(Float)

    instrument: Mapped["InstrumentModel"] = relationship(back_populates="quotes")

    __table_args__ = (
        Index("uq_quotes_symbol_tradetime", "symbol", "exchange_trade_time", unique=True),
        Index("idx_quotes_symbol_time", "symbol", "timestamp"),
    )


class CircuitBreakerModel(Base):
    __tablename__ = "circuit_breakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(30), ForeignKey("instruments.symbol", ondelete="RESTRICT"), index=True)
    session_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    close_price: Mapped[Optional[float]] = mapped_column(Float)
    lower_limit: Mapped[Optional[float]] = mapped_column(Float)
    upper_limit: Mapped[Optional[float]] = mapped_column(Float)
    breaker_pct: Mapped[Optional[float]] = mapped_column(Float)
    tick_size: Mapped[Optional[float]] = mapped_column(Float)
    open_adj_price: Mapped[Optional[float]] = mapped_column(Float)

    instrument: Mapped["InstrumentModel"] = relationship(back_populates="circuit_breakers")

    __table_args__ = (
        Index("idx_cb_sym_date", "symbol", "session_date", unique=True),
    )


class FinancialFilingModel(Base):
    __tablename__ = "financial_filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(30), ForeignKey("instruments.symbol", ondelete="RESTRICT"), index=True)
    financial_year: Mapped[Optional[str]] = mapped_column(String(100))
    quarter: Mapped[Optional[str]] = mapped_column(String(50))
    period: Mapped[Optional[str]] = mapped_column(Text)
    submission_deadline: Mapped[Optional[str]] = mapped_column(String(100))
    submission_date: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[Optional[str]] = mapped_column(Text)

    instrument: Mapped["InstrumentModel"] = relationship(back_populates="financial_filings")


class GoingConcernModel(Base):
    __tablename__ = "going_concern_threats"

    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    company_name: Mapped[Optional[str]] = mapped_column(Text)
    threat_status: Mapped[str] = mapped_column(Text, default="Yes")
    as_of_date: Mapped[date] = mapped_column(Date, default=date.today)


class NewsModel(Base):
    __tablename__ = "news_announcements"

    news_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="SET NULL"), nullable=True, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(Text)
    published_date: Mapped[Optional[str]] = mapped_column(String(50))
    published_time: Mapped[Optional[str]] = mapped_column(String(50))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    news_type: Mapped[Optional[str]] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    body: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    instrument: Mapped[Optional["InstrumentModel"]] = relationship(
        "InstrumentModel",
        primaryjoin="foreign(NewsModel.symbol) == InstrumentModel.symbol",
        back_populates="news_items",
    )


class TrecBrokerModel(Base):
    __tablename__ = "trec_brokers"

    trec_no: Mapped[str] = mapped_column(String(50), primary_key=True)
    trec_code: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    company_name: Mapped[str] = mapped_column(Text)
    representative_name: Mapped[Optional[str]] = mapped_column(Text)
    designation: Mapped[Optional[str]] = mapped_column(Text)
    office_phone: Mapped[Optional[str]] = mapped_column(Text)
    mobile: Mapped[Optional[str]] = mapped_column(Text)
    fax: Mapped[Optional[str]] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)


class MarketSummaryModel(Base):
    __tablename__ = "market_summaries"

    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    dsex_value: Mapped[Optional[float]] = mapped_column(Float)
    dsex_change: Mapped[Optional[float]] = mapped_column(Float)
    ds30_value: Mapped[Optional[float]] = mapped_column(Float)
    ds30_change: Mapped[Optional[float]] = mapped_column(Float)
    dses_value: Mapped[Optional[float]] = mapped_column(Float)
    turnover_mn: Mapped[Optional[float]] = mapped_column(Float)
    total_trades: Mapped[Optional[int]] = mapped_column(Integer)
    total_volume: Mapped[Optional[int]] = mapped_column(Integer)


class DailyEODModel(Base):
    __tablename__ = "daily_eod"

    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Optional[float]] = mapped_column(Float)
    high: Mapped[Optional[float]] = mapped_column(Float)
    low: Mapped[Optional[float]] = mapped_column(Float)
    close: Mapped[Optional[float]] = mapped_column(Float)
    ltp: Mapped[Optional[float]] = mapped_column(Float)
    ycp: Mapped[Optional[float]] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    value_mn: Mapped[float] = mapped_column(Float, default=0.0)
    trades: Mapped[int] = mapped_column(BigInteger, default=0)
    price_type: Mapped[str] = mapped_column(String(20), default="trade")
    session_status: Mapped[str] = mapped_column(String(20), default="traded")
    fetch_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("raw_fetches.fetch_id", ondelete="SET NULL"), nullable=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="SET NULL"), nullable=True)


class CompanyProfileModel(Base):
    __tablename__ = "company_profiles"

    symbol: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    authorized_capital: Mapped[Optional[float]] = mapped_column(Float)
    paid_up_capital: Mapped[Optional[float]] = mapped_column(Float)
    market_lot: Mapped[int] = mapped_column(Integer, default=1)
    face_value: Mapped[Optional[float]] = mapped_column(Float)
    listing_year: Mapped[Optional[int]] = mapped_column(Integer)
    eps: Mapped[Optional[float]] = mapped_column(Float)
    nav_per_share: Mapped[Optional[float]] = mapped_column(Float)
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_sponsor: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_govt: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_institute: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_foreign: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_public: Mapped[Optional[float]] = mapped_column(Float)
    as_of_date: Mapped[Optional[str]] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CompanyFundamentalsHistoryModel(Base):
    """Historical point-in-time fundamentals snapshots (quarterly EPS, NAV, P/E, shareholding)."""
    __tablename__ = "company_fundamentals_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="RESTRICT"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    eps: Mapped[Optional[float]] = mapped_column(Float)
    nav_per_share: Mapped[Optional[float]] = mapped_column(Float)
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    paid_up_capital: Mapped[Optional[float]] = mapped_column(Float)
    authorized_capital: Mapped[Optional[float]] = mapped_column(Float)
    market_lot: Mapped[int] = mapped_column(Integer, default=1)
    face_value: Mapped[Optional[float]] = mapped_column(Float)
    listing_year: Mapped[Optional[int]] = mapped_column(Integer)

    shareholding_sponsor: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_govt: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_institute: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_foreign: Mapped[Optional[float]] = mapped_column(Float)
    shareholding_public: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_fund_sym_asof"),
        Index("idx_fund_lookup", "security_id", "as_of_date"),
    )


class GoingConcernHistoryModel(Base):
    """Point-in-time and interval tracking for going concern threats."""
    __tablename__ = "going_concern_history"

    history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("securities.security_id", ondelete="RESTRICT"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(Text)
    threat_status: Mapped[str] = mapped_column(String(20), default="Yes")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolved_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("symbol", "effective_date", name="uq_gc_sym_date"),
        Index("idx_gc_lookup", "security_id", "is_active"),
    )

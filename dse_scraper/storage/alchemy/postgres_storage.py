"""
PostgreSQL Storage implementation powered by SQLAlchemy 2.0.
Implements BaseStorage with PostgreSQL native upserts (ON CONFLICT DO UPDATE).
"""

from datetime import date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dse_scraper.core.normalizers import safe_date, safe_float, safe_int, safe_str
from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.models.history import DailyEOD
from dse_scraper.models.instrument import Instrument
from dse_scraper.models.quote import InstrumentQuote
from dse_scraper.models.snapshot import LiveSnapshot
from dse_scraper.storage.alchemy.database import DatabaseManager
from dse_scraper.storage.alchemy.models import (
    CircuitBreakerModel,
    CompanyProfileModel,
    DailyEODModel,
    FinancialFilingModel,
    GoingConcernModel,
    InstrumentModel,
    MarketSummaryModel,
    NewsModel,
    QuoteModel,
    TrecBrokerModel,
)
from dse_scraper.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class PostgresAlchemyStorage(BaseStorage):
    """
    Enterprise PostgreSQL persistence engine for Promise ERP.
    Leverages SQLAlchemy 2.0 and PostgreSQL native upserts.
    """

    def __init__(self, db_url: str):
        self.db = DatabaseManager(db_url)
        self.db.init_db()

    def save_snapshot(self, snapshot: LiveSnapshot) -> None:
        """Persists quotes and instruments using PostgreSQL upserts."""
        ts = snapshot.timestamp

        with self.db.session() as sess:
            for q in snapshot.quotes:
                # 1. Upsert Instrument
                inst_stmt = insert(InstrumentModel).values(
                    symbol=q.symbol,
                    category=q.category,
                    board=q.board or "PUBLIC",
                    sector=q.sector,
                    asset_type=q.asset_type or "EQ",
                    updated_at=ts,
                ).on_conflict_do_update(
                    index_elements=[InstrumentModel.symbol],
                    set_={
                        "category": q.category,
                        "board": q.board or "PUBLIC",
                        "sector": q.sector,
                        "asset_type": q.asset_type or "EQ",
                        "updated_at": ts,
                    },
                )
                sess.execute(inst_stmt)

                # 2. Append Quote
                quote_entry = QuoteModel(
                    symbol=q.symbol,
                    timestamp=ts,
                    ltp=q.ltp,
                    ycp=q.ycp,
                    open=q.open,
                    high=q.high,
                    low=q.low,
                    close=q.close,
                    volume=q.volume or 0,
                    value_mn=q.value_mn or 0.0,
                    trades=q.trades or 0,
                    change=q.change,
                    percent=q.percent,
                )
                sess.add(quote_entry)

    def save_instruments(self, instruments: List[Instrument]) -> None:
        now = datetime.now(timezone.utc)
        with self.db.session() as sess:
            for inst in instruments:
                stmt = insert(InstrumentModel).values(
                    symbol=inst.symbol,
                    company_name=inst.name,
                    sector=inst.sector,
                    category=inst.category,
                    board=inst.board or "PUBLIC",
                    asset_type=inst.asset_type or "EQ",
                    updated_at=now,
                ).on_conflict_do_update(
                    index_elements=[InstrumentModel.symbol],
                    set_={
                        "company_name": inst.name,
                        "sector": inst.sector,
                        "category": inst.category,
                        "board": inst.board or "PUBLIC",
                        "asset_type": inst.asset_type or "EQ",
                        "updated_at": now,
                    },
                )
                sess.execute(stmt)

    def save_daily_eod(self, records: List[DailyEOD]) -> None:
        with self.db.session() as sess:
            for r in records:
                stmt = insert(DailyEODModel).values(
                    symbol=r.symbol,
                    date=r.date,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    ycp=r.ycp,
                    volume=r.volume or 0,
                    value_mn=r.value_mn or 0.0,
                    trades=r.trades or 0,
                ).on_conflict_do_update(
                    index_elements=[DailyEODModel.symbol, DailyEODModel.date],
                    set_={
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "ycp": r.ycp,
                        "volume": r.volume or 0,
                        "value_mn": r.value_mn or 0.0,
                        "trades": r.trades or 0,
                    },
                )
                sess.execute(stmt)

    def save_company_profile(self, profile: CompanyProfile) -> None:
        now = datetime.now(timezone.utc)
        as_of = profile.as_of_date.isoformat() if profile.as_of_date else None
        with self.db.session() as sess:
            stmt = insert(CompanyProfileModel).values(
                symbol=profile.symbol,
                name=profile.name,
                sector=profile.sector,
                authorized_capital=profile.authorized_capital,
                paid_up_capital=profile.paid_up_capital,
                market_lot=profile.market_lot or 1,
                face_value=profile.face_value,
                listing_year=profile.listing_year,
                eps=profile.eps,
                nav_per_share=profile.nav_per_share,
                pe_ratio=profile.pe_ratio,
                shareholding_sponsor=profile.shareholding_sponsor,
                shareholding_govt=profile.shareholding_govt,
                shareholding_institute=profile.shareholding_institute,
                shareholding_foreign=profile.shareholding_foreign,
                shareholding_public=profile.shareholding_public,
                as_of_date=as_of,
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=[CompanyProfileModel.symbol],
                set_={
                    "name": profile.name,
                    "sector": profile.sector,
                    "authorized_capital": profile.authorized_capital,
                    "paid_up_capital": profile.paid_up_capital,
                    "market_lot": profile.market_lot or 1,
                    "face_value": profile.face_value,
                    "listing_year": profile.listing_year,
                    "eps": profile.eps,
                    "nav_per_share": profile.nav_per_share,
                    "pe_ratio": profile.pe_ratio,
                    "shareholding_sponsor": profile.shareholding_sponsor,
                    "shareholding_govt": profile.shareholding_govt,
                    "shareholding_institute": profile.shareholding_institute,
                    "shareholding_foreign": profile.shareholding_foreign,
                    "shareholding_public": profile.shareholding_public,
                    "as_of_date": as_of,
                    "updated_at": now,
                },
            )
            sess.execute(stmt)

    def get_instruments(self) -> List[Instrument]:
        with self.db.session() as sess:
            stmt = select(InstrumentModel).order_by(InstrumentModel.symbol.asc())
            rows = sess.scalars(stmt).all()
            return [
                Instrument(
                    symbol=r.symbol,
                    name=r.company_name,
                    sector=r.sector,
                    category=r.category,
                    board=r.board,
                    asset_type=r.asset_type,
                )
                for r in rows
            ]

    def get_latest_quotes(self) -> List[InstrumentQuote]:
        with self.db.session() as sess:
            # Query distinct latest quote per symbol
            stmt = select(QuoteModel).order_by(QuoteModel.symbol.asc(), QuoteModel.timestamp.desc())
            rows = sess.scalars(stmt).all()
            seen = set()
            quotes = []
            for r in rows:
                if r.symbol not in seen:
                    seen.add(r.symbol)
                    quotes.append(
                        InstrumentQuote(
                            symbol=r.symbol,
                            ltp=r.ltp,
                            ycp=r.ycp,
                            open=r.open,
                            high=r.high,
                            low=r.low,
                            close=r.close,
                            volume=r.volume,
                            value_mn=r.value_mn,
                            trades=r.trades,
                            change=r.change,
                            percent=r.percent,
                        )
                    )
            return quotes

    # --- Rich Domain Ingestion Methods ---

    def ingest_unified_entities(self, unified_index: Dict[str, Any]) -> int:
        """Ingests full cross-referenced index into PostgreSQL."""
        now = datetime.now(timezone.utc)
        count = 0

        with self.db.session() as sess:
            for sym, data in unified_index.items():
                # 1. Instrument
                quote_data = data.get("latest_quote") or {}
                inst_stmt = insert(InstrumentModel).values(
                    symbol=sym,
                    company_name=data.get("company_name"),
                    sector=quote_data.get("sector"),
                    category=quote_data.get("category"),
                    board=quote_data.get("board", "PUBLIC"),
                    asset_type=quote_data.get("asset_type", "EQ"),
                    is_marginable=bool(data.get("is_marginable", False)),
                    operation_status=data.get("operation_status", "Active"),
                    closed_effective_date=data.get("closed_effective_date"),
                    updated_at=now,
                ).on_conflict_do_update(
                    index_elements=[InstrumentModel.symbol],
                    set_={
                        "company_name": data.get("company_name"),
                        "sector": quote_data.get("sector"),
                        "category": quote_data.get("category"),
                        "board": quote_data.get("board", "PUBLIC"),
                        "asset_type": quote_data.get("asset_type", "EQ"),
                        "is_marginable": bool(data.get("is_marginable", False)),
                        "operation_status": data.get("operation_status", "Active"),
                        "closed_effective_date": data.get("closed_effective_date"),
                        "updated_at": now,
                    },
                )
                sess.execute(inst_stmt)

                # 2. Circuit Breaker
                cb = data.get("circuit_breaker")
                if cb:
                    cb_stmt = insert(CircuitBreakerModel).values(
                        symbol=sym,
                        session_date=date.today(),
                        lower_limit=cb.get("lower_limit"),
                        upper_limit=cb.get("upper_limit"),
                        breaker_pct=cb.get("breaker_pct"),
                        tick_size=cb.get("tick_size"),
                    ).on_conflict_do_update(
                        index_elements=[CircuitBreakerModel.symbol, CircuitBreakerModel.session_date],
                        set_={
                            "lower_limit": cb.get("lower_limit"),
                            "upper_limit": cb.get("upper_limit"),
                            "breaker_pct": cb.get("breaker_pct"),
                            "tick_size": cb.get("tick_size"),
                        },
                    )
                    sess.execute(cb_stmt)

                # 3. Financial Filing Status
                filing = data.get("financial_filing")
                if filing:
                    sess.add(
                        FinancialFilingModel(
                            symbol=sym,
                            quarter=filing.get("quarter"),
                            period=filing.get("period"),
                            status=filing.get("status"),
                            submission_date=filing.get("submission_date"),
                            submission_deadline=filing.get("submission_deadline"),
                        )
                    )

                # 4. Going Concern Threat
                gc = data.get("going_concern_threat")
                if gc:
                    gc_stmt = insert(GoingConcernModel).values(
                        symbol=sym,
                        company_name=data.get("company_name"),
                        threat_status=gc,
                        as_of_date=date.today(),
                    ).on_conflict_do_update(
                        index_elements=[GoingConcernModel.symbol],
                        set_={"threat_status": gc, "as_of_date": date.today()},
                    )
                    sess.execute(gc_stmt)

                count += 1

        logger.info("Ingested %d unified entities into PostgreSQL.", count)
        return count

    def ingest_news(self, news_items: List[Dict[str, Any]]) -> int:
        count = 0
        with self.db.session() as sess:
            for n in news_items:
                news_id = n.get("news_id") or f"{n.get('symbol')}_{n.get('date')}_{hash(n.get('summary'))}"
                stmt = insert(NewsModel).values(
                    news_id=news_id,
                    symbol=n.get("symbol"),
                    company_name=n.get("company_name"),
                    published_date=n.get("date"),
                    published_time=n.get("time"),
                    news_type=n.get("type"),
                    summary=n.get("summary") or "",
                    body=n.get("body"),
                ).on_conflict_do_update(
                    index_elements=[NewsModel.news_id],
                    set_={
                        "symbol": n.get("symbol"),
                        "company_name": n.get("company_name"),
                        "published_date": n.get("date"),
                        "published_time": n.get("time"),
                        "news_type": n.get("type"),
                        "summary": n.get("summary") or "",
                        "body": n.get("body"),
                    },
                )
                sess.execute(stmt)
                count += 1
        logger.info("Ingested %d news items into PostgreSQL.", count)
        return count

    def ingest_trec_brokers(self, brokers: List[Dict[str, Any]]) -> int:
        count = 0
        with self.db.session() as sess:
            for b in brokers:
                trec_no = str(b.get("trec_no") or b.get("sl_no"))
                stmt = insert(TrecBrokerModel).values(
                    trec_no=trec_no,
                    trec_code=b.get("trec_code"),
                    company_name=b.get("company_name") or "Unknown",
                    representative_name=b.get("representative_name"),
                    designation=b.get("designation"),
                    office_phone=b.get("office_phone"),
                    mobile=b.get("mobile"),
                    fax=b.get("fax"),
                    address=b.get("address"),
                ).on_conflict_do_update(
                    index_elements=[TrecBrokerModel.trec_no],
                    set_={
                        "trec_code": b.get("trec_code"),
                        "company_name": b.get("company_name") or "Unknown",
                        "representative_name": b.get("representative_name"),
                        "designation": b.get("designation"),
                        "office_phone": b.get("office_phone"),
                        "mobile": b.get("mobile"),
                        "fax": b.get("fax"),
                        "address": b.get("address"),
                    },
                )
                sess.execute(stmt)
                count += 1
        logger.info("Ingested %d TREC brokers into PostgreSQL.", count)
        return count

    def ingest_market_summaries(self, summaries: List[Dict[str, Any]]) -> int:
        count = 0
        with self.db.session() as sess:
            for s in summaries:
                s_date = safe_date(s.get("date"))
                if not s_date:
                    continue
                stmt = insert(MarketSummaryModel).values(
                    session_date=s_date,
                    dsex_value=safe_float(s.get("dsex")),
                    dsex_change=safe_float(s.get("dsexChange")),
                    ds30_value=safe_float(s.get("ds30")),
                    ds30_change=safe_float(s.get("ds30Change")),
                    dses_value=safe_float(s.get("dses")),
                    turnover_mn=safe_float(s.get("turnover")),
                    total_trades=safe_int(s.get("trades")),
                    total_volume=safe_int(s.get("volume")),
                ).on_conflict_do_update(
                    index_elements=[MarketSummaryModel.session_date],
                    set_={
                        "dsex_value": safe_float(s.get("dsex")),
                        "dsex_change": safe_float(s.get("dsexChange")),
                        "ds30_value": safe_float(s.get("ds30")),
                        "ds30_change": safe_float(s.get("ds30Change")),
                        "dses_value": safe_float(s.get("dses")),
                        "turnover_mn": safe_float(s.get("turnover")),
                        "total_trades": safe_int(s.get("trades")),
                        "total_volume": safe_int(s.get("volume")),
                    },
                )
                sess.execute(stmt)
                count += 1
        logger.info("Ingested %d market summary sessions into PostgreSQL.", count)
        return count


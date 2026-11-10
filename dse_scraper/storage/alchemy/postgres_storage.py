"""
PostgreSQL Storage implementation powered by SQLAlchemy 2.0.
Implements BaseStorage with PostgreSQL native upserts (ON CONFLICT DO UPDATE).
Full provenance tracking, audit logging, SCD Type 2, and point-in-time fundamentals.
"""

from datetime import date, datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
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
    CompanyFundamentalsHistoryModel,
    CompanyProfileModel,
    DailyEODModel,
    FinancialFilingModel,
    GoingConcernHistoryModel,
    GoingConcernModel,
    InstrumentModel,
    MarketSummaryModel,
    NewsModel,
    QuoteModel,
    RawFetchModel,
    SecurityModel,
    TrecBrokerModel,
)
from dse_scraper.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class PostgresAlchemyStorage(BaseStorage):
    """
    Enterprise PostgreSQL persistence engine for DSE Data Engine.
    Leverages SQLAlchemy 2.0 and PostgreSQL native upserts.
    """

    def __init__(self, db_url: str):
        self.db = DatabaseManager(db_url)
        self.db.init_db()

    def save_snapshot(self, snapshot: LiveSnapshot) -> None:
        """Persists quotes and instruments using PostgreSQL upserts with audit provenance."""
        ts = snapshot.timestamp

        with self.db.session() as sess:
            # 1. Record raw_fetch audit entry
            fetch_entry = RawFetchModel(
                feed_name="live_snapshot",
                request_url="https://www.dse.com.bd/api/live/snapshot",
                session_date=snapshot.session_date,
                fetched_at=ts,
                http_status=200,
                record_count=len(snapshot.quotes),
            )
            sess.add(fetch_entry)
            sess.flush()
            fetch_id = fetch_entry.fetch_id

            # Cache symbol -> security_id lookup
            sec_rows = sess.execute(select(SecurityModel.current_symbol, SecurityModel.security_id)).fetchall()
            sec_map = {row[0]: row[1] for row in sec_rows}

            for q in snapshot.quotes:
                # 2. Upsert Instrument
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

                # 3. Insert Quote (Idempotent by (symbol, exchange_trade_time))
                sec_id = sec_map.get(q.symbol)
                quote_stmt = insert(QuoteModel).values(
                    symbol=q.symbol,
                    timestamp=ts,
                    exchange_trade_time=q.exchange_trade_time,
                    session_date=q.session_date,
                    feed_date=q.feed_date,
                    fetched_at=ts,
                    fetch_id=fetch_id,
                    security_id=sec_id,
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
                if q.exchange_trade_time is not None:
                    quote_stmt = quote_stmt.on_conflict_do_nothing(
                        index_elements=[QuoteModel.symbol, QuoteModel.exchange_trade_time]
                    )
                sess.execute(quote_stmt)

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

                # Also ensure securities master record exists
                sec_stmt = insert(SecurityModel).values(
                    current_symbol=inst.symbol,
                    company_name=inst.name,
                    updated_at=now,
                ).on_conflict_do_update(
                    index_elements=[SecurityModel.current_symbol],
                    set_={"company_name": inst.name, "updated_at": now},
                )
                sess.execute(sec_stmt)

    def save_daily_eod(self, records: List[DailyEOD], fetch_id: Optional[int] = None) -> None:
        if not records:
            return
        with self.db.session() as sess:
            sec_rows = sess.execute(select(SecurityModel.current_symbol, SecurityModel.security_id)).fetchall()
            sec_map = {row[0]: row[1] for row in sec_rows}

            val_list = [
                {
                    "symbol": r.symbol,
                    "date": r.date,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "ltp": getattr(r, "ltp", None),
                    "ycp": r.ycp,
                    "volume": r.volume or 0,
                    "value_mn": r.value_mn or 0.0,
                    "trades": r.trades or 0,
                    "price_type": getattr(r, "price_type", "trade") or "trade",
                    "session_status": getattr(r, "session_status", "traded") or "traded",
                    "fetch_id": fetch_id,
                    "security_id": sec_map.get(r.symbol),
                }
                for r in records
            ]
            stmt = insert(DailyEODModel)
            stmt = stmt.on_conflict_do_update(
                index_elements=[DailyEODModel.symbol, DailyEODModel.date],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "ltp": stmt.excluded.ltp,
                    "ycp": stmt.excluded.ycp,
                    "volume": stmt.excluded.volume,
                    "value_mn": stmt.excluded.value_mn,
                    "trades": stmt.excluded.trades,
                    "price_type": stmt.excluded.price_type,
                    "session_status": stmt.excluded.session_status,
                    "fetch_id": stmt.excluded.fetch_id,
                    "security_id": stmt.excluded.security_id,
                },
            )
            sess.execute(stmt, val_list)

    def save_company_profile(self, profile: CompanyProfile) -> None:
        now = datetime.now(timezone.utc)
        as_of = profile.as_of_date.isoformat() if profile.as_of_date else None
        as_of_dt = profile.as_of_date or date.today()

        with self.db.session() as sess:
            sec_stmt = select(SecurityModel.security_id).where(SecurityModel.current_symbol == profile.symbol)
            sec_id = sess.scalars(sec_stmt).first()

            # 1. Upsert flat current-state table
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

            # 2. Upsert point-in-time fundamentals history
            fund_stmt = insert(CompanyFundamentalsHistoryModel).values(
                security_id=sec_id,
                symbol=profile.symbol,
                as_of_date=as_of_dt,
                eps=profile.eps,
                nav_per_share=profile.nav_per_share,
                pe_ratio=profile.pe_ratio,
                paid_up_capital=profile.paid_up_capital,
                authorized_capital=profile.authorized_capital,
                market_lot=profile.market_lot or 1,
                face_value=profile.face_value,
                listing_year=profile.listing_year,
                shareholding_sponsor=profile.shareholding_sponsor,
                shareholding_govt=profile.shareholding_govt,
                shareholding_institute=profile.shareholding_institute,
                shareholding_foreign=profile.shareholding_foreign,
                shareholding_public=profile.shareholding_public,
            ).on_conflict_do_update(
                index_elements=[CompanyFundamentalsHistoryModel.symbol, CompanyFundamentalsHistoryModel.as_of_date],
                set_={
                    "security_id": sec_id,
                    "eps": profile.eps,
                    "nav_per_share": profile.nav_per_share,
                    "pe_ratio": profile.pe_ratio,
                    "paid_up_capital": profile.paid_up_capital,
                    "authorized_capital": profile.authorized_capital,
                    "market_lot": profile.market_lot or 1,
                    "face_value": profile.face_value,
                    "listing_year": profile.listing_year,
                    "shareholding_sponsor": profile.shareholding_sponsor,
                    "shareholding_govt": profile.shareholding_govt,
                    "shareholding_institute": profile.shareholding_institute,
                    "shareholding_foreign": profile.shareholding_foreign,
                    "shareholding_public": profile.shareholding_public,
                },
            )
            sess.execute(fund_stmt)

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
                            exchange_trade_time=r.exchange_trade_time,
                            session_date=r.session_date,
                            feed_date=r.feed_date,
                            fetch_id=r.fetch_id,
                        )
                    )
            return quotes

    # --- Rich Domain Ingestion Methods ---

    def ingest_unified_entities(self, unified_index: Dict[str, Any]) -> int:
        """Ingests full cross-referenced index into PostgreSQL."""
        now = datetime.now(timezone.utc)
        count = 0

        with self.db.session() as sess:
            # Preload security_id lookup
            sec_rows = sess.execute(select(SecurityModel.current_symbol, SecurityModel.security_id)).fetchall()
            sec_map = {row[0]: row[1] for row in sec_rows}

            for sym, data in unified_index.items():
                quote_data = data.get("latest_quote") or {}
                sec_id = sec_map.get(sym)

                # 1. Instrument
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
                        close_price=cb.get("close_price"),
                        lower_limit=cb.get("lower_limit"),
                        upper_limit=cb.get("upper_limit"),
                        breaker_pct=cb.get("breaker_pct"),
                        tick_size=cb.get("tick_size"),
                        open_adj_price=cb.get("open_adj_price"),
                    ).on_conflict_do_update(
                        index_elements=[CircuitBreakerModel.symbol, CircuitBreakerModel.session_date],
                        set_={
                            "close_price": cb.get("close_price"),
                            "lower_limit": cb.get("lower_limit"),
                            "upper_limit": cb.get("upper_limit"),
                            "breaker_pct": cb.get("breaker_pct"),
                            "tick_size": cb.get("tick_size"),
                            "open_adj_price": cb.get("open_adj_price"),
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

                # 4. Going Concern Threat (Current & History)
                gc = data.get("going_concern_threat")
                if gc:
                    gc_stmt = insert(GoingConcernModel).values(
                        symbol=sym,
                        company_name=data.get("company_name"),
                        threat_status=gc,
                        as_of_date=date.today(),
                    ).on_conflict_do_update(
                        index_elements=[GoingConcernModel.symbol],
                        set_={
                            "company_name": data.get("company_name"),
                            "threat_status": gc,
                            "as_of_date": date.today(),
                        },
                    )
                    sess.execute(gc_stmt)

                    gc_hist_stmt = insert(GoingConcernHistoryModel).values(
                        security_id=sec_id,
                        symbol=sym,
                        company_name=data.get("company_name"),
                        threat_status=gc,
                        effective_date=date.today(),
                        is_active=True,
                    ).on_conflict_do_update(
                        index_elements=[GoingConcernHistoryModel.symbol, GoingConcernHistoryModel.effective_date],
                        set_={
                            "security_id": sec_id,
                            "company_name": data.get("company_name"),
                            "threat_status": gc,
                            "is_active": True,
                        },
                    )
                    sess.execute(gc_hist_stmt)

                count += 1

        logger.info("Ingested %d unified entities into PostgreSQL.", count)
        return count

    def ingest_news(self, news_items: List[Dict[str, Any]]) -> int:
        count = 0
        dhaka_tz = ZoneInfo("Asia/Dhaka")

        with self.db.session() as sess:
            sec_rows = sess.execute(select(SecurityModel.current_symbol, SecurityModel.security_id)).fetchall()
            sec_map = {row[0]: row[1] for row in sec_rows}

            for n in news_items:
                sym = n.get("symbol")
                news_id = n.get("news_id") or f"{sym}_{n.get('date')}_{hash(n.get('summary'))}"
                pub_date_str = n.get("date")
                pub_time_str = n.get("time") or "00:00"

                published_at = None
                if pub_date_str:
                    try:
                        clean_time = pub_time_str.strip() if ":" in str(pub_time_str) else "00:00"
                        dt = datetime.strptime(f"{pub_date_str.strip()} {clean_time}", "%d %b %Y %H:%M")
                        published_at = dt.replace(tzinfo=dhaka_tz).astimezone(timezone.utc)
                    except Exception:
                        pass

                stmt = insert(NewsModel).values(
                    news_id=news_id,
                    symbol=sym,
                    security_id=sec_map.get(sym),
                    company_name=n.get("company_name"),
                    published_date=pub_date_str,
                    published_time=pub_time_str,
                    published_at=published_at,
                    news_type=n.get("type"),
                    summary=n.get("summary") or "",
                    body=n.get("body"),
                ).on_conflict_do_update(
                    index_elements=[NewsModel.news_id],
                    set_={
                        "symbol": sym,
                        "security_id": sec_map.get(sym),
                        "company_name": n.get("company_name"),
                        "published_date": pub_date_str,
                        "published_time": pub_time_str,
                        "published_at": published_at,
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

    def ingest_market_summary(self, summary_data: Dict[str, Any]) -> None:
        """Saves daily market index summary (DSEX, DS30, Turnover)."""
        sess_date = safe_date(summary_data.get("session_date"))
        if not sess_date:
            return

        with self.db.session() as sess:
            stmt = insert(MarketSummaryModel).values(
                session_date=sess_date,
                dsex_value=safe_float(summary_data.get("dsex_value")),
                dsex_change=safe_float(summary_data.get("dsex_change")),
                ds30_value=safe_float(summary_data.get("ds30_value")),
                ds30_change=safe_float(summary_data.get("ds30_change")),
                dses_value=safe_float(summary_data.get("dses_value")),
                turnover_mn=safe_float(summary_data.get("turnover_mn")),
                total_trades=safe_int(summary_data.get("total_trades")),
                total_volume=safe_int(summary_data.get("total_volume")),
            ).on_conflict_do_update(
                index_elements=[MarketSummaryModel.session_date],
                set_={
                    "dsex_value": safe_float(summary_data.get("dsex_value")),
                    "dsex_change": safe_float(summary_data.get("dsex_change")),
                    "ds30_value": safe_float(summary_data.get("ds30_value")),
                    "ds30_change": safe_float(summary_data.get("ds30_change")),
                    "dses_value": safe_float(summary_data.get("dses_value")),
                    "turnover_mn": safe_float(summary_data.get("turnover_mn")),
                    "total_trades": safe_int(summary_data.get("total_trades")),
                    "total_volume": safe_int(summary_data.get("total_volume")),
                },
            )
            sess.execute(stmt)

"""
Production-grade SQLite storage implementation with WAL mode,
transaction isolation, and idempotent upserts.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Generator, List, Optional

from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.models.history import DailyEOD
from dse_scraper.models.instrument import Instrument
from dse_scraper.models.quote import InstrumentQuote
from dse_scraper.models.snapshot import LiveSnapshot
from dse_scraper.storage.base import BaseStorage


class SQLiteStorage(BaseStorage):
    """
    SQLite persistence layer optimized for time-series stock data.
    Enables WAL mode for concurrent read/write and ensures idempotent operations.
    Properly closes connections to avoid Windows file locks.
    """

    def __init__(self, db_path: str = "dse_market.db"):
        self.db_path = Path(db_path).resolve()
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS instruments (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    category TEXT,
                    board TEXT,
                    asset_type TEXT,
                    face_value REAL,
                    market_lot INTEGER,
                    listing_year INTEGER,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_indices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    index_key TEXT NOT NULL,
                    value REAL NOT NULL,
                    change REAL,
                    percent REAL,
                    prev REAL
                );
                CREATE INDEX IF NOT EXISTS idx_indices_key_time ON market_indices(index_key, timestamp);

                CREATE TABLE IF NOT EXISTS market_totals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    trades INTEGER,
                    volume INTEGER,
                    turnover_mn REAL,
                    market_cap REAL
                );

                CREATE TABLE IF NOT EXISTS latest_quotes (
                    symbol TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    ltp REAL,
                    ycp REAL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    value_mn REAL,
                    trades INTEGER,
                    change REAL,
                    percent REAL,
                    category TEXT,
                    board TEXT,
                    sector TEXT,
                    asset_type TEXT
                );

                CREATE TABLE IF NOT EXISTS intraday_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    ltp REAL,
                    high REAL,
                    low REAL,
                    volume INTEGER,
                    value_mn REAL,
                    trades INTEGER,
                    percent REAL
                );
                CREATE INDEX IF NOT EXISTS idx_ticks_sym_time ON intraday_ticks(symbol, timestamp);

                CREATE TABLE IF NOT EXISTS daily_eod (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    ycp REAL,
                    volume INTEGER,
                    value_mn REAL,
                    trades INTEGER,
                    PRIMARY KEY (symbol, date)
                );

                CREATE TABLE IF NOT EXISTS company_profiles (
                    symbol TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    authorized_capital REAL,
                    paid_up_capital REAL,
                    market_lot INTEGER,
                    face_value REAL,
                    listing_year INTEGER,
                    eps REAL,
                    nav_per_share REAL,
                    pe_ratio REAL,
                    shareholding_sponsor REAL,
                    shareholding_govt REAL,
                    shareholding_institute REAL,
                    shareholding_foreign REAL,
                    shareholding_public REAL,
                    as_of_date TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def save_snapshot(self, snapshot: LiveSnapshot) -> None:
        """Atomically persist snapshot: indices, totals, latest quotes, and ticks."""
        ts = snapshot.timestamp.isoformat()

        with self._connection() as conn:
            cursor = conn.cursor()

            # 1. Market Indices
            for idx in snapshot.indices:
                cursor.execute(
                    """
                    INSERT INTO market_indices (timestamp, index_key, value, change, percent, prev)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ts, idx.key, idx.value, idx.change, idx.percent, idx.prev),
                )

            # 2. Market Totals
            if snapshot.totals:
                t = snapshot.totals
                cursor.execute(
                    """
                    INSERT INTO market_totals (timestamp, trades, volume, turnover_mn, market_cap)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ts, t.trades, t.volume, t.turnover_mn, t.market_cap),
                )

            # 3. Quotes & Instruments
            for q in snapshot.quotes:
                # Upsert master instrument registry
                cursor.execute(
                    """
                    INSERT INTO instruments (symbol, category, board, sector, asset_type, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        category=COALESCE(excluded.category, instruments.category),
                        board=COALESCE(excluded.board, instruments.board),
                        sector=COALESCE(excluded.sector, instruments.sector),
                        asset_type=COALESCE(excluded.asset_type, instruments.asset_type),
                        updated_at=excluded.updated_at
                    """,
                    (q.symbol, q.category, q.board, q.sector, q.asset_type, ts),
                )

                # Upsert latest quotes
                cursor.execute(
                    """
                    INSERT INTO latest_quotes (
                        symbol, timestamp, ltp, ycp, open, high, low, close,
                        volume, value_mn, trades, change, percent, category, board, sector, asset_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        timestamp=excluded.timestamp,
                        ltp=excluded.ltp,
                        ycp=excluded.ycp,
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        volume=excluded.volume,
                        value_mn=excluded.value_mn,
                        trades=excluded.trades,
                        change=excluded.change,
                        percent=excluded.percent,
                        category=COALESCE(excluded.category, latest_quotes.category),
                        board=COALESCE(excluded.board, latest_quotes.board),
                        sector=COALESCE(excluded.sector, latest_quotes.sector),
                        asset_type=COALESCE(excluded.asset_type, latest_quotes.asset_type)
                    """,
                    (
                        q.symbol, ts, q.ltp, q.ycp, q.open, q.high, q.low, q.close,
                        q.volume, q.value_mn, q.trades, q.change, q.percent,
                        q.category, q.board, q.sector, q.asset_type
                    ),
                )

                # Append intraday tick if LTP is active
                if q.ltp and q.ltp > 0:
                    cursor.execute(
                        """
                        INSERT INTO intraday_ticks (timestamp, symbol, ltp, high, low, volume, value_mn, trades, percent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (ts, q.symbol, q.ltp, q.high, q.low, q.volume, q.value_mn, q.trades, q.percent),
                    )

            conn.commit()

    def save_instruments(self, instruments: List[Instrument]) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            for inst in instruments:
                conn.execute(
                    """
                    INSERT INTO instruments (symbol, name, sector, category, board, asset_type, face_value, market_lot, listing_year, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        name=COALESCE(excluded.name, instruments.name),
                        sector=COALESCE(excluded.sector, instruments.sector),
                        category=COALESCE(excluded.category, instruments.category),
                        board=COALESCE(excluded.board, instruments.board),
                        asset_type=COALESCE(excluded.asset_type, instruments.asset_type),
                        face_value=COALESCE(excluded.face_value, instruments.face_value),
                        market_lot=COALESCE(excluded.market_lot, instruments.market_lot),
                        listing_year=COALESCE(excluded.listing_year, instruments.listing_year),
                        updated_at=excluded.updated_at
                    """,
                    (
                        inst.symbol, inst.name, inst.sector, inst.category, inst.board,
                        inst.asset_type, inst.face_value, inst.market_lot, inst.listing_year, ts
                    ),
                )
            conn.commit()

    def save_daily_eod(self, records: List[DailyEOD]) -> None:
        with self._connection() as conn:
            for r in records:
                conn.execute(
                    """
                    INSERT INTO daily_eod (symbol, date, open, high, low, close, ycp, volume, value_mn, trades)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, date) DO UPDATE SET
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        ycp=excluded.ycp,
                        volume=excluded.volume,
                        value_mn=excluded.value_mn,
                        trades=excluded.trades
                    """,
                    (
                        r.symbol, r.date.isoformat(), r.open, r.high, r.low,
                        r.close, r.ycp, r.volume, r.value_mn, r.trades
                    ),
                )
            conn.commit()

    def save_company_profile(self, profile: CompanyProfile) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        as_of = profile.as_of_date.isoformat() if profile.as_of_date else None

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO company_profiles (
                    symbol, name, sector, authorized_capital, paid_up_capital,
                    market_lot, face_value, listing_year, eps, nav_per_share,
                    pe_ratio, shareholding_sponsor, shareholding_govt, shareholding_institute,
                    shareholding_foreign, shareholding_public, as_of_date, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=COALESCE(excluded.name, company_profiles.name),
                    sector=COALESCE(excluded.sector, company_profiles.sector),
                    authorized_capital=COALESCE(excluded.authorized_capital, company_profiles.authorized_capital),
                    paid_up_capital=COALESCE(excluded.paid_up_capital, company_profiles.paid_up_capital),
                    market_lot=COALESCE(excluded.market_lot, company_profiles.market_lot),
                    face_value=COALESCE(excluded.face_value, company_profiles.face_value),
                    listing_year=COALESCE(excluded.listing_year, company_profiles.listing_year),
                    eps=COALESCE(excluded.eps, company_profiles.eps),
                    nav_per_share=COALESCE(excluded.nav_per_share, company_profiles.nav_per_share),
                    pe_ratio=COALESCE(excluded.pe_ratio, company_profiles.pe_ratio),
                    shareholding_sponsor=COALESCE(excluded.shareholding_sponsor, company_profiles.shareholding_sponsor),
                    shareholding_govt=COALESCE(excluded.shareholding_govt, company_profiles.shareholding_govt),
                    shareholding_institute=COALESCE(excluded.shareholding_institute, company_profiles.shareholding_institute),
                    shareholding_foreign=COALESCE(excluded.shareholding_foreign, company_profiles.shareholding_foreign),
                    shareholding_public=COALESCE(excluded.shareholding_public, company_profiles.shareholding_public),
                    as_of_date=COALESCE(excluded.as_of_date, company_profiles.as_of_date),
                    updated_at=excluded.updated_at
                """,
                (
                    profile.symbol, profile.name, profile.sector, profile.authorized_capital,
                    profile.paid_up_capital, profile.market_lot, profile.face_value, profile.listing_year,
                    profile.eps, profile.nav_per_share, profile.pe_ratio,
                    profile.shareholding_sponsor, profile.shareholding_govt, profile.shareholding_institute,
                    profile.shareholding_foreign, profile.shareholding_public, as_of, ts
                ),
            )
            conn.commit()

    def get_instruments(self) -> List[Instrument]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM instruments ORDER BY symbol ASC").fetchall()
            return [
                Instrument(
                    symbol=r["symbol"],
                    name=r["name"],
                    sector=r["sector"],
                    category=r["category"],
                    board=r["board"],
                    asset_type=r["asset_type"],
                    face_value=r["face_value"],
                    market_lot=r["market_lot"],
                    listing_year=r["listing_year"],
                )
                for r in rows
            ]

    def get_latest_quotes(self) -> List[InstrumentQuote]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM latest_quotes ORDER BY symbol ASC").fetchall()
            return [
                InstrumentQuote(
                    symbol=r["symbol"],
                    ltp=r["ltp"],
                    ycp=r["ycp"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"],
                    value_mn=r["value_mn"],
                    trades=r["trades"],
                    change=r["change"],
                    percent=r["percent"],
                    category=r["category"],
                    board=r["board"],
                    sector=r["sector"],
                    asset_type=r["asset_type"],
                )
                for r in rows
            ]

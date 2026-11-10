"""
Migration script for Phase 1: Ingestion Hardening.
Applies non-destructive schema changes to PostgreSQL:
1. Creates raw_fetches audit table.
2. Adds ltp, price_type, session_status, and fetch_id to daily_eod.
3. Adds exchange_trade_time, session_date, feed_date, fetched_at, fetch_id to quotes.
4. Adds unique index uq_quotes_symbol_tradetime on quotes (symbol, exchange_trade_time).
5. Adds close_price to circuit_breakers.
6. Changes foreign key delete rules from CASCADE to RESTRICT on instruments child tables.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from dse_scraper.config import DSEConfig
from dse_scraper.storage.alchemy.database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger(__name__)

MIGRATION_STATEMENTS = [
    # 1. raw_fetches
    """
    CREATE TABLE IF NOT EXISTS raw_fetches (
        fetch_id BIGSERIAL PRIMARY KEY,
        feed_name VARCHAR(50) NOT NULL,
        request_url TEXT NOT NULL,
        session_date DATE,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        http_status INT NOT NULL,
        record_count INT DEFAULT 0,
        payload_sha256 VARCHAR(64)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_raw_fetches_feed_date ON raw_fetches(feed_name, session_date);",

    # 2. daily_eod
    """
    ALTER TABLE daily_eod
        ADD COLUMN IF NOT EXISTS ltp NUMERIC(18, 4),
        ADD COLUMN IF NOT EXISTS price_type VARCHAR(20) NOT NULL DEFAULT 'trade',
        ADD COLUMN IF NOT EXISTS session_status VARCHAR(20) NOT NULL DEFAULT 'traded',
        ADD COLUMN IF NOT EXISTS fetch_id BIGINT REFERENCES raw_fetches(fetch_id) ON DELETE SET NULL;
    """,

    # 3. quotes
    """
    ALTER TABLE quotes
        ADD COLUMN IF NOT EXISTS exchange_trade_time TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS session_date DATE,
        ADD COLUMN IF NOT EXISTS feed_date DATE,
        ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ADD COLUMN IF NOT EXISTS fetch_id BIGINT REFERENCES raw_fetches(fetch_id) ON DELETE SET NULL;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_quotes_symbol_tradetime'
        ) THEN
            ALTER TABLE quotes ADD CONSTRAINT uq_quotes_symbol_tradetime UNIQUE (symbol, exchange_trade_time);
        END IF;
    END $$;
    """,

    # 4. circuit_breakers
    """
    ALTER TABLE circuit_breakers
        ADD COLUMN IF NOT EXISTS close_price NUMERIC(18, 4);
    """,

    # 5. Foreign Keys: Change CASCADE to RESTRICT
    """
    ALTER TABLE quotes DROP CONSTRAINT IF EXISTS quotes_symbol_fkey;
    """,
    """
    ALTER TABLE quotes ADD CONSTRAINT quotes_symbol_fkey
        FOREIGN KEY (symbol) REFERENCES instruments(symbol) ON DELETE RESTRICT;
    """,
    """
    ALTER TABLE circuit_breakers DROP CONSTRAINT IF EXISTS circuit_breakers_symbol_fkey;
    """,
    """
    ALTER TABLE circuit_breakers ADD CONSTRAINT circuit_breakers_symbol_fkey
        FOREIGN KEY (symbol) REFERENCES instruments(symbol) ON DELETE RESTRICT;
    """,
    """
    ALTER TABLE financial_filings DROP CONSTRAINT IF EXISTS financial_filings_symbol_fkey;
    """,
    """
    ALTER TABLE financial_filings ADD CONSTRAINT financial_filings_symbol_fkey
        FOREIGN KEY (symbol) REFERENCES instruments(symbol) ON DELETE RESTRICT;
    """
]


def run_migration():
    config = DSEConfig()
    mgr = DatabaseManager(config.postgres_url)
    logger.info("Executing Phase 1 schema migration against %s...", config.postgres_url.split("@")[-1])

    with mgr.engine.begin() as conn:
        for stmt in MIGRATION_STATEMENTS:
            cleaned = stmt.strip()
            if cleaned:
                conn.execute(text(cleaned))

    logger.info("Phase 1 schema migration completed successfully.")


if __name__ == "__main__":
    run_migration()

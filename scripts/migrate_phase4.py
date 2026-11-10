"""
Migration script for Phase 4: Fundamental & Filing History, News Timestamps.
1. Creates company_fundamentals_history table (dated fundamental snapshots).
2. Seeds company_fundamentals_history from existing company_profiles.
3. Creates going_concern_history table (effective date tracking).
4. Seeds going_concern_history from existing going_concern_threats.
5. Adds security_id and published_at TIMESTAMPTZ to news_announcements.
6. Backfills published_at (Asia/Dhaka -> UTC) and links security_id on all news items.
"""

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from dse_scraper.config import DSEConfig
from dse_scraper.storage.alchemy.database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger(__name__)

MIGRATION_STATEMENTS = [
    # 1. company_fundamentals_history table
    """
    CREATE TABLE IF NOT EXISTS company_fundamentals_history (
        history_id BIGSERIAL PRIMARY KEY,
        security_id INT REFERENCES securities(security_id) ON DELETE RESTRICT,
        symbol VARCHAR(30) NOT NULL,
        as_of_date DATE NOT NULL,
        eps NUMERIC(18, 4),
        nav_per_share NUMERIC(18, 4),
        pe_ratio NUMERIC(18, 4),
        paid_up_capital NUMERIC(18, 4),
        authorized_capital NUMERIC(18, 4),
        market_lot INT DEFAULT 1,
        face_value NUMERIC(18, 4),
        listing_year INT,
        shareholding_sponsor NUMERIC(8, 4),
        shareholding_govt NUMERIC(8, 4),
        shareholding_institute NUMERIC(8, 4),
        shareholding_foreign NUMERIC(8, 4),
        shareholding_public NUMERIC(8, 4),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_fund_sym_asof UNIQUE (symbol, as_of_date)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_fund_lookup ON company_fundamentals_history(security_id, as_of_date);",

    # 2. Seed company_fundamentals_history from company_profiles
    """
    INSERT INTO company_fundamentals_history (
        security_id, symbol, as_of_date, eps, nav_per_share, pe_ratio,
        paid_up_capital, authorized_capital, market_lot, face_value, listing_year,
        shareholding_sponsor, shareholding_govt, shareholding_institute,
        shareholding_foreign, shareholding_public
    )
    SELECT 
        s.security_id,
        cp.symbol,
        COALESCE(cp.updated_at::date, DATE '2026-11-08') AS as_of_date,
        cp.eps,
        cp.nav_per_share,
        cp.pe_ratio,
        cp.paid_up_capital,
        cp.authorized_capital,
        cp.market_lot,
        cp.face_value,
        cp.listing_year,
        cp.shareholding_sponsor,
        cp.shareholding_govt,
        cp.shareholding_institute,
        cp.shareholding_foreign,
        cp.shareholding_public
    FROM company_profiles cp
    LEFT JOIN securities s ON s.current_symbol = cp.symbol
    ON CONFLICT (symbol, as_of_date) DO NOTHING;
    """,

    # 3. going_concern_history table
    """
    CREATE TABLE IF NOT EXISTS going_concern_history (
        history_id BIGSERIAL PRIMARY KEY,
        security_id INT REFERENCES securities(security_id) ON DELETE RESTRICT,
        symbol VARCHAR(30) NOT NULL,
        company_name TEXT,
        threat_status VARCHAR(20) NOT NULL DEFAULT 'Yes',
        effective_date DATE NOT NULL,
        resolved_date DATE,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_gc_sym_date UNIQUE (symbol, effective_date)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_gc_lookup ON going_concern_history(security_id, is_active);",

    # 4. Seed going_concern_history from going_concern_threats
    """
    INSERT INTO going_concern_history (
        security_id, symbol, company_name, threat_status, effective_date, is_active
    )
    SELECT 
        s.security_id,
        g.symbol,
        g.company_name,
        g.threat_status,
        COALESCE(g.as_of_date, DATE '2026-11-09') AS effective_date,
        TRUE AS is_active
    FROM going_concern_threats g
    LEFT JOIN securities s ON s.current_symbol = g.symbol
    ON CONFLICT (symbol, effective_date) DO NOTHING;
    """,

    # 5. news_announcements columns
    """
    ALTER TABLE news_announcements
        ADD COLUMN IF NOT EXISTS security_id INT REFERENCES securities(security_id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
    """,
    "CREATE INDEX IF NOT EXISTS idx_news_published_at ON news_announcements(published_at);",
    "CREATE INDEX IF NOT EXISTS idx_news_security_id ON news_announcements(security_id);",

    # 6. Link security_id on news_announcements
    """
    UPDATE news_announcements n
    SET security_id = s.security_id
    FROM securities s
    WHERE n.symbol = s.current_symbol AND n.security_id IS NULL;
    """,

    # 7. Parse and populate published_at timestamp
    """
    UPDATE news_announcements
    SET published_at = (to_date(published_date, 'DD Mon YYYY') + COALESCE(NULLIF(published_time, '')::time, '00:00'::time)) AT TIME ZONE 'Asia/Dhaka'
    WHERE published_at IS NULL 
      AND published_date IS NOT NULL 
      AND published_date ~ '^\\d{2}\\s+[A-Za-z]{3}\\s+\\d{4}$';
    """
]


def run_migration():
    config = DSEConfig()
    mgr = DatabaseManager(config.postgres_url)
    logger.info("Executing Phase 4 schema migration & backfill against %s...", config.postgres_url.split("@")[-1])

    with mgr.engine.begin() as conn:
        for stmt in MIGRATION_STATEMENTS:
            cleaned = stmt.strip()
            if cleaned:
                conn.execute(text(cleaned))

    with mgr.engine.connect() as conn:
        fund_cnt = conn.execute(text("SELECT count(*) FROM company_fundamentals_history")).scalar()
        gc_cnt = conn.execute(text("SELECT count(*) FROM going_concern_history")).scalar()
        news_ts = conn.execute(text("SELECT count(*) FROM news_announcements WHERE published_at IS NOT NULL")).scalar()
        news_sec = conn.execute(text("SELECT count(*) FROM news_announcements WHERE security_id IS NOT NULL")).scalar()
        logger.info(
            "Phase 4 complete! Fundamentals history: %d | Going concern history: %d | News with parsed timestamps: %d | News linked to securities: %d",
            fund_cnt, gc_cnt, news_ts, news_sec
        )


if __name__ == "__main__":
    run_migration()


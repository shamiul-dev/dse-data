"""
Migration script for Phase 2: Master Security Registry & SCD Type 2 History.
1. Creates securities table (surrogate security_id, current_symbol, isin, company_name).
2. Creates security_attributes_history table with [valid_from, valid_to) SCD Type 2 intervals.
3. Seeds securities from the existing 687 instruments.
4. Seeds initial SCD Type 2 attribute records with valid_from = '2024-11-01', valid_to = NULL, is_current = TRUE.
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
    # 1. Master securities table
    """
    CREATE TABLE IF NOT EXISTS securities (
        security_id SERIAL PRIMARY KEY,
        current_symbol VARCHAR(30) NOT NULL UNIQUE,
        isin VARCHAR(12) UNIQUE,
        company_name VARCHAR(255),
        first_listed_date DATE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_securities_symbol ON securities(current_symbol);",

    # 2. SCD Type 2 security_attributes_history table
    """
    CREATE TABLE IF NOT EXISTS security_attributes_history (
        history_id BIGSERIAL PRIMARY KEY,
        security_id INT NOT NULL REFERENCES securities(security_id) ON DELETE RESTRICT,
        symbol VARCHAR(30) NOT NULL,
        category VARCHAR(10),
        board VARCHAR(50) DEFAULT 'PUBLIC',
        sector VARCHAR(100),
        is_marginable BOOLEAN DEFAULT FALSE,
        operation_status VARCHAR(50) DEFAULT 'Active',
        valid_from DATE NOT NULL,
        valid_to DATE,
        is_current BOOLEAN DEFAULT TRUE,
        change_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_sec_attr_lookup ON security_attributes_history(security_id, valid_from, valid_to);",
    "CREATE INDEX IF NOT EXISTS idx_sec_attr_current ON security_attributes_history(security_id, is_current);",

    # 3. Add optional security_id foreign key to daily_eod and quotes
    """
    ALTER TABLE daily_eod
        ADD COLUMN IF NOT EXISTS security_id INT REFERENCES securities(security_id) ON DELETE SET NULL;
    """,
    """
    ALTER TABLE quotes
        ADD COLUMN IF NOT EXISTS security_id INT REFERENCES securities(security_id) ON DELETE SET NULL;
    """,

    # 4. Seed securities from instruments (upsert by current_symbol)
    """
    INSERT INTO securities (current_symbol, company_name)
    SELECT symbol, company_name FROM instruments
    ON CONFLICT (current_symbol) DO UPDATE
    SET company_name = EXCLUDED.company_name;
    """,

    # 5. Populate initial SCD Type 2 baseline if table is empty
    """
    INSERT INTO security_attributes_history (
        security_id, symbol, category, board, sector, is_marginable, operation_status, valid_from, valid_to, is_current, change_reason
    )
    SELECT 
        s.security_id,
        i.symbol,
        i.category,
        i.board,
        i.sector,
        i.is_marginable,
        i.operation_status,
        DATE '2024-11-01' AS valid_from,
        NULL AS valid_to,
        TRUE AS is_current,
        'Initial baseline seeding from instruments master' AS change_reason
    FROM instruments i
    JOIN securities s ON s.current_symbol = i.symbol
    WHERE NOT EXISTS (
        SELECT 1 FROM security_attributes_history sah WHERE sah.security_id = s.security_id
    );
    """,

    # 6. Populate security_id foreign key on daily_eod where null
    """
    UPDATE daily_eod d
    SET security_id = s.security_id
    FROM securities s
    WHERE d.symbol = s.current_symbol AND d.security_id IS NULL;
    """,

    # 7. Populate security_id foreign key on quotes where null
    """
    UPDATE quotes q
    SET security_id = s.security_id
    FROM securities s
    WHERE q.symbol = s.current_symbol AND q.security_id IS NULL;
    """
]


def run_migration():
    config = DSEConfig()
    mgr = DatabaseManager(config.postgres_url)
    logger.info("Executing Phase 2 schema migration & seeding against %s...", config.postgres_url.split("@")[-1])

    with mgr.engine.begin() as conn:
        for stmt in MIGRATION_STATEMENTS:
            cleaned = stmt.strip()
            if cleaned:
                conn.execute(text(cleaned))

    with mgr.engine.connect() as conn:
        sec_cnt = conn.execute(text("SELECT count(*) FROM securities")).scalar()
        sah_cnt = conn.execute(text("SELECT count(*) FROM security_attributes_history")).scalar()
        eod_linked = conn.execute(text("SELECT count(*) FROM daily_eod WHERE security_id IS NOT NULL")).scalar()
        logger.info("Phase 2 complete! Securities seeded: %d | SCD2 records: %d | daily_eod linked: %d", sec_cnt, sah_cnt, eod_linked)


if __name__ == "__main__":
    run_migration()


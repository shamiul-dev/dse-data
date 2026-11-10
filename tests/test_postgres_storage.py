from pathlib import Path
import pytest
from dse_scraper.config import DSEConfig
from dse_scraper.parsers.snapshot_parser import parse_live_snapshot
from dse_scraper.storage.alchemy.postgres_storage import PostgresAlchemyStorage


@pytest.fixture
def sample_snapshot():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return parse_live_snapshot(f.read())


def test_postgres_alchemy_storage(sample_snapshot):
    config = DSEConfig()
    try:
        storage = PostgresAlchemyStorage(config.postgres_url)
    except Exception as e:
        pytest.skip(f"PostgreSQL not accessible: {e}")

    # 1. Save live snapshot
    storage.save_snapshot(sample_snapshot)

    # 2. Query instruments and quotes
    instruments = storage.get_instruments()
    assert len(instruments) > 300

    quotes = storage.get_latest_quotes()
    assert len(quotes) > 300
    sym_map = {q.symbol: q for q in quotes}
    assert "1JANATAMF" in sym_map

    # 3. Test Phase 1 Provenance & Idempotency
    janata = sym_map["1JANATAMF"]
    assert janata.exchange_trade_time is not None
    assert janata.session_date is not None
    assert janata.feed_date is not None
    assert janata.fetch_id is not None

    count_before = len(storage.get_latest_quotes())
    # Save same snapshot again -> must NOT duplicate rows due to ON CONFLICT DO NOTHING
    storage.save_snapshot(sample_snapshot)
    count_after = len(storage.get_latest_quotes())
    assert count_before == count_after


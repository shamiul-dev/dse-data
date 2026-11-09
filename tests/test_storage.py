from datetime import date
from pathlib import Path
import tempfile
import pytest

from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.models.history import DailyEOD
from dse_scraper.models.instrument import Instrument
from dse_scraper.parsers.snapshot_parser import parse_live_snapshot
from dse_scraper.storage.memory_storage import MemoryStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def sample_snapshot():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return parse_live_snapshot(f.read())


def test_memory_storage(sample_snapshot):
    storage = MemoryStorage()
    storage.save_snapshot(sample_snapshot)

    quotes = storage.get_latest_quotes()
    assert len(quotes) > 300

    instruments = storage.get_instruments()
    assert len(instruments) > 300

    # Test daily eod
    eod = DailyEOD(symbol="GP", date=date(2026, 11, 9), close=280.5)
    storage.save_daily_eod([eod])
    assert ("GP", "2026-11-09") in storage.daily_eod


def test_sqlite_storage_roundtrip(sample_snapshot):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_dse.db"
        storage = SQLiteStorage(str(db_path))

        # 1. Save Snapshot
        storage.save_snapshot(sample_snapshot)

        # Verify latest quotes
        quotes = storage.get_latest_quotes()
        assert len(quotes) > 300
        sym_map = {q.symbol: q for q in quotes}
        assert "1JANATAMF" in sym_map

        # Verify instruments registered
        instruments = storage.get_instruments()
        assert len(instruments) > 300

        # 2. Test Idempotency: Save identical snapshot again (should not duplicate or fail)
        storage.save_snapshot(sample_snapshot)
        quotes_after = storage.get_latest_quotes()
        assert len(quotes_after) == len(quotes)

        # 3. Test Historical EOD Upsert
        eod1 = DailyEOD(symbol="GP", date=date(2026, 11, 9), open=280.0, close=285.0, volume=50000)
        eod2 = DailyEOD(symbol="BATBC", date=date(2026, 11, 9), open=400.0, close=405.0, volume=30000)
        storage.save_daily_eod([eod1, eod2])

        # Overwrite eod1 with updated close
        eod1_updated = DailyEOD(symbol="GP", date=date(2026, 11, 9), open=280.0, close=286.5, volume=52000)
        storage.save_daily_eod([eod1_updated])

        # 4. Test Company Profile Upsert
        profile = CompanyProfile(
            symbol="GP",
            name="Grameenphone Ltd.",
            sector="Telecommunication",
            pe_ratio=10.5,
            eps=24.5,
            nav_per_share=45.2,
            shareholding_sponsor=90.0,
            shareholding_public=7.5,
            as_of_date=date(2026, 6, 30),
        )
        storage.save_company_profile(profile)
        # Update profile again
        profile.pe_ratio = 10.8
        storage.save_company_profile(profile)


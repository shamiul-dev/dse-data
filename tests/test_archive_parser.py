"""
Unit tests for Day-End Archive parser.
Verifies Phase 1 ingestion hardening:
- LTP vs Close separation
- Untraded bar normalization (NULL prices, 0 volume, session_status='no_trade')
"""

import json
from dse_scraper.parsers.archive_parser import parse_day_end_response


def test_archive_parser_traded_record():
    payload = {
        "total": 1,
        "page": 1,
        "pageSize": 500,
        "rows": [
            {
                "serial": 1,
                "date": "2026-11-09",
                "tradingCode": "GP",
                "ltp": 223.2,
                "high": 225.3,
                "low": 223.0,
                "openp": 225.0,
                "closep": 223.2,
                "ycp": 224.8,
                "trade": 2317,
                "value": 29.843,
                "volume": 133386,
            }
        ]
    }
    records, total, pages = parse_day_end_response(payload)
    assert total == 1
    assert pages == 1
    assert len(records) == 1

    rec = records[0]
    assert rec.symbol == "GP"
    assert rec.ltp == 223.2
    assert rec.close == 223.2
    assert rec.open == 225.0
    assert rec.volume == 133386
    assert rec.session_status == "traded"
    assert rec.price_type == "trade"


def test_archive_parser_untraded_record():
    payload = {
        "total": 1,
        "page": 1,
        "pageSize": 500,
        "rows": [
            {
                "serial": 2,
                "date": "2026-11-09",
                "tradingCode": "ABBLPBOND",
                "ltp": 0.0,
                "high": 0.0,
                "low": 0.0,
                "openp": 0.0,
                "closep": 980.0,
                "ycp": 980.0,
                "trade": 0,
                "value": 0.0,
                "volume": 0,
            }
        ]
    }
    records, total, pages = parse_day_end_response(payload)
    assert len(records) == 1

    rec = records[0]
    assert rec.symbol == "ABBLPBOND"
    # Untraded bars must store NULL for active trade prices
    assert rec.ltp is None
    assert rec.open is None
    assert rec.high is None
    assert rec.low is None
    # Close is preserved as reference price
    assert rec.close == 980.0
    assert rec.volume == 0
    assert rec.trades == 0
    assert rec.session_status == "no_trade"
    assert rec.price_type == "reference"


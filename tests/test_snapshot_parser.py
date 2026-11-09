import json
from pathlib import Path
from dse_scraper.parsers.snapshot_parser import parse_live_snapshot


def test_parse_live_snapshot_with_fixture():
    fixture_path = Path(__file__).parent / "fixtures" / "sample_snapshot.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        payload = f.read()

    snapshot = parse_live_snapshot(payload)

    # Assert indices parsed
    assert len(snapshot.indices) >= 3
    index_keys = {idx.key for idx in snapshot.indices}
    assert "DSEX" in index_keys
    assert "DS30" in index_keys
    assert "DSES" in index_keys

    dsex = next(i for i in snapshot.indices if i.key == "DSEX")
    assert dsex.value > 1000

    # Assert totals
    assert snapshot.totals is not None
    assert snapshot.totals.market_cap is not None

    # Assert quotes parsed
    assert len(snapshot.quotes) > 300
    symbols = {q.symbol for q in snapshot.quotes}
    assert "1JANATAMF" in symbols

    first = snapshot.quotes[0]
    assert first.symbol != ""
    assert first.ycp is not None


def test_parse_live_snapshot_malformed_inputs():
    # Corrupt string
    res = parse_live_snapshot("not json")
    assert len(snapshot_res := res.quotes) == 0
    assert len(res.indices) == 0

    # Empty dictionary
    res = parse_live_snapshot({})
    assert len(res.quotes) == 0

    # Missing rows
    res = parse_live_snapshot({"prices": {"cols": ["code", "ltp"], "rows": [["TEST", "10.5"], [None, "5.0"]]}})
    assert len(res.quotes) == 1
    assert res.quotes[0].symbol == "TEST"
    assert res.quotes[0].ltp == 10.5


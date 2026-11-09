from datetime import date
from dse_scraper.core.normalizers import safe_date, safe_float, safe_int, safe_str


def test_safe_float_clean_numbers():
    assert safe_float(12.34) == 12.34
    assert safe_float("12.34") == 12.34
    assert safe_float(0) == 0.0
    assert safe_float("0.0") == 0.0


def test_safe_float_edge_cases():
    # Commas & currency symbols
    assert safe_float("1,234.50") == 1234.50
    assert safe_float("৳ 450.25") == 450.25
    assert safe_float("450.25 Tk") == 450.25
    assert safe_float("5.75%") == 5.75

    # Missing & placeholder values
    assert safe_float(None) is None
    assert safe_float("-") is None
    assert safe_float("--") is None
    assert safe_float("N/A") is None
    assert safe_float("", default=0.0) == 0.0
    assert safe_float("corrupt_value", default=-1.0) == -1.0


def test_safe_int():
    assert safe_int(100) == 100
    assert safe_int("100") == 100
    assert safe_int("100.0") == 100
    assert safe_int("1,000") == 1000
    assert safe_int(None) is None
    assert safe_int("-") is None
    assert safe_int("invalid", default=0) == 0


def test_safe_str():
    assert safe_str("  GP  ") == "GP"
    assert safe_str(None) == ""
    assert safe_str(None, default="UNKNOWN") == "UNKNOWN"
    assert safe_str(123) == "123"


def test_safe_date():
    expected = date(2026, 11, 9)
    assert safe_date("2026-11-09") == expected
    assert safe_date("09-11-2026") == expected
    assert safe_date("09-Nov-2026") == expected
    assert safe_date("Nov 09, 2026") == expected
    assert safe_date("09/11/2026") == expected
    assert safe_date(None) is None
    assert safe_date("-") is None
    assert safe_date("not-a-date") is None


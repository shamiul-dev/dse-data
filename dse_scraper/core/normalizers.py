"""
Robust type-casting and normalization utilities.
These functions NEVER raise unhandled conversion exceptions, ensuring that
corrupt, malformed, or missing DSE fields never crash a scraping run.
"""

from datetime import date, datetime
import re
from typing import Any, Optional


def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert an input to float.
    Handles None, empty strings, commas, currency symbols, hyphens, and 'N/A'.
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)

    # Clean string representation
    s = str(val).strip()
    if not s or s in ("-", "--", "---", "N/A", "n/a", "null", "None", "Loading..."):
        return default

    # Remove currency symbols, commas, quotes
    s = s.replace(",", "").replace("৳", "").replace("Tk", "").replace("tk", "").strip()

    # Handle percentage strings like "5.25%"
    if s.endswith("%"):
        s = s[:-1].strip()

    try:
        return float(s)
    except (ValueError, TypeError):
        # Attempt regex extraction if there are embedded numbers (e.g. "12.5 mn")
        match = re.search(r"[-+]?\d*\.?\d+", s)
        if match:
            try:
                return float(match.group(0))
            except (ValueError, TypeError):
                return default
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely convert an input to integer.
    Handles floats, strings with decimals ("100.0"), commas, hyphens, and None.
    """
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)

    s = str(val).strip()
    if not s or s in ("-", "--", "---", "N/A", "n/a", "null", "None"):
        return default

    s = s.replace(",", "").replace("৳", "").replace("Tk", "").replace("tk", "").strip()
    try:
        # If string contains a decimal like "100.0", convert via float first
        return int(float(s))
    except (ValueError, TypeError):
        return default


def safe_str(val: Any, default: str = "") -> str:
    """
    Safely normalize string fields: strips whitespace, converts None to default.
    """
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def safe_date(val: Any, default: Optional[date] = None) -> Optional[date]:
    """
    Safely parses various DSE date formats:
    - '2026-11-09' (ISO)
    - '09-11-2026' (DD-MM-YYYY)
    - 'Nov 09, 2026'
    - '09 Nov, 2026'
    - '09-Nov-2026'
    """
    if val is None:
        return default
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()

    s = str(val).strip()
    if not s or s in ("-", "--", "N/A", "null", "None"):
        return default

    known_formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d-%m-%y",
    ]

    for fmt in known_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue

    # Attempt regex pattern match YYYY-MM-DD
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    return default


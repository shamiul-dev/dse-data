"""
Pure parser for DSE historical Day-End archive data.
Deterministic, handles pagination and per-row safety.
"""

import json
from typing import Any, Dict, List, Tuple, Union

from dse_scraper.core.normalizers import safe_date, safe_float, safe_int, safe_str
from dse_scraper.models.history import DailyEOD


def parse_day_end_response(payload: Union[str, bytes, Dict[str, Any]]) -> Tuple[List[DailyEOD], int, int]:
    """
    Parses DSE /api/live/data-archive/day-end JSON response.
    Returns:
        (records: List[DailyEOD], total_records: int, total_pages: int)
    """
    if isinstance(payload, (str, bytes)):
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return [], 0, 0
    elif isinstance(data := payload, dict):
        pass
    else:
        return [], 0, 0

    rows = data.get("rows") or []
    total = safe_int(data.get("total"), 0) or 0
    page_size = safe_int(data.get("pageSize"), 500) or 500
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

    records: List[DailyEOD] = []
    for r in rows:
        if not isinstance(r, dict):
            continue

        symbol = safe_str(r.get("tradingCode") or r.get("code") or r.get("symbol"))
        record_date = safe_date(r.get("date"))

        if not symbol or not record_date:
            continue

        records.append(
            DailyEOD(
                symbol=symbol,
                date=record_date,
                open=safe_float(r.get("openp") or r.get("open")),
                high=safe_float(r.get("high")),
                low=safe_float(r.get("low")),
                close=safe_float(r.get("closep") or r.get("close")),
                ycp=safe_float(r.get("ycp")),
                volume=safe_int(r.get("volume"), 0),
                value_mn=safe_float(r.get("value"), 0.0),
                trades=safe_int(r.get("trade") or r.get("trades"), 0),
            )
        )

    return records, total, total_pages


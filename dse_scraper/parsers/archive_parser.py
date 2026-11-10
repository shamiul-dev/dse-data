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

        raw_vol = safe_int(r.get("volume"), 0) or 0
        raw_trades = safe_int(r.get("trade") or r.get("trades"), 0) or 0
        raw_val = safe_float(r.get("value"), 0.0) or 0.0
        raw_ltp = safe_float(r.get("ltp"))
        raw_open = safe_float(r.get("openp") or r.get("open"))
        raw_high = safe_float(r.get("high"))
        raw_low = safe_float(r.get("low"))
        raw_close = safe_float(r.get("closep") or r.get("close"))
        raw_ycp = safe_float(r.get("ycp"))

        is_untraded = (raw_vol == 0 and raw_trades == 0) or (raw_ltp == 0 and raw_open == 0)

        if is_untraded:
            open_val = None
            high_val = None
            low_val = None
            ltp_val = None
            close_val = raw_close if raw_close and raw_close > 0 else raw_ycp
            session_status = "no_trade"
            price_type = "reference"
        else:
            open_val = raw_open
            high_val = raw_high
            low_val = raw_low
            ltp_val = raw_ltp
            close_val = raw_close
            session_status = "traded"
            price_type = "trade"

        records.append(
            DailyEOD(
                symbol=symbol,
                date=record_date,
                open=open_val,
                high=high_val,
                low=low_val,
                close=close_val,
                ltp=ltp_val,
                ycp=raw_ycp,
                volume=raw_vol,
                value_mn=raw_val,
                trades=raw_trades,
                price_type=price_type,
                session_status=session_status,
            )
        )

    return records, total, total_pages


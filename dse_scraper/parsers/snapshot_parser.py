"""
Pure parser for DSE modern /api/live/snapshot response.
Deterministic, isolated from network and database operations.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Union

from dse_scraper.core.normalizers import safe_float, safe_int, safe_str
from dse_scraper.models.quote import IndexQuote, InstrumentQuote
from dse_scraper.models.snapshot import LiveSnapshot, MarketTotals


def parse_live_snapshot(payload: Union[str, bytes, Dict[str, Any]]) -> LiveSnapshot:
    """
    Parses DSE /api/live/snapshot JSON into a typed LiveSnapshot model.
    Guarantees no crash on malformed rows or missing columns.
    """
    now = datetime.now(timezone.utc)
    if isinstance(payload, (str, bytes)):
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return LiveSnapshot(timestamp=now, indices=[], totals=None, quotes=[])
    elif isinstance(data := payload, dict):
        pass
    else:
        return LiveSnapshot(timestamp=now, indices=[], totals=None, quotes=[])

    # 1. Parse Market Indices
    indices: List[IndexQuote] = []
    market_data = data.get("market") or {}
    for idx_item in market_data.get("indices") or []:
        key = safe_str(idx_item.get("key"))
        value = safe_float(idx_item.get("value"))
        if key and value is not None:
            indices.append(
                IndexQuote(
                    key=key,
                    value=value,
                    change=safe_float(idx_item.get("change"), 0.0) or 0.0,
                    percent=safe_float(idx_item.get("percent"), 0.0) or 0.0,
                    prev=safe_float(idx_item.get("prev")),
                )
            )

    # 2. Parse Market Totals
    totals_data = market_data.get("totals") or {}
    totals = MarketTotals(
        trades=safe_int(totals_data.get("trades"), 0),
        volume=safe_int(totals_data.get("volume"), 0),
        turnover_mn=safe_float(totals_data.get("turnover"), 0.0),
        market_cap=safe_float(totals_data.get("marketCap")),
    )

    # 3. Parse Instrument Quotes
    quotes: List[InstrumentQuote] = []
    prices_data = data.get("prices") or {}
    cols: List[str] = prices_data.get("cols") or []
    rows: List[List[Any]] = prices_data.get("rows") or []

    # Map column names to indices
    col_map = {col.lower(): i for i, col in enumerate(cols)}

    for row in rows:
        if not isinstance(row, list):
            continue

        def get_val(col_name: str) -> Any:
            idx = col_map.get(col_name.lower())
            if idx is not None and 0 <= idx < len(row):
                return row[idx]
            return None

        symbol = safe_str(get_val("code"))
        if not symbol:
            continue

        ltp = safe_float(get_val("ltp"))
        ycp = safe_float(get_val("ycp"))

        # Calculate change and percent only when active trading occurred (ltp > 0)
        raw_change = get_val("change")
        change = safe_float(raw_change)
        percent = safe_float(get_val("percent"))

        if ltp and ltp > 0 and ycp is not None and ycp > 0:
            if change is None:
                change = round(ltp - ycp, 2)
            if percent is None:
                percent = round((change / ycp) * 100, 2)
        elif not ltp or ltp == 0:
            change = None
            percent = None

        quotes.append(
            InstrumentQuote(
                symbol=symbol,
                ltp=ltp,
                ycp=ycp,
                open=safe_float(get_val("open")),
                high=safe_float(get_val("high")),
                low=safe_float(get_val("low")),
                close=safe_float(get_val("close")),
                volume=safe_int(get_val("volume"), 0),
                value_mn=safe_float(get_val("value"), 0.0),
                trades=safe_int(get_val("trades"), 0),
                change=change,
                percent=percent,
                category=safe_str(get_val("category")) or None,
                board=safe_str(get_val("board")) or None,
                sector=safe_str(get_val("sector")) or None,
                asset_type=safe_str(get_val("assetType")) or None,
            )
        )

    return LiveSnapshot(
        timestamp=now,
        indices=indices,
        totals=totals,
        quotes=quotes,
    )

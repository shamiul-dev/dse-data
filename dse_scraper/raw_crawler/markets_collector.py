"""
Raw collector for Markets domain.
Extracts live prices, indices, circuit breakers, P/E ratios, and market summaries.
"""

from datetime import date, timedelta
import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from lxml import html

from dse_scraper.core.client import ResilientClient
from dse_scraper.core.normalizers import safe_float, safe_int, safe_str

logger = logging.getLogger(__name__)


class MarketsCollector:
    def __init__(self, client: ResilientClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir / "markets"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> Dict[str, int]:
        results = {}
        results["latest_share_price"] = self.collect_live_snapshot()
        results["circuit_breakers"] = self.collect_circuit_breakers()
        results["pe_at_a_glance"] = self.collect_pe_ratios()
        results["market_summary_history"] = self.collect_market_summary()
        return results

    def collect_live_snapshot(self) -> int:
        """Fetches /api/live/snapshot and saves prices and indices separately."""
        url = f"{self.client.config.modern_base_url}/api/live/snapshot"
        res = self.client.get(url, headers={"Accept": "application/json"})
        if not res.is_success:
            logger.error("Failed to fetch live snapshot (%d)", res.status)
            return 0

        data = json.loads(res.body.decode("utf-8", errors="ignore"))
        
        # Save complete raw snapshot
        (self.output_dir / "live_snapshot_raw.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

        # Also extract structured latest quotes
        prices = data.get("prices") or {}
        cols = prices.get("cols") or []
        rows = prices.get("rows") or []
        structured_quotes = [dict(zip(cols, r)) for r in rows if isinstance(r, list)]

        (self.output_dir / "latest_share_price.json").write_text(
            json.dumps(structured_quotes, indent=2), encoding="utf-8"
        )

        # Indices
        market = data.get("market") or {}
        (self.output_dir / "market_indices.json").write_text(
            json.dumps(market, indent=2), encoding="utf-8"
        )

        logger.info("Saved latest share prices (%d items) and market indices.", len(structured_quotes))
        return len(structured_quotes)

    def collect_circuit_breakers(self) -> int:
        """Scrapes /circuit-breaker table."""
        url = f"{self.client.config.modern_base_url}/circuit-breaker"
        res = self.client.get(url)
        if not res.is_success:
            logger.error("Failed to fetch circuit-breaker (%d)", res.status)
            return 0

        doc = html.fromstring(res.body)
        tables = doc.xpath("//table")
        items = []

        if tables:
            rows = tables[0].xpath(".//tr")
            for r in rows[1:]:
                tds = r.xpath("./td")
                if not tds:
                    continue
                cells = [td.text_content().strip() for td in tds]
                # Pattern: ['1', '1JANATAMF', 'First Janata Bank Mutual Fund', '3.20', '10.00%', '0.1', '3.20', '2.90', '3.50']
                if len(cells) >= 8:
                    items.append({
                        "serial": safe_int(cells[0]),
                        "symbol": safe_str(cells[1]),
                        "company_name": safe_str(cells[2]),
                        "close_price": safe_float(cells[3]),
                        "breaker_pct": safe_float(cells[4]),
                        "tick_size": safe_float(cells[5]),
                        "open_adj_price": safe_float(cells[6]),
                        "lower_limit": safe_float(cells[7]) if len(cells) > 7 else None,
                        "upper_limit": safe_float(cells[8]) if len(cells) > 8 else None,
                    })

        (self.output_dir / "circuit_breakers.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved circuit breakers (%d items).", len(items))
        return len(items)

    def collect_pe_ratios(self) -> int:
        """Scrapes /pe table."""
        url = f"{self.client.config.modern_base_url}/pe"
        res = self.client.get(url)
        if not res.is_success:
            logger.error("Failed to fetch P/E ratios (%d)", res.status)
            return 0

        doc = html.fromstring(res.body)
        tables = doc.xpath("//table")
        items = []

        for t in tables:
            rows = t.xpath(".//tr")
            if len(rows) > 1:
                headers = [
                    th.text_content().strip().lower().replace(" ", "_").replace(".", "").replace("/", "_")
                    for th in rows[0].xpath("./th | ./td")
                ]
                headers = [h for h in headers if h]
                for r in rows[1:]:
                    tds = r.xpath("./td")
                    if not tds:
                        continue
                    cells = [td.text_content().strip() for td in tds]
                    if len(cells) >= 2 and any(cells):
                        items.append(dict(zip(headers[:len(cells)], cells)))

        (self.output_dir / "pe_at_a_glance.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved P/E at a glance (%d items).", len(items))
        return len(items)

    def collect_market_summary(self) -> int:
        """Fetches /api/live/data-archive/market-summary for the past 60 days."""
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=60)).isoformat()
        url = f"{self.client.config.modern_base_url}/api/live/data-archive/market-summary?from={from_date}&to={to_date}"
        
        res = self.client.get(url, headers={"Accept": "application/json"})
        if not res.is_success:
            logger.error("Failed to fetch market summary history (%d)", res.status)
            return 0

        data = json.loads(res.body.decode("utf-8", errors="ignore"))
        rows = data.get("rows") or []

        (self.output_dir / "market_summary_history.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8"
        )
        logger.info("Saved market summary history (%d sessions).", len(rows))
        return len(rows)


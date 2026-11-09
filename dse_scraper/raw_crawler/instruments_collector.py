"""
Raw collector for Instruments & Listings domain.
Extracts all instruments, IPOs, OTC listings, bonds, and government securities.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from lxml import html

from dse_scraper.core.client import ResilientClient

logger = logging.getLogger(__name__)


class InstrumentsCollector:
    def __init__(self, client: ResilientClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir / "instruments"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> Dict[str, int]:
        results = {}
        results["all_instruments"] = self.collect_all_instruments()
        results["ipo_centre"] = self.collect_ipo_centre()
        results["otc_market"] = self.collect_otc_market()
        return results

    def collect_all_instruments(self) -> int:
        """Fetches /api/live/data-archive/instruments."""
        url = f"{self.client.config.modern_base_url}/api/live/data-archive/instruments"
        res = self.client.get(url, headers={"Accept": "application/json"})
        if not res.is_success:
            logger.error("Failed to fetch instruments list (%d)", res.status)
            return 0

        data = json.loads(res.body.decode("utf-8", errors="ignore"))
        instruments = data.get("instruments") or []

        (self.output_dir / "all_instruments.json").write_text(
            json.dumps(instruments, indent=2), encoding="utf-8"
        )
        logger.info("Saved master instruments list (%d symbols).", len(instruments))
        return len(instruments)

    def collect_ipo_centre(self) -> int:
        """Scrapes /ipo."""
        url = f"{self.client.config.modern_base_url}/ipo"
        res = self.client.get(url)
        items = []

        if res.is_success:
            doc = html.fromstring(res.body)
            tables = doc.xpath("//table")
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

        (self.output_dir / "ipo_centre.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved IPO centre data (%d items).", len(items))
        return len(items)

    def collect_otc_market(self) -> int:
        """Scrapes /otc."""
        url = f"{self.client.config.modern_base_url}/otc"
        res = self.client.get(url)
        items = []

        if res.is_success:
            doc = html.fromstring(res.body)
            tables = doc.xpath("//table")
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

        (self.output_dir / "otc_market.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved OTC market data (%d items).", len(items))
        return len(items)


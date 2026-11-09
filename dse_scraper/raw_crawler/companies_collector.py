"""
Raw collector for Companies & Filings domain.
Extracts corporate actions, marginable securities, auditor opinions, PSI,
financial statement submission status, going concern list, and closed companies.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from lxml import html

from dse_scraper.core.client import ResilientClient

logger = logging.getLogger(__name__)


class CompaniesCollector:
    def __init__(self, client: ResilientClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir / "companies"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> Dict[str, int]:
        results = {}
        results["marginable_securities"] = self.collect_marginable()
        results["financial_statement_status"] = self.collect_financial_statement_status()
        results["going_concern_list"] = self.collect_going_concern()
        results["closed_companies"] = self.collect_closed_companies()
        results["corporate_actions"] = self.collect_corporate_actions()
        return results

    def _scrape_table(self, url: str) -> List[Dict[str, Any]]:
        res = self.client.get(url)
        if not res.is_success:
            logger.error("Failed to fetch %s (%d)", url, res.status)
            return []

        doc = html.fromstring(res.body)
        tables = doc.xpath("//table")
        items = []

        if tables:
            rows = tables[0].xpath(".//tr")
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
        return items

    def collect_marginable(self) -> int:
        """Scrapes /marginable-securities."""
        items = self._scrape_table(f"{self.client.config.modern_base_url}/marginable-securities")
        (self.output_dir / "marginable_securities.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved marginable securities (%d items).", len(items))
        return len(items)

    def collect_financial_statement_status(self) -> int:
        """Scrapes /financial-statement-status."""
        items = self._scrape_table(f"{self.client.config.modern_base_url}/financial-statement-status")
        (self.output_dir / "financial_statement_status.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved financial statement filing status (%d items).", len(items))
        return len(items)

    def collect_going_concern(self) -> int:
        """Scrapes /going-concern list."""
        items = self._scrape_table(f"{self.client.config.modern_base_url}/going-concern")
        (self.output_dir / "going_concern_list.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved going concern list (%d items).", len(items))
        return len(items)

    def collect_closed_companies(self) -> int:
        """Scrapes /companies/closed."""
        items = self._scrape_table(f"{self.client.config.modern_base_url}/companies/closed")
        (self.output_dir / "closed_companies.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved closed companies (%d items).", len(items))
        return len(items)

    def collect_corporate_actions(self) -> int:
        """Scrapes /corporate-actions."""
        items = self._scrape_table(f"{self.client.config.modern_base_url}/corporate-actions")
        (self.output_dir / "corporate_actions.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved corporate actions (%d items).", len(items))
        return len(items)

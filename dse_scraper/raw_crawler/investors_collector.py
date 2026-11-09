"""
Raw collector for Investors & About DSE domain.
Extracts the TREC Holders' Directory (licensed brokerage firms, representatives, contact info).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
from lxml import html

from dse_scraper.core.client import ResilientClient
from dse_scraper.core.normalizers import safe_int, safe_str

logger = logging.getLogger(__name__)


class InvestorsCollector:
    def __init__(self, client: ResilientClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir / "investors"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> Dict[str, int]:
        results = {}
        results["trec_holders_directory"] = self.collect_trec_holders()
        return results

    def collect_trec_holders(self) -> int:
        """Scrapes /trec-holders?view=alpha."""
        url = f"{self.client.config.modern_base_url}/trec-holders?view=alpha"
        res = self.client.get(url)
        if not res.is_success:
            logger.error("Failed to fetch TREC holders (%d)", res.status)
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
                # ['1', '3i Securities Limited', 'Modhumita Cinema Building...', '260', 'DSERSZ', 'Ms. Ireen Sultana', 'Managing Director', '+88 02 226637744', '01711140905', '-']
                if len(cells) >= 6 and any(cells):
                    items.append({
                        "sl_no": safe_int(cells[0]),
                        "company_name": safe_str(cells[1]),
                        "address": safe_str(cells[2]),
                        "trec_no": safe_str(cells[3]),
                        "trec_code": safe_str(cells[4]),
                        "representative_name": safe_str(cells[5]),
                        "designation": safe_str(cells[6]) if len(cells) > 6 and cells[6] not in ("", "-") else None,
                        "office_phone": safe_str(cells[7]) if len(cells) > 7 and cells[7] not in ("", "-") else None,
                        "mobile": safe_str(cells[8]) if len(cells) > 8 and cells[8] not in ("", "-") else None,
                        "fax": safe_str(cells[9]) if len(cells) > 9 and cells[9] not in ("", "-") else None,
                    })

        (self.output_dir / "trec_holders_directory.json").write_text(
            json.dumps(items, indent=2), encoding="utf-8"
        )
        logger.info("Saved TREC holders directory (%d brokerages).", len(items))
        return len(items)


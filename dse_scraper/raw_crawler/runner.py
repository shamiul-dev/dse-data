"""
Orchestrates raw scraping across all DSE categories with strict rate limits,
followed by automatic cross-referencing and deduplication.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.raw_crawler.companies_collector import CompaniesCollector
from dse_scraper.raw_crawler.cross_referencer import CrossReferencer
from dse_scraper.raw_crawler.instruments_collector import InstrumentsCollector
from dse_scraper.raw_crawler.investors_collector import InvestorsCollector
from dse_scraper.raw_crawler.markets_collector import MarketsCollector
from dse_scraper.raw_crawler.news_collector import NewsCollector

logger = logging.getLogger(__name__)


class RawDataCrawler:
    """Master orchestrator to crawl all DSE pages into separate raw JSONs."""

    def __init__(self, output_dir: str = "raw_data", config: DSEConfig = None):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or DSEConfig()
        self.client = ResilientClient(self.config)

        # Collectors
        self.markets = MarketsCollector(self.client, self.output_dir)
        self.companies = CompaniesCollector(self.client, self.output_dir)
        self.instruments = InstrumentsCollector(self.client, self.output_dir)
        self.news = NewsCollector(self.client, self.output_dir)
        self.investors = InvestorsCollector(self.client, self.output_dir)
        self.cross_ref = CrossReferencer(self.output_dir)

    def crawl_all(self) -> Dict[str, Any]:
        """Runs all collectors sequentially with rate-limiting, then cross-references."""
        summary = {}

        logger.info("=== STEP 1: Crawling Markets ===")
        summary["markets"] = self.markets.collect_all()

        logger.info("=== STEP 2: Crawling Instruments ===")
        summary["instruments"] = self.instruments.collect_all()

        logger.info("=== STEP 3: Crawling Companies & Filings ===")
        summary["companies"] = self.companies.collect_all()

        logger.info("=== STEP 4: Crawling News & Announcements ===")
        summary["news"] = self.news.collect_all()

        logger.info("=== STEP 5: Crawling Investors & Brokers ===")
        summary["investors"] = self.investors.collect_all()

        logger.info("=== STEP 6: Cross-Referencing & Deduplicating ===")
        summary["cross_reference"] = self.cross_ref.run()

        logger.info("All domains crawled and cross-referenced successfully!")
        return summary


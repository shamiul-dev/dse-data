"""
Two-Year Complete Backfill Pipeline for DSE Data Engine.
Executes all 4 historical phases:
Phase 1: Market Summaries (Nov 1, 2024 -> Nov 9, 2026)
Phase 2: Corporate News & PSI Announcements (104 weekly windows)
Phase 3: Historical EOD OHLCV (310,545 records across 622 pages)
Phase 4: Company Fundamentals & Shareholding Structure (687 instruments)
"""

from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.services.company_service import CompanyProfileService
from dse_scraper.services.history_service import HistoricalDataService
from dse_scraper.storage.alchemy.postgres_storage import PostgresAlchemyStorage

logger = logging.getLogger(__name__)

START_DATE = "2024-11-01"
END_DATE = "2026-11-09"


class TwoYearBackfillPipeline:
    def __init__(
        self,
        config: Optional[DSEConfig] = None,
        storage: Optional[PostgresAlchemyStorage] = None,
    ):
        self.config = config or DSEConfig()
        self.client = ResilientClient(self.config)
        self.storage = storage or PostgresAlchemyStorage(self.config.postgres_url)
        self.history_service = HistoricalDataService(
            client=self.client, storage=self.storage, config=self.config
        )
        self.company_service = CompanyProfileService(
            client=self.client, storage=self.storage, config=self.config
        )

    def run_all(self, skip_phases: Optional[List[int]] = None) -> Dict[str, int]:
        skip = skip_phases or []
        results = {}

        print("\n=======================================================")
        print(f"Starting 2-Year DSE Backfill ({START_DATE} -> {END_DATE})")
        print("Rate Limit: 1.0 req/sec with randomized jitter & breathers")
        print("=======================================================\n")

        # Phase 1: Market Summaries
        if 1 not in skip:
            results["market_summaries"] = self.run_phase_1_market_summaries()
        else:
            print("Skipping Phase 1.")

        # Phase 2: News & Announcements
        if 2 not in skip:
            results["news_announcements"] = self.run_phase_2_news()
        else:
            print("Skipping Phase 2.")

        # Phase 3: Historical EOD OHLCV
        if 3 not in skip:
            results["daily_eod"] = self.run_phase_3_historical_eod()
        else:
            print("Skipping Phase 3.")

        # Phase 4: Company Fundamentals
        if 4 not in skip:
            results["company_profiles"] = self.run_phase_4_company_fundamentals()
        else:
            print("Skipping Phase 4.")

        print("\n=======================================================")
        print("All 4 Phases Complete!")
        for phase, count in results.items():
            print(f"  {phase:<24}: {count:,} records persisted")
        print("=======================================================\n")
        return results

    def run_phase_1_market_summaries(self) -> int:
        print("\n--- Phase 1: Ingesting 2 Years of Market Summaries & Indices ---")
        url = f"{self.config.modern_base_url}/api/live/data-archive/market-summary?from={START_DATE}&to={END_DATE}"
        res = self.client.get(url, headers={"Accept": "application/json"})
        if not res.is_success:
            print(f"Failed to fetch market summaries: HTTP {res.status}")
            return 0

        data = json.loads(res.body.decode("utf-8", errors="ignore"))
        rows = data.get("rows") or []
        count = self.storage.ingest_market_summaries(rows)
        print(f"Success! Ingested {count:,} daily market index sessions.")
        return count

    def run_phase_2_news(self) -> int:
        print("\n--- Phase 2: Ingesting 2 Years of Corporate Disclosures & PSI ---")
        start = date.fromisoformat(START_DATE)
        end = date.fromisoformat(END_DATE)
        total_days = (end - start).days

        # Divide into 7-day increments to prevent truncation
        curr = start
        total_ingested = 0
        chunk_idx = 0
        total_chunks = (total_days + 6) // 7

        while curr <= end:
            chunk_end = min(curr + timedelta(days=6), end)
            chunk_idx += 1
            w_from = curr.isoformat()
            w_to = chunk_end.isoformat()

            url = f"{self.config.modern_base_url}/api/live/news?from={w_from}&to={w_to}"
            res = self.client.get(url, headers={"Accept": "application/json"})
            if res.is_success:
                try:
                    data = json.loads(res.body.decode("utf-8", errors="ignore"))
                    rows = data.get("rows") or []
                    news_items = []
                    for r in rows:
                        if not isinstance(r, dict):
                            continue
                        news_items.append({
                            "news_id": r.get("id"),
                            "symbol": str(r.get("code") or "").strip().upper() or None,
                            "company_name": r.get("name"),
                            "sector": r.get("sector"),
                            "date": r.get("date"),
                            "time": r.get("time"),
                            "type": r.get("type"),
                            "summary": r.get("summary") or "",
                            "body": r.get("body") or "",
                        })

                    if news_items:
                        ingested = self.storage.ingest_news(news_items)
                        total_ingested += ingested
                        if chunk_idx % 10 == 0 or chunk_idx == total_chunks:
                            print(f"  News progress: week {chunk_idx}/{total_chunks} ({total_ingested:,} articles saved)")
                except Exception as e:
                    logger.warning("Error parsing news chunk %s to %s: %s", w_from, w_to, e)

            # Adaptive breather every 40 chunks
            if chunk_idx % 40 == 0:
                print("  Taking a 3s cooldown breather...")
                time.sleep(3.0)

            curr = chunk_end + timedelta(days=1)

        print(f"Success! Ingested {total_ingested:,} news announcements across 2 years.")
        return total_ingested

    def run_phase_3_historical_eod(self) -> int:
        print("\n--- Phase 3: Ingesting 2 Years of Daily EOD OHLCV (310k+ rows) ---")
        count = self.history_service.backfill(
            from_date=START_DATE,
            to_date=END_DATE,
            symbol=None,
            resume=True,
            batch_breather_interval=50,
            breather_seconds=3.0,
        )
        print(f"Success! Ingested {count:,} historical EOD price records.")
        return count

    def run_phase_4_company_fundamentals(self) -> int:
        print("\n--- Phase 4: Ingesting Fundamentals for All 687 Listed Companies ---")
        count = self.company_service.sync_all(resume=True)
        print(f"Success! Synced fundamentals for {count:,} companies.")
        return count


if __name__ == "__main__":
    pipeline = TwoYearBackfillPipeline()
    pipeline.run_all()


"""
Company fundamentals service.
Crawls and updates company profiles, balance sheet items, and shareholding patterns
with dual-source redundancy (modern and legacy DSE mirrors) and persistent checkpointing.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.models.fundamentals import CompanyProfile
from dse_scraper.parsers.company_parser import parse_company_profile
from dse_scraper.storage.base import BaseStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class CompanyProfileService:
    """Service to fetch and sync company profiles and fundamentals."""

    def __init__(
        self,
        client: Optional[ResilientClient] = None,
        storage: Optional[BaseStorage] = None,
        config: Optional[DSEConfig] = None,
    ):
        self.config = config or DSEConfig()
        self.client = client or ResilientClient(self.config)
        self.storage = storage or SQLiteStorage(self.config.sqlite_db_path)

    def fetch_company(self, symbol: str) -> CompanyProfile:
        """
        Fetches company profile with automatic dual-source fallback:
        Tries legacy portal (old.dsebd.org) which has full tables,
        or modern portal (dse.com.bd).
        """
        sym = symbol.strip().upper()

        # Primary: legacy displayCompany.php has rich historical tables
        legacy_url = f"{self.config.legacy_base_url}/displayCompany.php?name={sym}"
        res = self.client.get(legacy_url, referer=self.config.legacy_base_url)

        if res.is_success and len(res.body) > 2000:
            profile = parse_company_profile(res.body, symbol=sym)
            if profile.authorized_capital or profile.pe_ratio or profile.shareholding_sponsor:
                return profile

        # Secondary fallback: modern portal
        modern_url = f"{self.config.modern_base_url}/company/{sym}"
        res = self.client.get(modern_url, referer=self.config.modern_base_url)
        if res.is_success:
            return parse_company_profile(res.body, symbol=sym)

        logger.warning("Could not fetch complete profile for %s from either source.", sym)
        return CompanyProfile(symbol=sym)

    def sync_company(self, symbol: str) -> CompanyProfile:
        """Fetches and persists a single company profile."""
        profile = self.fetch_company(symbol)
        self.storage.save_company_profile(profile)
        return profile

    def sync_all(self, symbols: Optional[List[str]] = None, resume: bool = True) -> int:
        """
        Syncs fundamentals for all known instruments with progress tracking and checkpointing.
        """
        checkpoint_file = Path(".fundamentals_checkpoint.json")
        synced_symbols = set()

        if resume and checkpoint_file.exists():
            try:
                synced_symbols = set(json.loads(checkpoint_file.read_text(encoding="utf-8")).get("synced", []))
                logger.info("Found checkpoint with %d previously synced instruments.", len(synced_symbols))
            except Exception:
                synced_symbols = set()
        elif not resume and checkpoint_file.exists():
            checkpoint_file.unlink(missing_ok=True)

        if not symbols:
            instruments = self.storage.get_instruments()
            symbols = [inst.symbol for inst in instruments]

        if not symbols:
            logger.warning("No instruments found in storage to sync. Run live sync first.")
            return 0

        pending_symbols = [s for s in symbols if s not in synced_symbols]
        logger.info(
            "Starting fundamentals sync: %d total, %d pending, %d previously completed.",
            len(symbols), len(pending_symbols), len(synced_symbols),
        )

        count = 0
        for i, sym in enumerate(pending_symbols, 1):
            try:
                self.sync_company(sym)
                synced_symbols.add(sym)
                count += 1

                # Save checkpoint periodically
                if count % 10 == 0 or i == len(pending_symbols):
                    checkpoint_file.write_text(
                        json.dumps({"synced": sorted(list(synced_symbols))}, indent=2),
                        encoding="utf-8",
                    )
                    logger.info("Fundamentals progress: %d/%d completed in this session.", i, len(pending_symbols))
            except Exception as e:
                logger.error("Error syncing company %s: %s (continuing with remaining)", sym, e)

        # Remove checkpoint when all symbols are done
        if len(synced_symbols) >= len(symbols):
            checkpoint_file.unlink(missing_ok=True)
            logger.info("Full fundamentals sync completed! Checkpoint cleared.")

        return count

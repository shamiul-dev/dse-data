"""
Live market service.
Coordinates fetching real-time market snapshots from DSE modern API,
parsing them deterministically, and storing them in the configured repository.
"""

import logging
from typing import Optional

from dse_scraper.config import DSEConfig
from dse_scraper.core.client import ResilientClient
from dse_scraper.models.snapshot import LiveSnapshot
from dse_scraper.parsers.snapshot_parser import parse_live_snapshot
from dse_scraper.storage.base import BaseStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class LiveMarketService:
    """Service to capture live market quotes and index benchmarks."""

    def __init__(
        self,
        client: Optional[ResilientClient] = None,
        storage: Optional[BaseStorage] = None,
        config: Optional[DSEConfig] = None,
    ):
        self.config = config or DSEConfig()
        self.client = client or ResilientClient(self.config)
        self.storage = storage or SQLiteStorage(self.config.sqlite_db_path)

    def fetch_snapshot(self) -> LiveSnapshot:
        """
        Fetches the current live market snapshot from /api/live/snapshot
        and returns a strongly-typed LiveSnapshot without persisting it.
        """
        url = f"{self.config.modern_base_url}/api/live/snapshot"
        response = self.client.get(
            url,
            headers={"Accept": "application/json"},
            referer=f"{self.config.modern_base_url}/markets/latest-share-price",
        )

        if not response.is_success:
            logger.error("Failed to fetch live snapshot from %s (status %d)", url, response.status)
            return parse_live_snapshot({})

        return parse_live_snapshot(response.body)

    def sync(self) -> LiveSnapshot:
        """
        Fetches the live snapshot, persists it into the configured storage,
        and returns the snapshot.
        """
        snapshot = self.fetch_snapshot()
        if snapshot.quotes:
            self.storage.save_snapshot(snapshot)
            logger.info(
                "Successfully synced live snapshot: %d quotes, %d indices.",
                len(snapshot.quotes),
                len(snapshot.indices),
            )
        else:
            logger.warning("Synced snapshot contained 0 quotes.")
        return snapshot


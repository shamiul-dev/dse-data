"""
Configuration and settings for the DSE Scraper.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DSEConfig(BaseModel):
    """Central configuration for network, scraping, and storage behavior."""

    # Target URLs
    modern_base_url: str = "https://www.dse.com.bd"
    legacy_base_url: str = "https://old.dsebd.org"

    # Timeouts (seconds)
    timeout: int = 15

    # Retries & Backoff
    max_retries: int = 4
    backoff_factor: float = 1.5

    # Rate Limiting (Polite throttling to never trigger CloudFront rate limits)
    requests_per_second: float = 1.0
    jitter_range: tuple[float, float] = (0.3, 0.8)

    # User Agent / Headers
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # SSL Verification (DSE mirrors frequently have incomplete intermediate cert chains)
    verify_ssl: bool = False

    # Optional Proxy (e.g. http://user:pass@proxy.com:8080)
    proxy: Optional[str] = None

    # SQLite Database Default Path
    sqlite_db_path: str = "dse_market.db"

    # PostgreSQL Connection URL
    postgres_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/dse_db"

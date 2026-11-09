"""
Resilient Scrapling HTTP/Stealth client with exponential backoff,
jittered rate limiting, and automatic anti-bot / browser escalation.
"""

import logging
import random
import time
from typing import Dict, Optional

from scrapling import Fetcher, StealthyFetcher

from dse_scraper.config import DSEConfig
from dse_scraper.core.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ScrapeResponse:
    """Standardized response wrapper across Fetcher and StealthyFetcher."""

    def __init__(self, status: int, text: str, body: bytes, url: str):
        self.status = status
        self.text = text
        self.body = body
        self.url = url

    @property
    def is_success(self) -> bool:
        return 200 <= self.status < 300


class ResilientClient:
    """
    Infallible HTTP client designed to scrape DSE endpoints reliably.
    Applies TLS fingerprint impersonation, rate limiting, exponential backoff,
    and automatic browser escalation.
    """

    def __init__(self, config: Optional[DSEConfig] = None):
        self.config = config or DSEConfig()
        self.rate_limiter = RateLimiter(
            requests_per_second=self.config.requests_per_second,
            jitter_range=self.config.jitter_range,
        )

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
        force_stealth: bool = False,
    ) -> ScrapeResponse:
        """
        Executes a resilient GET request with automatic retries and fallback.
        """
        req_headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            req_headers.update(headers)

        effective_referer = referer or self.config.modern_base_url

        if force_stealth:
            return self._fetch_stealth(url, headers=req_headers)

        last_error = None
        for attempt in range(1, self.config.max_retries + 1):
            self.rate_limiter.wait()

            try:
                # Scrapling Fetcher with curl_cffi TLS impersonation
                page = Fetcher.get(
                    url,
                    headers=req_headers,
                    timeout=self.config.timeout,
                    proxy=self.config.proxy,
                    verify=self.config.verify_ssl,
                )

                if page.status in (200, 301, 302):
                    body_bytes = page.body if isinstance(page.body, bytes) else str(page.body).encode("utf-8")
                    return ScrapeResponse(
                        status=page.status,
                        text=page.text if hasattr(page, "text") and page.text else body_bytes.decode("utf-8", errors="ignore"),
                        body=body_bytes,
                        url=url,
                    )

                # If rate-limited or server error (502, 503, 504), backoff and retry
                if page.status in (429, 500, 502, 503, 504):
                    delay = (self.config.backoff_factor ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        "Status %d received for %s (attempt %d/%d). Backing off for %.2fs...",
                        page.status, url, attempt, self.config.max_retries, delay
                    )
                    time.sleep(delay)
                    continue

                # If 403 Forbidden or WAF challenge encountered, escalate to StealthyFetcher
                if page.status == 403:
                    logger.warning("Status 403 encountered on %s. Escalating to StealthyFetcher...", url)
                    return self._fetch_stealth(url, headers=req_headers)

                # Return other status codes directly
                body_bytes = page.body if isinstance(page.body, bytes) else str(page.body).encode("utf-8")
                return ScrapeResponse(status=page.status, text=page.text, body=body_bytes, url=url)

            except Exception as exc:
                last_error = exc
                delay = (self.config.backoff_factor ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(
                    "Connection error on %s: %s (attempt %d/%d). Retrying in %.2fs...",
                    url, exc, attempt, self.config.max_retries, delay
                )
                time.sleep(delay)

        # If standard fetcher exhausted retries, try StealthyFetcher as final resort
        logger.warning("Standard fetcher retries exhausted for %s. Attempting StealthyFetcher fallback...", url)
        try:
            return self._fetch_stealth(url, headers=req_headers)
        except Exception as final_exc:
            logger.error("All fetch attempts failed for %s. Last error: %s", url, final_exc or last_error)
            return ScrapeResponse(status=599, text="", body=b"", url=url)

    def _fetch_stealth(self, url: str, headers: Optional[Dict[str, str]] = None) -> ScrapeResponse:
        """Fallback to headless anti-detect browser via Scrapling StealthyFetcher."""
        try:
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                timeout=self.config.timeout * 2 * 1000,
            )
            body_bytes = page.body if isinstance(page.body, bytes) else str(page.body).encode("utf-8")
            return ScrapeResponse(
                status=getattr(page, "status", 200) or 200,
                text=page.text if hasattr(page, "text") and page.text else body_bytes.decode("utf-8", errors="ignore"),
                body=body_bytes,
                url=url,
            )
        except Exception as exc:
            logger.error("StealthyFetcher failed for %s: %s", url, exc)
            return ScrapeResponse(status=599, text="", body=b"", url=url)

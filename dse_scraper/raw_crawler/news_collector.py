"""
Raw collector for News & Announcements domain.
Extracts real-time company news, board meeting schedules, dividend notices, and disclosures.
Uses DSE's official REST endpoint (/api/live/news) with fallback to HTML parsing.
"""

from datetime import date, timedelta
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List

from dse_scraper.core.client import ResilientClient

logger = logging.getLogger(__name__)


class NewsCollector:
    def __init__(self, client: ResilientClient, output_dir: Path):
        self.client = client
        self.output_dir = output_dir / "news"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self) -> Dict[str, int]:
        results = {}
        results["news_and_announcements"] = self.collect_recent_news(days=7)
        return results

    def collect_recent_news(self, days: int = 7) -> int:
        """Fetches news for a given range of days via REST API with fallback."""
        all_news = []
        today = date.today()
        from_date = (today - timedelta(days=days)).isoformat()
        to_date = today.isoformat()

        # Primary method: Direct REST API (/api/live/news)
        api_url = f"{self.client.config.modern_base_url}/api/live/news?from={from_date}&to={to_date}"
        res = self.client.get(api_url, headers={"Accept": "application/json"})

        if res.is_success:
            try:
                data = json.loads(res.body.decode("utf-8", errors="ignore"))
                rows = data.get("rows") or []
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    news_id = r.get("id")
                    symbol = str(r.get("code") or "").strip().upper() or None
                    all_news.append({
                        "news_id": news_id,
                        "symbol": symbol,
                        "company_name": r.get("name"),
                        "sector": r.get("sector"),
                        "date": r.get("date"),
                        "time": r.get("time"),
                        "type": r.get("type"),
                        "summary": r.get("summary", ""),
                        "body": r.get("body", ""),
                    })

                if all_news:
                    (self.output_dir / "news_and_announcements.json").write_text(
                        json.dumps(all_news, indent=2), encoding="utf-8"
                    )
                    logger.info("Saved news and announcements via REST API (%d items).", len(all_news))
                    return len(all_news)
            except Exception as exc:
                logger.warning("Failed to decode /api/live/news JSON: %s. Falling back to page scraping.", exc)

        # Fallback method: HTML RSC scraping
        logger.info("Falling back to HTML page scraping for news...")
        seen_keys = set()
        for d_offset in range(days):
            target_date = (today - timedelta(days=d_offset)).isoformat()
            url = f"{self.client.config.modern_base_url}/news?from={target_date}&to={target_date}"
            res = self.client.get(url)
            if not res.is_success:
                continue

            text = res.body.decode("utf-8", errors="ignore")
            # Improved regex extracting individual properties flexibly
            item_blocks = re.findall(r'\{\\"id\\":\\"[^"]+\\"(?:.(?!\{\\"id\\"))*?\}', text)
            for block in item_blocks:
                id_m = re.search(r'\\"id\\":\\"([^\\"]+)\\"', block)
                summary_m = re.search(r'\\"summary\\":\\"([^\\"]+)\\"', block)
                date_m = re.search(r'\\"date\\":\\"([^\\"]+)\\"', block)
                time_m = re.search(r'\\"time\\":\\"([^\\"]+)\\"', block)
                type_m = re.search(r'\\"type\\":\\"([^\\"]+)\\"', block)
                body_m = re.search(r'\\"body\\":\\"(.*?)\\"(?:,\s*\\"[a-zA-Z0-9_]+\\"|\})', block)

                news_id = id_m.group(1) if id_m else None
                summary = summary_m.group(1) if summary_m else ""
                symbol = summary.split(":")[0].strip() if ":" in summary else None

                key = news_id or (symbol, date_m.group(1) if date_m else None, summary)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_news.append({
                        "news_id": news_id,
                        "symbol": symbol,
                        "date": date_m.group(1) if date_m else None,
                        "time": time_m.group(1) if time_m else None,
                        "type": type_m.group(1) if type_m else None,
                        "summary": summary,
                        "body": body_m.group(1).replace(r'\"', '"').replace(r'\n', '\n') if body_m else "",
                    })

        (self.output_dir / "news_and_announcements.json").write_text(
            json.dumps(all_news, indent=2), encoding="utf-8"
        )
        logger.info("Saved news and announcements (%d items).", len(all_news))
        return len(all_news)

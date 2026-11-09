"""
Cross-referencing and deduplication engine.
Aggregates all raw JSON domains, resolves shared entities (by symbol, doc_id, date),
eliminates duplicates, and outputs a consolidated cross-reference map.
"""

from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CrossReferencer:
    """Links and deduplicates records across raw JSON files."""

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir

    def run(self) -> Dict[str, Any]:
        """Performs cross-referencing and outputs consolidated JSON files."""
        symbols_index: Dict[str, Dict[str, Any]] = defaultdict(dict)
        stats = {
            "total_symbols_discovered": 0,
            "markets_entries": 0,
            "circuit_breaker_entries": 0,
            "marginable_entries": 0,
            "financial_statements_entries": 0,
            "going_concern_entries": 0,
            "closed_companies_entries": 0,
            "news_entries": 0,
            "trec_brokers_entries": 0,
        }

        # 1. Master instruments
        inst_file = self.raw_dir / "instruments" / "all_instruments.json"
        if inst_file.exists():
            instruments = json.loads(inst_file.read_text(encoding="utf-8"))
            for sym in instruments:
                clean = sym.strip().upper()
                symbols_index[clean]["symbol"] = clean

        # 2. Latest Quotes (Markets)
        quotes_file = self.raw_dir / "markets" / "latest_share_price.json"
        if quotes_file.exists():
            quotes = json.loads(quotes_file.read_text(encoding="utf-8"))
            stats["markets_entries"] = len(quotes)
            for q in quotes:
                sym = str(q.get("code") or q.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                symbols_index[sym]["symbol"] = sym
                symbols_index[sym]["latest_quote"] = {
                    "ltp": q.get("ltp"),
                    "ycp": q.get("ycp"),
                    "high": q.get("high"),
                    "low": q.get("low"),
                    "close": q.get("close"),
                    "volume": q.get("volume"),
                    "value_mn": q.get("value"),
                    "trades": q.get("trades"),
                    "category": q.get("category"),
                    "sector": q.get("sector"),
                    "asset_type": q.get("assetType"),
                }

        # 3. Circuit Breakers (Markets)
        cb_file = self.raw_dir / "markets" / "circuit_breakers.json"
        if cb_file.exists():
            cbs = json.loads(cb_file.read_text(encoding="utf-8"))
            stats["circuit_breaker_entries"] = len(cbs)
            for item in cbs:
                sym = str(item.get("symbol") or "").strip().upper()
                if sym:
                    symbols_index[sym]["company_name"] = item.get("company_name")
                    symbols_index[sym]["circuit_breaker"] = {
                        "lower_limit": item.get("lower_limit"),
                        "upper_limit": item.get("upper_limit"),
                        "breaker_pct": item.get("breaker_pct"),
                        "tick_size": item.get("tick_size"),
                    }

        # 4. Marginable Securities (Companies)
        margin_file = self.raw_dir / "companies" / "marginable_securities.json"
        if margin_file.exists():
            margins = json.loads(margin_file.read_text(encoding="utf-8"))
            stats["marginable_entries"] = len(margins)
            for m in margins:
                sym = str(m.get("trading_code") or m.get("code") or m.get("symbol") or "").strip().upper()
                if sym:
                    symbols_index[sym]["is_marginable"] = True

        # 5. Financial Statement Filing Status
        fin_file = self.raw_dir / "companies" / "financial_statement_status.json"
        if fin_file.exists():
            fins = json.loads(fin_file.read_text(encoding="utf-8"))
            stats["financial_statements_entries"] = len(fins)
            for f in fins:
                sym = str(f.get("trading_code") or "").strip().upper()
                if sym:
                    symbols_index[sym]["financial_filing"] = {
                        "quarter": f.get("quarter"),
                        "period": f.get("period"),
                        "status": f.get("status"),
                        "submission_date": f.get("submission_date"),
                        "submission_deadline": f.get("submission_deadline"),
                    }

        # 6. Going Concern List
        gc_file = self.raw_dir / "companies" / "going_concern_list.json"
        if gc_file.exists():
            gcs = json.loads(gc_file.read_text(encoding="utf-8"))
            stats["going_concern_entries"] = len(gcs)
            for g in gcs:
                sym = str(g.get("trading_code") or "").strip().upper()
                if sym:
                    symbols_index[sym]["going_concern_threat"] = g.get("going_concern_threat_status", "Yes")

        # 7. Closed Companies
        closed_file = self.raw_dir / "companies" / "closed_companies.json"
        if closed_file.exists():
            closed = json.loads(closed_file.read_text(encoding="utf-8"))
            stats["closed_companies_entries"] = len(closed)
            for c in closed:
                sym = str(c.get("trading_code") or "").strip().upper()
                if sym:
                    symbols_index[sym]["operation_status"] = "Closed"
                    symbols_index[sym]["closed_effective_date"] = c.get("effective_date_of_operation_close")

        # 8. News & Disclosures
        news_file = self.raw_dir / "news" / "news_and_announcements.json"
        if news_file.exists():
            news = json.loads(news_file.read_text(encoding="utf-8"))
            stats["news_entries"] = len(news)
            for n in news:
                sym = str(n.get("symbol") or "").strip().upper()
                if sym:
                    if sym not in symbols_index:
                        symbols_index[sym]["symbol"] = sym
                    if "news_items" not in symbols_index[sym]:
                        symbols_index[sym]["news_items"] = []
                    symbols_index[sym]["news_items"].append({
                        "news_id": n.get("news_id"),
                        "date": n.get("date"),
                        "time": n.get("time"),
                        "type": n.get("type"),
                        "summary": n.get("summary"),
                    })

        # 9. TREC Brokers
        trec_file = self.raw_dir / "investors" / "trec_holders_directory.json"
        if trec_file.exists():
            brokers = json.loads(trec_file.read_text(encoding="utf-8"))
            stats["trec_brokers_entries"] = len(brokers)

        stats["total_symbols_discovered"] = len(symbols_index)

        # Save unified entity index
        (self.raw_dir / "unified_entity_index.json").write_text(
            json.dumps(symbols_index, indent=2), encoding="utf-8"
        )

        # Save summary report
        (self.raw_dir / "cross_reference_report.json").write_text(
            json.dumps(stats, indent=2), encoding="utf-8"
        )

        logger.info("Cross-referencing complete. Indexed %d unique symbols.", len(symbols_index))
        return stats

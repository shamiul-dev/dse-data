"""
Command Line Interface for DSE Scraper.
"""

import argparse
from datetime import date, timedelta
import logging
import sys
from pathlib import Path

from dse_scraper import DSEScraper, DSEConfig
from dse_scraper.raw_crawler.runner import RawDataCrawler
from dse_scraper.storage.alchemy.postgres_storage import PostgresAlchemyStorage
from dse_scraper.storage.sqlite_storage import SQLiteStorage

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def cmd_live(scraper: DSEScraper, args: argparse.Namespace) -> None:
    print("Fetching live market snapshot from DSE...")
    snapshot = scraper.live.sync()
    print(f"Success! Captured {len(snapshot.quotes)} instruments and {len(snapshot.indices)} indices.")
    for idx in snapshot.indices:
        print(f"  {idx.key}: {idx.value:,.2f} ({idx.change:+.2f}, {idx.percent:+.2f}%)")
    if snapshot.totals:
        print(f"  Market Turnover: {snapshot.totals.turnover_mn:,.2f} mn BDT | Trades: {snapshot.totals.trades:,}")


def cmd_backfill(scraper: DSEScraper, args: argparse.Namespace) -> None:
    to_date = args.to_date or date.today().isoformat()
    if args.from_date:
        from_date = args.from_date
    else:
        # Default to 30 days back
        from_date = (date.today() - timedelta(days=args.days or 30)).isoformat()

    print(f"Backfilling historical EOD from {from_date} to {to_date} (symbol: {args.symbol or 'ALL'})...")
    count = scraper.history.backfill(from_date=from_date, to_date=to_date, symbol=args.symbol)
    print(f"Backfill complete! Persisted {count:,} historical records.")


def cmd_company(scraper: DSEScraper, args: argparse.Namespace) -> None:
    if args.symbol:
        sym = args.symbol.upper()
        print(f"Fetching fundamentals for {sym}...")
        profile = scraper.company.sync_company(sym)
        print(f"Company: {profile.name or profile.symbol} ({profile.sector or 'Unknown Sector'})")
        print(f"  Authorized Capital: {profile.authorized_capital} mn | Paid-up: {profile.paid_up_capital} mn")
        print(f"  P/E: {profile.pe_ratio} | EPS: {profile.eps} | NAV: {profile.nav_per_share}")
        print(f"  Sponsor: {profile.shareholding_sponsor}% | Public: {profile.shareholding_public}%")
    else:
        print("Syncing fundamentals for all instruments in database...")
        resume = not getattr(args, "fresh", False)
        count = scraper.company.sync_all(resume=resume)
        print(f"Synced {count} company profiles.")


def cmd_status(scraper: DSEScraper, args: argparse.Namespace) -> None:
    if isinstance(scraper.storage, PostgresAlchemyStorage):
        with scraper.storage.db.session() as sess:
            from sqlalchemy import text
            print("\n=== PostgreSQL Database Status (dse_db) ===")
            tables = [
                "instruments",
                "quotes",
                "circuit_breakers",
                "financial_filings",
                "going_concern_threats",
                "news_announcements",
                "trec_brokers",
                "market_summaries",
                "daily_eod",
                "company_profiles",
            ]
            for tbl in tables:
                cnt = sess.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
                print(f"  {tbl:<24}: {cnt:,} rows")
            print()
    elif isinstance(scraper.storage, SQLiteStorage):
        with scraper.storage._connection() as conn:
            inst_count = conn.execute("SELECT count(*) FROM instruments").fetchone()[0]
            quotes_count = conn.execute("SELECT count(*) FROM latest_quotes").fetchone()[0]
            eod_count = conn.execute("SELECT count(*) FROM daily_eod").fetchone()[0]
            profiles_count = conn.execute("SELECT count(*) FROM company_profiles").fetchone()[0]
            ticks_count = conn.execute("SELECT count(*) FROM intraday_ticks").fetchone()[0]

        print("\n=== DSE SQLite Database Status ===")
        print(f"Database File:    {scraper.config.sqlite_db_path}")
        print(f"Instruments:      {inst_count:,}")
        print(f"Latest Quotes:    {quotes_count:,}")
        print(f"Historical EOD:   {eod_count:,}")
        print(f"Company Profiles: {profiles_count:,}")
        print(f"Intraday Ticks:   {ticks_count:,}\n")


def cmd_load_postgres(config: DSEConfig, args: argparse.Namespace) -> None:
    import json
    raw_dir = Path(args.raw or "raw_data")
    db_url = args.url or config.postgres_url
    print(f"\nConnecting to PostgreSQL at {db_url} using SQLAlchemy 2.0...")

    storage = PostgresAlchemyStorage(db_url=db_url)
    print("Database tables initialized successfully via SQLAlchemy metadata!")

    # 1. Ingest Unified Index
    unified_file = raw_dir / "unified_entity_index.json"
    if unified_file.exists():
        unified_data = json.loads(unified_file.read_text(encoding="utf-8"))
        count = storage.ingest_unified_entities(unified_data)
        print(f"  Ingested {count:,} instruments, circuit breakers & compliance statuses.")

    # 2. Ingest News
    news_file = raw_dir / "news" / "news_and_announcements.json"
    if news_file.exists():
        news_data = json.loads(news_file.read_text(encoding="utf-8"))
        count = storage.ingest_news(news_data)
        print(f"  Ingested {count:,} news and announcements.")

    # 3. Ingest TREC Brokers
    trec_file = raw_dir / "investors" / "trec_holders_directory.json"
    if trec_file.exists():
        trec_data = json.loads(trec_file.read_text(encoding="utf-8"))
        count = storage.ingest_trec_brokers(trec_data)
        print(f"  Ingested {count:,} licensed brokerage firms (TREC holders).")

    # 4. Ingest Market Summaries
    summary_file = raw_dir / "markets" / "market_summary_history.json"
    if summary_file.exists():
        summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
        count = storage.ingest_market_summaries(summary_data)
        print(f"  Ingested {count:,} market summary trading sessions.")

    # Print PostgreSQL record counts
    with storage.db.session() as sess:
        from sqlalchemy import text
        print("\n=== PostgreSQL Database Status (dse_db) ===")
        for tbl in ["instruments", "quotes", "circuit_breakers", "financial_filings", "going_concern_threats", "news_announcements", "trec_brokers", "market_summaries"]:
            cnt = sess.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
            print(f"  {tbl:<24}: {cnt:,} rows")
    print("\nPostgreSQL load complete!\n")


def cmd_crawl_all(config: DSEConfig, args: argparse.Namespace) -> None:
    print("\nStarting full site crawl across all 5 navigation domains with strict rate limits...")
    crawler = RawDataCrawler(output_dir=args.out or "raw_data", config=config)
    summary = crawler.crawl_all()
    print("\n=== Crawl Summary ===")
    for domain, stats in summary.items():
        print(f"Domain: {domain}")
        if isinstance(stats, dict):
            for k, v in stats.items():
                print(f"  {k}: {v}")
    print(f"\nRaw JSON files saved in: {crawler.output_dir.resolve()}\n")


def main():
    parser = argparse.ArgumentParser(description="DSE Market Data Scraper CLI")
    parser.add_argument("--storage", choices=["postgres", "sqlite"], default="postgres", help="Storage backend (default: postgres)")
    parser.add_argument("--url", help="PostgreSQL connection URL override")
    parser.add_argument("--db", default="dse_market.db", help="Path to SQLite database file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # crawl-all command
    p_crawl = subparsers.add_parser("crawl-all", help="Crawl all 5 domains into separate JSONs and cross-reference")
    p_crawl.add_argument("--out", default="raw_data", help="Output directory for raw JSONs")

    # load-postgres command
    p_pg = subparsers.add_parser("load-postgres", help="Load raw cross-referenced data into PostgreSQL via SQLAlchemy")
    p_pg.add_argument("--raw", default="raw_data", help="Directory containing raw JSON files")
    p_pg.add_argument("--url", help="PostgreSQL connection URL override")

    # live command
    subparsers.add_parser("live", help="Capture live market snapshot")

    # backfill command
    p_backfill = subparsers.add_parser("backfill", help="Backfill historical EOD prices")
    p_backfill.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    p_backfill.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    p_backfill.add_argument("--days", type=int, default=30, help="Days to look back if --from is omitted")
    p_backfill.add_argument("--symbol", help="Optional specific ticker (e.g. GP)")

    # company command
    p_company = subparsers.add_parser("company", help="Sync company fundamentals")
    p_company.add_argument("--symbol", help="Specific ticker symbol (omits to sync all)")
    p_company.add_argument("--fresh", action="store_true", help="Ignore checkpoint and sync from beginning")

    # backfill-2yr command
    p_b2 = subparsers.add_parser("backfill-2yr", help="Run complete 2-year backfill across all 4 phases")
    p_b2.add_argument("--skip-phase", type=int, nargs="*", default=[], help="Phase numbers to skip (1=Summary, 2=News, 3=EOD, 4=Fundamentals)")

    # status command
    subparsers.add_parser("status", help="Show database record counts")

    args = parser.parse_args()
    config = DSEConfig(sqlite_db_path=args.db)
    if args.url:
        config.postgres_url = args.url

    # Select storage engine
    if args.storage == "postgres":
        storage = PostgresAlchemyStorage(db_url=config.postgres_url)
    else:
        storage = SQLiteStorage(config.sqlite_db_path)

    scraper = DSEScraper(storage=storage, config=config)

    if args.command == "crawl-all":
        cmd_crawl_all(config, args)
    elif args.command == "load-postgres":
        cmd_load_postgres(config, args)
    elif args.command == "live":
        cmd_live(scraper, args)
    elif args.command == "backfill":
        cmd_backfill(scraper, args)
    elif args.command == "backfill-2yr":
        from dse_scraper.pipeline.backfill_2year import TwoYearBackfillPipeline
        pipeline = TwoYearBackfillPipeline(config=config, storage=storage if isinstance(storage, PostgresAlchemyStorage) else None)
        pipeline.run_all(skip_phases=args.skip_phase)
    elif args.command == "company":
        cmd_company(scraper, args)
    elif args.command == "status":
        cmd_status(scraper, args)


if __name__ == "__main__":
    main()

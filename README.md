# DSE Scraper (Dhaka Stock Exchange)

A modular, high-reliability Python scraping and ingestion engine for the **Dhaka Stock Exchange (DSE)** built with **Scrapling** and **SQLAlchemy 2.0** for **PostgreSQL**.

---

## Key Features

- **Dual-Engine Discovery**: Leverages DSE's modern Next.js REST API (`/api/live/snapshot`, `/api/live/data-archive/...`) for high-speed columnar JSON ingestion alongside resilient HTML scraping for deep company balance sheets.
- **Scrapling Anti-Bot & TLS Impersonation**: Uses `curl_cffi` to match real browser TLS/JA3/JA4 fingerprints with automatic escalation to headless browser (`StealthyFetcher`) if CloudFront or WAF challenges arise.
- **SQLAlchemy 2.0 ORM**: Fully typed declarative models with connection pooling and PostgreSQL native upserts (`ON CONFLICT DO UPDATE`).
- **Comprehensive Coverage (All 5 Domains)**:
  1. **Markets**: Real-time quotes, indices (DSEX, DS30, DSES), circuit breakers, P/E ratios, and market turnover history.
  2. **Instruments**: Master registry of 686 securities across equities, mutual funds, corporate bonds, and treasury bonds.
  3. **Companies & Filings**: Margin-financeable list, financial statement filing compliance, going-concern flags, and closed companies.
  4. **News & Announcements**: Real-time corporate news, board meeting schedules, dividend notices, and Price Sensitive Information (PSI).
  5. **Investors & Brokers**: Complete directory of 307 licensed brokerage firms (TREC holders).
- **TDD-Tested**: 12 automated unit tests covering normalizers, parsers, SQLite, and PostgreSQL storage.

---

## Project Structure

```text
dse-data/
├── dse_scraper/                 # Importable core package
│   ├── config.py                # Timeouts, retries, rate-limits, database URLs
│   ├── core/
│   │   ├── client.py            # Resilient Scrapling client with backoff & stealth fallback
│   │   ├── normalizers.py       # Safe conversion utilities (float, int, date, str)
│   │   └── rate_limiter.py      # Token-bucket rate limiter with randomized jitter
│   ├── models/                  # Strongly-typed Pydantic domain models
│   ├── parsers/                 # Pure deterministic parsers
│   ├── raw_crawler/             # Raw category crawlers and cross-referencer
│   ├── services/                # High-level domain services (Live, History, Company)
│   └── storage/                 # Persistence layer
│       ├── base.py              # Abstract BaseStorage interface
│       ├── sqlite_storage.py    # SQLite (WAL mode)
│       ├── memory_storage.py    # In-memory storage (DataFrames / testing)
│       └── alchemy/             # SQLAlchemy 2.0 PostgreSQL package
│           ├── database.py      # Engine & session manager
│           ├── models.py        # DeclarativeBase ORM models
│           └── postgres_storage.py # Postgres adapter with native upserts
├── raw_data/                    # Saved JSON files partitioned by category
├── cli.py                       # Standalone CLI interface
├── pyproject.toml               # Package configuration
└── tests/                       # Unit tests & offline fixtures
```

---

## PostgreSQL Setup & Database Tables

The PostgreSQL connection URL is configured in [`dse_scraper/config.py`](dse_scraper/config.py):
```text
postgresql+psycopg://postgres:postgres@127.0.0.1:5432/dse_db
```

### Relational Tables (`dse_db`):
- `instruments`: Master list of securities (symbol, sector, category, board, marginable, operational status)
- `quotes`: Real-time session price ticks (ltp, high, low, close, volume, value, trades)
- `circuit_breakers`: Daily upper/lower limits, floor/ceiling prices, tick sizes
- `financial_filings`: Quarterly submission compliance, deadlines, submission dates
- `going_concern_threats`: Auditor going-concern risk flags
- `news_announcements`: Corporate announcements, earnings notices, board meetings
- `trec_brokers`: Licensed stock brokerage directory, contact info, representatives
- `market_summaries`: Daily session indices and turnover benchmarks
- `daily_eod`: Historical OHLCV price archive

---

## CLI Usage

```bash
# Intelligent daily sync (auto-detects missing dates, pulls latest news, and live ticks)
python cli.py sync

# 1. Crawl all 5 domains into separate raw JSONs and cross-reference
python cli.py crawl-all

# 2. Ingest raw cross-referenced data into PostgreSQL (dse_db)
python cli.py load-postgres

# 3. Sync live market snapshot into database (during market hours)
python cli.py live

# 4. Backfill historical daily OHLCV prices
python cli.py backfill --days 30

# 5. Run full 2-year backfill across all 4 phases
python cli.py backfill-2yr

# 6. Sync company fundamentals (balance sheet, PE, shareholding)
python cli.py company --symbol GP

# 7. Check database status
python cli.py status
```

---

## Running Tests

```bash
python -m pytest
```

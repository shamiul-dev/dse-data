"""
SQLAlchemy 2.0 Engine and Session Management for PostgreSQL.
"""

from contextlib import contextmanager
import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dse_scraper.storage.alchemy.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLAlchemy 2.0 engine, sessions, and DDL migrations."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(
            self.db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        """Creates all tables in PostgreSQL if they don't already exist."""
        logger.info("Initializing PostgreSQL tables using SQLAlchemy metadata...")
        Base.metadata.create_all(self.engine)
        logger.info("PostgreSQL tables initialized successfully.")

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Transactional session context manager."""
        sess: Session = self.session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()


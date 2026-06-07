"""Database engine and session management."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.storage.models import Base

logger = logging.getLogger(__name__)


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    """Enable WAL mode and foreign key enforcement for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class Database:
    """Manages the SQLAlchemy engine and provides session context managers.

    Supports both file-based SQLite (production) and in-memory SQLite (tests).
    WAL journal mode is enabled for concurrent read/write access from the
    scheduler and the dashboard.
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._engine = self._build_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        logger.info("Database initialised: %s", database_url)

    def _build_engine(self, url: str) -> Engine:
        is_memory = url == "sqlite:///:memory:"

        kwargs: dict = {
            "echo": False,
        }

        if url.startswith("sqlite"):
            # For file-based SQLite, ensure the parent directory exists
            if not is_memory:
                db_path = url.replace("sqlite:///", "")
                os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

            if is_memory:
                # StaticPool keeps the same connection object for in-memory DBs
                kwargs["connect_args"] = {"check_same_thread": False}
                kwargs["poolclass"] = StaticPool
            else:
                kwargs["connect_args"] = {"check_same_thread": False}

        engine = create_engine(url, **kwargs)

        if url.startswith("sqlite"):
            event.listen(engine, "connect", _configure_sqlite)

        return engine

    def create_tables(self) -> None:
        """Create all tables defined in the ORM models (idempotent)."""
        Base.metadata.create_all(self._engine)
        logger.info("Database tables created/verified")

    def drop_tables(self) -> None:
        """Drop all tables — used only in tests."""
        Base.metadata.drop_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional session scope with automatic rollback on error."""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def health_check(self) -> bool:
        """Return True if the database is reachable."""
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.error("Database health check failed: %s", exc)
            return False

    def dispose(self) -> None:
        """Dispose the engine connection pool (call before process exit)."""
        self._engine.dispose()
        logger.debug("Database engine disposed")

    @property
    def engine(self) -> Engine:
        return self._engine

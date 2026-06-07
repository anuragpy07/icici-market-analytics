"""Data access layer — all database reads and writes go through this class."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy import delete, distinct, func, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.storage.database import Database
from src.storage.models import (
    CorporateAction,
    LiveQuote,
    Metric,
    Price,
    Ranking,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class Repository:
    """Provides typed, high-level access to all database tables.

    All mutations use SQLite's INSERT OR REPLACE semantics (upsert) to
    allow idempotent pipeline reruns without duplicates.

    Query style: SQLAlchemy 2.x ``select()``-based throughout.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Prices ────────────────────────────────────────────────────────────────

    def upsert_prices(self, df: pd.DataFrame) -> int:
        """Upsert a DataFrame of price rows. Returns the row count written."""
        if df.empty:
            return 0

        records = df.to_dict(orient="records")
        written = 0

        with self._db.session() as sess:
            for rec in records:
                stmt = (
                    sqlite_insert(Price)
                    .values(**rec)
                    .on_conflict_do_update(
                        index_elements=["symbol", "date"],
                        set_={
                            k: rec[k]
                            for k in rec
                            if k not in ("id", "symbol", "date", "created_at")
                        },
                    )
                )
                sess.execute(stmt)
                written += 1

        logger.debug("Upserted %d price rows", written)
        return written

    def get_prices(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return adjusted OHLCV data for a symbol, optionally filtered by date range."""
        with self._db.session() as sess:
            stmt = select(Price).where(Price.symbol == symbol)
            if start_date:
                stmt = stmt.where(Price.date >= start_date)
            if end_date:
                stmt = stmt.where(Price.date <= end_date)
            stmt = stmt.order_by(Price.date)
            rows = sess.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "symbol": r.symbol,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "adj_close": r.adj_close,
                    "adj_factor": r.adj_factor,
                }
                for r in rows
            ]
        ).set_index("date")

    def get_all_symbols_with_prices(self) -> list[str]:
        """Return a sorted list of symbols that have at least one price row."""
        with self._db.session() as sess:
            rows = sess.execute(
                select(distinct(Price.symbol)).order_by(Price.symbol)
            ).all()
        return [row[0] for row in rows]

    # ── Metrics ───────────────────────────────────────────────────────────────

    def upsert_metrics(self, df: pd.DataFrame) -> int:
        """Upsert a DataFrame of metric rows."""
        if df.empty:
            return 0

        records = df.to_dict(orient="records")
        written = 0

        with self._db.session() as sess:
            for rec in records:
                stmt = (
                    sqlite_insert(Metric)
                    .values(**rec)
                    .on_conflict_do_update(
                        index_elements=["symbol", "date"],
                        set_={
                            k: rec[k]
                            for k in rec
                            if k not in ("id", "symbol", "date", "created_at")
                        },
                    )
                )
                sess.execute(stmt)
                written += 1

        logger.debug("Upserted %d metric rows", written)
        return written

    def get_latest_metrics(self, symbols: Optional[list[str]] = None) -> pd.DataFrame:
        """Return the most recent metric row per symbol."""
        with self._db.session() as sess:
            # Subquery: latest date per symbol
            max_date_subq = (
                select(Metric.symbol, func.max(Metric.date).label("max_date"))
                .group_by(Metric.symbol)
                .subquery()
            )
            stmt = select(Metric).join(
                max_date_subq,
                (Metric.symbol == max_date_subq.c.symbol)
                & (Metric.date == max_date_subq.c.max_date),
            )
            if symbols:
                stmt = stmt.where(Metric.symbol.in_(symbols))
            rows = sess.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "symbol": r.symbol,
                    "date": r.date,
                    "return_1y": r.return_1y,
                    "return_6m": r.return_6m,
                    "return_3m": r.return_3m,
                    "daily_return": r.daily_return,
                    "annualized_volatility": r.annualized_volatility,
                    "rolling_volatility_21d": r.rolling_volatility_21d,
                    "momentum_score": r.momentum_score,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown": r.max_drawdown,
                }
                for r in rows
            ]
        )

    def get_metrics_history(self, symbol: str) -> pd.DataFrame:
        """Return full metric history for a symbol (for rolling vol charts)."""
        with self._db.session() as sess:
            rows = sess.execute(
                select(Metric)
                .where(Metric.symbol == symbol)
                .order_by(Metric.date)
            ).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "rolling_volatility_21d": r.rolling_volatility_21d,
                    "annualized_volatility": r.annualized_volatility,
                    "momentum_score": r.momentum_score,
                    "return_1y": r.return_1y,
                }
                for r in rows
            ]
        ).set_index("date")

    # ── Live Quotes ───────────────────────────────────────────────────────────

    def upsert_live_quote(self, quote: dict[str, Any]) -> None:
        """Insert a live quote and prune stale rows for the same symbol.

        LiveQuote has no unique constraint on ``symbol`` (multiple quotes
        accumulate over time for audit / replay purposes).  We keep only
        the single most-recent row per symbol to bound table growth.
        """
        with self._db.session() as sess:
            # Plain insert — id is auto-generated so no conflict possible
            sess.execute(sqlite_insert(LiveQuote).values(**quote))

            # Delete all older rows for this symbol in the same transaction
            sess.execute(
                text(
                    "DELETE FROM live_quotes WHERE symbol = :sym AND id NOT IN "
                    "(SELECT MAX(id) FROM live_quotes WHERE symbol = :sym)"
                ),
                {"sym": quote["symbol"]},
            )

    def get_live_quotes(self, symbols: Optional[list[str]] = None) -> pd.DataFrame:
        """Return the latest live quote for each requested symbol."""
        with self._db.session() as sess:
            # Subquery: max id per symbol (= most recently inserted row)
            max_id_subq = select(func.max(LiveQuote.id).label("max_id")).group_by(
                LiveQuote.symbol
            )
            if symbols is not None:
                max_id_subq = max_id_subq.where(LiveQuote.symbol.in_(symbols))
            max_id_subq = max_id_subq.subquery()

            rows = sess.execute(
                select(LiveQuote).where(
                    LiveQuote.id.in_(select(max_id_subq.c.max_id))
                )
            ).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "symbol": r.symbol,
                    "ltp": r.ltp,
                    "bid": r.bid,
                    "ask": r.ask,
                    "volume": r.volume,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "prev_close": r.prev_close,
                    "change": r.change,
                    "change_pct": r.change_pct,
                    "is_stale": r.is_stale,
                    "timestamp": r.timestamp,
                }
                for r in rows
            ]
        )

    # ── Corporate Actions ─────────────────────────────────────────────────────

    def upsert_corporate_actions(self, df: pd.DataFrame) -> int:
        """Upsert corporate action events."""
        if df.empty:
            return 0

        records = df.to_dict(orient="records")
        written = 0

        with self._db.session() as sess:
            for rec in records:
                stmt = (
                    sqlite_insert(CorporateAction)
                    .values(**rec)
                    .on_conflict_do_update(
                        index_elements=["symbol", "ex_date", "action_type"],
                        set_={"ratio": rec["ratio"], "dividend_amount": rec["dividend_amount"]},
                    )
                )
                sess.execute(stmt)
                written += 1

        return written

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        with self._db.session() as sess:
            stmt = (
                select(CorporateAction)
                .where(CorporateAction.symbol == symbol)
                .order_by(CorporateAction.ex_date)
            )
            if start_date:
                stmt = stmt.where(CorporateAction.ex_date >= start_date)
            if end_date:
                stmt = stmt.where(CorporateAction.ex_date <= end_date)
            rows = sess.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "symbol": r.symbol,
                    "ex_date": r.ex_date,
                    "action_type": r.action_type,
                    "ratio": r.ratio,
                    "dividend_amount": r.dividend_amount,
                }
                for r in rows
            ]
        )

    # ── Rankings ──────────────────────────────────────────────────────────────

    def upsert_rankings(self, df: pd.DataFrame) -> int:
        """Replace today's ranking rows (delete then insert)."""
        if df.empty:
            return 0

        records = df.to_dict(orient="records")
        comp_date = records[0].get("computation_date", date.today())

        with self._db.session() as sess:
            sess.execute(
                delete(Ranking).where(Ranking.computation_date == comp_date)
            )
            for rec in records:
                sess.execute(sqlite_insert(Ranking).values(**rec).on_conflict_do_nothing())

        return len(records)

    def get_latest_rankings(self) -> pd.DataFrame:
        """Return the most recent ranking table."""
        with self._db.session() as sess:
            max_date_row = sess.execute(
                select(func.max(Ranking.computation_date))
            ).scalar()
            if not max_date_row:
                return pd.DataFrame()

            rows = sess.execute(
                select(Ranking)
                .where(Ranking.computation_date == max_date_row)
                .order_by(Ranking.momentum_rank)
            ).scalars().all()

        return pd.DataFrame(
            [
                {
                    "symbol": r.symbol,
                    "sector": r.sector,
                    "momentum_score": r.momentum_score,
                    "momentum_rank": r.momentum_rank,
                    "momentum_percentile": r.momentum_percentile,
                    "volatility": r.volatility,
                    "volatility_rank": r.volatility_rank,
                    "return_1y": r.return_1y,
                    "return_6m": r.return_6m,
                    "return_3m": r.return_3m,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown": r.max_drawdown,
                    "computation_date": r.computation_date,
                }
                for r in rows
            ]
        )

    # ── Validation Reports ────────────────────────────────────────────────────

    def save_validation_reports(self, records: list[dict[str, Any]]) -> int:
        """Append validation report rows."""
        if not records:
            return 0

        with self._db.session() as sess:
            for rec in records:
                sess.execute(sqlite_insert(ValidationReport).values(**rec).on_conflict_do_nothing())

        return len(records)

    def get_validation_summary(self, report_date: Optional[date] = None) -> pd.DataFrame:
        """Return validation results, defaulting to the most recent run date."""
        with self._db.session() as sess:
            if report_date is None:
                report_date = sess.execute(
                    select(func.max(ValidationReport.report_date))
                ).scalar()
                if report_date is None:
                    return pd.DataFrame()

            rows = sess.execute(
                select(ValidationReport).where(
                    ValidationReport.report_date == report_date
                )
            ).scalars().all()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "symbol": r.symbol,
                    "check_name": r.check_name,
                    "status": r.status,
                    "failure_count": r.failure_count,
                    "details": r.details,
                    "report_date": r.report_date,
                }
                for r in rows
            ]
        )

    def get_last_api_call_time(self) -> Optional[datetime]:
        """Return the timestamp of the most recently saved live quote."""
        with self._db.session() as sess:
            result = sess.execute(
                select(func.max(LiveQuote.created_at))
            ).scalar()
        if result is None:
            return None
        if isinstance(result, str):
            return datetime.fromisoformat(result)
        return result

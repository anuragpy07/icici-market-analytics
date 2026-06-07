"""SQLAlchemy ORM models for the market analytics database."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Price(Base):
    """Daily OHLCV prices with adjustment factors for corporate actions."""

    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_price_symbol_date"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    exchange: str = Column(String(10), nullable=False, default="NSE")
    date: date = Column(Date, nullable=False, index=True)
    open: float | None = Column(Float)
    high: float | None = Column(Float)
    low: float | None = Column(Float)
    close: float = Column(Float, nullable=False)
    volume: int | None = Column(BigInteger)
    adj_close: float = Column(Float, nullable=False)
    adj_factor: float = Column(Float, nullable=False, default=1.0)
    is_adjusted: bool = Column(Boolean, nullable=False, default=False)
    created_at: datetime = Column(DateTime, server_default=func.now())
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Price {self.symbol} {self.date} close={self.close:.2f}>"


class Metric(Base):
    """Computed analytics metrics for each symbol on a given date."""

    __tablename__ = "metrics"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_metric_symbol_date"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    date: date = Column(Date, nullable=False, index=True)
    return_1y: float | None = Column(Float)
    return_6m: float | None = Column(Float)
    return_3m: float | None = Column(Float)
    daily_return: float | None = Column(Float)
    annualized_volatility: float | None = Column(Float)
    rolling_volatility_21d: float | None = Column(Float)
    momentum_score: float | None = Column(Float)
    sharpe_ratio: float | None = Column(Float)
    max_drawdown: float | None = Column(Float)
    created_at: datetime = Column(DateTime, server_default=func.now())
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        mom = f"{self.momentum_score:.4f}" if self.momentum_score is not None else "None"
        return f"<Metric {self.symbol} {self.date} momentum={mom}>"


class LiveQuote(Base):
    """Real-time or most-recent market quote for a symbol."""

    __tablename__ = "live_quotes"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    ltp: float = Column(Float, nullable=False)
    bid: float | None = Column(Float)
    ask: float | None = Column(Float)
    volume: int | None = Column(BigInteger)
    open: float | None = Column(Float)
    high: float | None = Column(Float)
    low: float | None = Column(Float)
    prev_close: float | None = Column(Float)
    change: float | None = Column(Float)
    change_pct: float | None = Column(Float)
    is_stale: bool = Column(Boolean, nullable=False, default=False)
    timestamp: datetime = Column(DateTime, nullable=False)
    created_at: datetime = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<LiveQuote {self.symbol} ltp={self.ltp:.2f}>"


class CorporateAction(Base):
    """Corporate events (splits, bonuses, dividends) that affect price adjustments."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint("symbol", "ex_date", "action_type", name="uq_corp_action"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    ex_date: date = Column(Date, nullable=False, index=True)
    action_type: str = Column(String(20), nullable=False)  # SPLIT | BONUS | DIVIDEND
    ratio: float = Column(Float, nullable=False, default=1.0)
    dividend_amount: float = Column(Float, nullable=False, default=0.0)
    notes: str | None = Column(Text)
    created_at: datetime = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<CorporateAction {self.symbol} {self.ex_date} {self.action_type}>"


class Ranking(Base):
    """Universe-wide momentum and volatility rankings computed periodically."""

    __tablename__ = "rankings"
    __table_args__ = (
        UniqueConstraint("computation_date", "symbol", name="uq_ranking_date_symbol"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    computation_date: date = Column(Date, nullable=False, index=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    sector: str | None = Column(String(50))
    momentum_score: float | None = Column(Float)
    momentum_rank: int | None = Column(Integer)
    momentum_percentile: float | None = Column(Float)
    volatility: float | None = Column(Float)
    volatility_rank: int | None = Column(Integer)
    return_1y: float | None = Column(Float)
    return_6m: float | None = Column(Float)
    return_3m: float | None = Column(Float)
    sharpe_ratio: float | None = Column(Float)
    max_drawdown: float | None = Column(Float)
    created_at: datetime = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Ranking {self.symbol} rank={self.momentum_rank}>"


class ValidationReport(Base):
    """Per-symbol data quality validation results."""

    __tablename__ = "validation_reports"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    report_date: date = Column(Date, nullable=False, index=True)
    symbol: str = Column(String(20), nullable=False, index=True)
    check_name: str = Column(String(50), nullable=False)
    status: str = Column(String(10), nullable=False)  # PASS | FAIL | WARN
    failure_count: int = Column(Integer, nullable=False, default=0)
    details: str | None = Column(Text)
    created_at: datetime = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ValidationReport {self.symbol} {self.check_name} {self.status}>"

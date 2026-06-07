"""Shared pytest fixtures for unit, integration, and mock API tests."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings
from src.storage.database import Database
from src.storage.repository import Repository


# ── Price series fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_prices_300() -> pd.Series:
    """300-bar adjusted close series — sufficient for all return windows."""
    np.random.seed(42)
    n = 300
    dates = pd.bdate_range("2022-01-01", periods=n)
    log_returns = np.random.normal(0.0005, 0.015, n)
    prices = 1000.0 * np.exp(np.cumsum(log_returns))
    return pd.Series(prices, index=dates, name="adj_close")


@pytest.fixture
def sample_prices_50() -> pd.Series:
    """50-bar series — insufficient for 1Y/6M metrics, sufficient for 3M."""
    np.random.seed(7)
    n = 50
    dates = pd.bdate_range("2023-01-01", periods=n)
    log_returns = np.random.normal(0.0003, 0.012, n)
    prices = 500.0 * np.exp(np.cumsum(log_returns))
    return pd.Series(prices, index=dates, name="adj_close")


@pytest.fixture
def flat_prices() -> pd.Series:
    """Constant prices — zero vol, zero returns, edge-case test."""
    dates = pd.bdate_range("2022-01-01", periods=300)
    return pd.Series(1000.0, index=dates, name="adj_close")


@pytest.fixture
def trending_down_prices() -> pd.Series:
    """Monotonically declining prices — max drawdown = full decline."""
    np.random.seed(99)
    n = 300
    dates = pd.bdate_range("2022-01-01", periods=n)
    prices = np.linspace(1000, 500, n)  # 50% decline
    return pd.Series(prices, index=dates, name="adj_close")


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """Full OHLCV DataFrame with 300 bars for processor tests."""
    np.random.seed(42)
    n = 300
    dates = pd.bdate_range("2022-01-01", periods=n).date
    closes = 1000.0 * np.exp(np.cumsum(np.random.normal(0.0005, 0.015, n)))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.01, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.01, n)))
    volumes = np.random.lognormal(14, 0.5, n).astype(int)

    return pd.DataFrame(
        {
            "date": dates,
            "symbol": "TEST",
            "exchange": "NSE",
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "adj_close": closes,
            "adj_factor": 1.0,
            "is_adjusted": False,
        }
    ).set_index("date")


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db() -> Database:
    """In-memory SQLite database with all tables created."""
    db = Database("sqlite:///:memory:")
    db.create_tables()
    yield db
    db.dispose()


@pytest.fixture
def repo(in_memory_db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(in_memory_db)


# ── Settings fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def test_settings() -> Settings:
    """Settings with MockProvider and in-memory database."""
    return Settings(
        MARKET_DATA_PROVIDER="mock",
        DATABASE_URL="sqlite:///:memory:",
        UNIVERSE_FILE="data/universe/nifty500.csv",
        UNIVERSE_SIZE_LIMIT=10,
        RISK_FREE_RATE=0.065,
        TRADING_DAYS_PER_YEAR=252,
        LOG_LEVEL="WARNING",
        CACHE_TTL_HISTORICAL=60,
        CACHE_TTL_LIVE=5,
    )


# ── Corporate action fixture ──────────────────────────────────────────────────

@pytest.fixture
def corp_actions_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "TEST",
                "ex_date": date(2022, 6, 1),
                "action_type": "SPLIT",
                "ratio": 2.0,
                "dividend_amount": 0.0,
            }
        ]
    )

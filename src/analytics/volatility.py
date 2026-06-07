"""Volatility metrics: annualised vol, rolling vol, and related risk measures."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_annualized_volatility(
    daily_returns: pd.Series,
    trading_days: int = 252,
    min_periods: int = 21,
) -> float:
    """Annualised volatility = std(daily_returns) * sqrt(trading_days).

    Args:
        daily_returns: Simple daily returns (already pct_change, no NaNs required).
        trading_days:  Convention (252 for India, same as global equities).
        min_periods:   Minimum non-NaN observations. Returns NaN if not met.
    """
    clean = daily_returns.dropna()
    if len(clean) < min_periods:
        return float("nan")
    return float(clean.std() * np.sqrt(trading_days))


def compute_rolling_volatility(
    daily_returns: pd.Series,
    window: int = 21,
    trading_days: int = 252,
    min_periods: int = 5,
) -> pd.Series:
    """Rolling annualised volatility over a sliding window.

    Returns a Series aligned with daily_returns. NaN for windows with
    fewer than min_periods observations.
    """
    return daily_returns.rolling(window=window, min_periods=min_periods).std() * np.sqrt(
        trading_days
    )


def compute_downside_volatility(
    daily_returns: pd.Series,
    target_return: float = 0.0,
    trading_days: int = 252,
) -> float:
    """Downside deviation — uses only negative excess returns.

    Used in Sortino ratio calculation.
    """
    clean = daily_returns.dropna()
    downside = clean[clean < target_return]
    if downside.empty:
        return float("nan")
    return float(downside.std() * np.sqrt(trading_days))


def compute_realized_variance(
    daily_returns: pd.Series,
    trading_days: int = 252,
) -> float:
    """Annualised realised variance."""
    clean = daily_returns.dropna()
    if clean.empty:
        return float("nan")
    return float(clean.var() * trading_days)


def compute_volatility_of_volatility(
    daily_returns: pd.Series,
    short_window: int = 21,
    long_window: int = 63,
) -> float:
    """Standard deviation of rolling 21-day vol — measures vol regime stability."""
    if len(daily_returns) < long_window:
        return float("nan")
    rolling_vol = compute_rolling_volatility(daily_returns, window=short_window)
    return float(rolling_vol.dropna().std())

"""Risk-adjusted return metrics: Sharpe ratio and maximum drawdown."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_sharpe_ratio(
    daily_returns: pd.Series,
    risk_free_rate: float = 0.065,
    trading_days: int = 252,
    min_periods: int = 21,
) -> float:
    """Annualised Sharpe ratio.

    Sharpe = (mean_excess_return * trading_days) / (std * sqrt(trading_days))
           = (mean_excess_return / std) * sqrt(trading_days)

    Args:
        daily_returns:  Simple daily returns (NaNs dropped internally).
        risk_free_rate: Annual rate; converted to daily for subtraction.
        trading_days:   252 for Indian equities.
        min_periods:    Minimum non-NaN returns. Returns NaN if not met.
    """
    clean = daily_returns.dropna()
    if len(clean) < min_periods:
        return float("nan")

    daily_rf = risk_free_rate / trading_days
    excess = clean - daily_rf
    std = excess.std()

    if np.isnan(std) or std < 1e-12:
        return float("nan")

    return float((excess.mean() / std) * np.sqrt(trading_days))


def compute_max_drawdown(prices: pd.Series) -> float:
    """Maximum peak-to-trough drawdown of the price series.

    Returns a negative number (e.g. -0.35 means a 35% drawdown).
    Returns NaN for empty or single-element series.
    """
    if len(prices) < 2:
        return float("nan")

    clean = prices.dropna()
    if clean.empty:
        return float("nan")

    rolling_peak = clean.expanding().max()
    drawdown = (clean - rolling_peak) / rolling_peak
    return float(drawdown.min())


def compute_calmar_ratio(
    prices: pd.Series,
    daily_returns: pd.Series,
    trading_days: int = 252,
) -> float:
    """Calmar ratio = annualised return / |max drawdown|.

    A higher Calmar indicates better return per unit of drawdown risk.
    """
    mdd = compute_max_drawdown(prices)
    if np.isnan(mdd) or mdd == 0:
        return float("nan")

    ann_return = float(daily_returns.dropna().mean() * trading_days)
    return ann_return / abs(mdd)


def compute_sortino_ratio(
    daily_returns: pd.Series,
    risk_free_rate: float = 0.065,
    trading_days: int = 252,
) -> float:
    """Sortino ratio using downside deviation as the risk denominator."""
    clean = daily_returns.dropna()
    if len(clean) < 21:
        return float("nan")

    daily_rf = risk_free_rate / trading_days
    excess = clean - daily_rf
    downside = excess[excess < 0]

    if downside.empty or downside.std() == 0:
        return float("nan")

    downside_vol = float(downside.std() * np.sqrt(trading_days))
    ann_excess = float(excess.mean() * trading_days)
    return ann_excess / downside_vol

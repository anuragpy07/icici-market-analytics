"""Period return calculations on adjusted price series.

All return formulas use trading-day index arithmetic, not calendar days.
Index positions follow the assignment specification exactly:
  1Y return:  price(t-21) / price(t-252) - 1
  6M return:  price(t-21) / price(t-126) - 1
  3M return:  price(t-21) / price(t-63)  - 1

The denominator excludes the latest month (21 trading days) to avoid
the well-documented short-term reversal effect in momentum strategies.
"""
from __future__ import annotations

import pandas as pd


def compute_return_1y(prices: pd.Series) -> float:
    """1-year return excluding the latest month.

    Requires at least 252 bars. Returns NaN if insufficient history.
    """
    if len(prices) < 252:
        return float("nan")
    return float(prices.iloc[-21] / prices.iloc[-252] - 1)


def compute_return_6m(prices: pd.Series) -> float:
    """6-month return excluding the latest month.

    Requires at least 126 bars. Returns NaN if insufficient history.
    """
    if len(prices) < 126:
        return float("nan")
    return float(prices.iloc[-21] / prices.iloc[-126] - 1)


def compute_return_3m(prices: pd.Series) -> float:
    """3-month return excluding the latest month.

    Requires at least 63 bars. Returns NaN if insufficient history.
    """
    if len(prices) < 63:
        return float("nan")
    return float(prices.iloc[-21] / prices.iloc[-63] - 1)


def compute_daily_returns(prices: pd.Series) -> pd.Series:
    """Compute simple daily returns from adjusted close prices.

    Returns a Series aligned with prices (first element is NaN).
    """
    return prices.pct_change()


def compute_period_return(
    prices: pd.Series,
    start_offset: int,
    end_offset: int = -21,
) -> float:
    """Generic period return between two index offsets.

    Args:
        prices: Adjusted close price series (oldest first).
        start_offset: Negative index from the end (e.g. -252 for 1Y ago).
        end_offset: Negative index for the end of the period (default -21).

    Returns NaN if the series is too short.
    """
    required = abs(start_offset)
    if len(prices) < required:
        return float("nan")
    return float(prices.iloc[end_offset] / prices.iloc[start_offset] - 1)


def compute_ytd_return(prices: pd.Series, as_of: "pd.Timestamp | None" = None) -> float:
    """Year-to-date return from the start of the current calendar year.

    Uses positional iloc rather than label-based loc so it is immune to
    index type mismatches between Python date objects and pd.Timestamp.
    """
    if prices.empty:
        return float("nan")

    idx = pd.to_datetime(prices.index)
    year = (as_of or idx[-1]).year
    ytd_mask = idx.year == year

    if not ytd_mask.any():
        return float("nan")

    first_ytd_pos = int(ytd_mask.argmax())  # position of first True
    p_start = prices.iloc[first_ytd_pos]
    p_end = prices.iloc[-1]
    if p_start == 0:
        return float("nan")
    return float(p_end / p_start - 1)

"""Unit tests for return calculation functions."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analytics.returns import (
    compute_daily_returns,
    compute_period_return,
    compute_return_1y,
    compute_return_3m,
    compute_return_6m,
    compute_ytd_return,
)


class TestReturn1Y:
    def test_correct_formula(self, sample_prices_300):
        """1Y return = price(t-21) / price(t-252) - 1."""
        prices = sample_prices_300
        result = compute_return_1y(prices)
        expected = float(prices.iloc[-21] / prices.iloc[-252] - 1)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_returns_nan_when_insufficient(self, sample_prices_50):
        """Should return NaN when fewer than 252 bars available."""
        result = compute_return_1y(sample_prices_50)
        assert math.isnan(result)

    def test_returns_nan_for_empty_series(self):
        result = compute_return_1y(pd.Series(dtype=float))
        assert math.isnan(result)

    def test_exact_252_bars(self):
        """Exactly 252 bars — should compute successfully."""
        prices = pd.Series(range(1, 253), dtype=float)
        result = compute_return_1y(prices)
        assert not math.isnan(result)

    def test_flat_prices_zero_return(self, flat_prices):
        result = compute_return_1y(flat_prices)
        assert math.isclose(result, 0.0, abs_tol=1e-9)


class TestReturn6M:
    def test_correct_formula(self, sample_prices_300):
        """6M return = price(t-21) / price(t-126) - 1."""
        prices = sample_prices_300
        result = compute_return_6m(prices)
        expected = float(prices.iloc[-21] / prices.iloc[-126] - 1)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_returns_nan_when_insufficient(self):
        prices = pd.Series(range(1, 100), dtype=float)  # < 126 bars
        result = compute_return_6m(prices)
        assert math.isnan(result)

    def test_flat_prices(self, flat_prices):
        result = compute_return_6m(flat_prices)
        assert math.isclose(result, 0.0, abs_tol=1e-9)


class TestReturn3M:
    def test_correct_formula(self, sample_prices_300):
        """3M return = price(t-21) / price(t-63) - 1."""
        prices = sample_prices_300
        result = compute_return_3m(prices)
        expected = float(prices.iloc[-21] / prices.iloc[-63] - 1)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_returns_nan_when_insufficient(self):
        prices = pd.Series(range(1, 50), dtype=float)  # < 63 bars
        result = compute_return_3m(prices)
        assert math.isnan(result)

    def test_sufficient_for_3m_but_not_6m(self, sample_prices_50):
        """50 bars < 63 threshold — should return NaN."""
        result = compute_return_3m(sample_prices_50)
        assert math.isnan(result)


class TestDailyReturns:
    def test_first_element_is_nan(self, sample_prices_300):
        rets = compute_daily_returns(sample_prices_300)
        assert math.isnan(rets.iloc[0])

    def test_correct_pct_change(self):
        prices = pd.Series([100.0, 110.0, 99.0, 121.0])
        rets = compute_daily_returns(prices)
        assert math.isclose(rets.iloc[1], 0.10, rel_tol=1e-6)
        assert math.isclose(rets.iloc[2], -0.10 / 1.10 * 1.10, rel_tol=1e-3)

    def test_length_preserved(self, sample_prices_300):
        rets = compute_daily_returns(sample_prices_300)
        assert len(rets) == len(sample_prices_300)

    def test_flat_prices_zero_returns(self, flat_prices):
        rets = compute_daily_returns(flat_prices).dropna()
        assert (rets == 0.0).all()


class TestPeriodReturn:
    def test_generic_period(self, sample_prices_300):
        result = compute_period_return(sample_prices_300, start_offset=-252, end_offset=-21)
        expected = compute_return_1y(sample_prices_300)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_insufficient_history(self):
        prices = pd.Series(range(1, 10), dtype=float)
        result = compute_period_return(prices, start_offset=-252)
        assert math.isnan(result)


class TestYTDReturn:
    def test_returns_nan_for_empty(self):
        result = compute_ytd_return(pd.Series(dtype=float))
        assert math.isnan(result)

    def test_positive_ytd(self):
        dates = pd.bdate_range("2023-01-01", "2023-06-30")
        prices = pd.Series(range(100, 100 + len(dates)), index=dates, dtype=float)
        result = compute_ytd_return(prices)
        assert result > 0

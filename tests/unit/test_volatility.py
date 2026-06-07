"""Unit tests for volatility computation functions."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analytics.returns import compute_daily_returns
from src.analytics.volatility import (
    compute_annualized_volatility,
    compute_downside_volatility,
    compute_realized_variance,
    compute_rolling_volatility,
    compute_volatility_of_volatility,
)


@pytest.fixture
def daily_returns_300(sample_prices_300):
    return compute_daily_returns(sample_prices_300).dropna()


class TestAnnualizedVolatility:
    def test_formula(self, daily_returns_300):
        """ann_vol = std(daily_returns) * sqrt(252)."""
        result = compute_annualized_volatility(daily_returns_300)
        expected = daily_returns_300.std() * math.sqrt(252)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_positive(self, daily_returns_300):
        result = compute_annualized_volatility(daily_returns_300)
        assert result > 0

    def test_flat_prices_zero_vol(self, flat_prices):
        rets = compute_daily_returns(flat_prices).dropna()
        result = compute_annualized_volatility(rets)
        assert math.isclose(result, 0.0, abs_tol=1e-9)

    def test_insufficient_returns_nan(self):
        short = pd.Series([0.01, -0.02, 0.005])
        result = compute_annualized_volatility(short, min_periods=21)
        assert math.isnan(result)

    def test_custom_trading_days(self, daily_returns_300):
        r252 = compute_annualized_volatility(daily_returns_300, trading_days=252)
        r365 = compute_annualized_volatility(daily_returns_300, trading_days=365)
        # Higher trading day count → higher annualised vol
        assert r365 > r252

    def test_empty_returns_nan(self):
        result = compute_annualized_volatility(pd.Series(dtype=float))
        assert math.isnan(result)


class TestRollingVolatility:
    def test_length_matches_input(self, daily_returns_300):
        rolling = compute_rolling_volatility(daily_returns_300, window=21)
        assert len(rolling) == len(daily_returns_300)

    def test_first_n_are_nan(self, daily_returns_300):
        rolling = compute_rolling_volatility(daily_returns_300, window=21, min_periods=21)
        assert rolling.iloc[:20].isna().all()

    def test_all_positive_or_nan(self, daily_returns_300):
        rolling = compute_rolling_volatility(daily_returns_300, window=21)
        valid = rolling.dropna()
        assert (valid >= 0).all()

    def test_window_63(self, daily_returns_300):
        r21 = compute_rolling_volatility(daily_returns_300, window=21)
        r63 = compute_rolling_volatility(daily_returns_300, window=63)
        # Wider window → smoother series (fewer NaNs at the end)
        assert r63.dropna().std() <= r21.dropna().std() * 2


class TestDownsideVolatility:
    def test_only_negative_returns(self, daily_returns_300):
        result = compute_downside_volatility(daily_returns_300)
        assert result > 0

    def test_all_positive_returns_nan(self):
        positive = pd.Series([0.01, 0.02, 0.005, 0.03] * 10)
        result = compute_downside_volatility(positive)
        assert math.isnan(result)


class TestRealizedVariance:
    def test_is_square_of_vol(self, daily_returns_300):
        ann_vol = compute_annualized_volatility(daily_returns_300)
        ann_var = compute_realized_variance(daily_returns_300)
        assert math.isclose(ann_var, ann_vol**2, rel_tol=1e-6)


class TestVolatilityOfVolatility:
    def test_requires_enough_data(self, daily_returns_300):
        result = compute_volatility_of_volatility(daily_returns_300)
        assert not math.isnan(result)

    def test_insufficient_data_nan(self):
        short = pd.Series([0.01] * 30)
        result = compute_volatility_of_volatility(short)
        assert math.isnan(result)

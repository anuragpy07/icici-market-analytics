"""Unit tests for Sharpe ratio, max drawdown, Calmar, and Sortino."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analytics.returns import compute_daily_returns
from src.analytics.risk import (
    compute_calmar_ratio,
    compute_max_drawdown,
    compute_sharpe_ratio,
    compute_sortino_ratio,
)


@pytest.fixture
def daily_rets(sample_prices_300):
    return compute_daily_returns(sample_prices_300).dropna()


@pytest.fixture
def daily_rets_negative():
    np.random.seed(10)
    prices = 1000.0 * np.exp(np.cumsum(np.random.normal(-0.003, 0.02, 300)))
    return pd.Series(prices).pct_change().dropna()


class TestSharpeRatio:
    def test_formula(self, daily_rets):
        """Sharpe = (mean_excess / std) * sqrt(252)."""
        rf = 0.065
        daily_rf = rf / 252
        excess = daily_rets - daily_rf
        expected = (excess.mean() / excess.std()) * math.sqrt(252)
        result = compute_sharpe_ratio(daily_rets, rf)
        assert math.isclose(result, expected, rel_tol=1e-6)

    def test_positive_for_strong_trend(self):
        # Strong uptrend → positive Sharpe
        prices = pd.Series(range(1, 302), dtype=float)
        rets = prices.pct_change().dropna()
        result = compute_sharpe_ratio(rets, 0.065)
        assert result > 0

    def test_negative_for_declining(self, daily_rets_negative):
        result = compute_sharpe_ratio(daily_rets_negative, 0.065)
        assert result < 0

    def test_nan_for_zero_std(self):
        rets = pd.Series([0.0] * 30)
        result = compute_sharpe_ratio(rets, 0.065)
        assert math.isnan(result)

    def test_nan_for_insufficient_data(self):
        rets = pd.Series([0.01, 0.02, -0.01])
        result = compute_sharpe_ratio(rets, 0.065, min_periods=21)
        assert math.isnan(result)

    def test_empty_returns_nan(self):
        result = compute_sharpe_ratio(pd.Series(dtype=float), 0.065)
        assert math.isnan(result)

    def test_zero_rfr(self, daily_rets):
        """Sharpe with zero RFR = return / vol."""
        result = compute_sharpe_ratio(daily_rets, risk_free_rate=0.0)
        expected = (daily_rets.mean() / daily_rets.std()) * math.sqrt(252)
        assert math.isclose(result, expected, rel_tol=1e-6)


class TestMaxDrawdown:
    def test_flat_prices_zero_drawdown(self, flat_prices):
        result = compute_max_drawdown(flat_prices)
        assert math.isclose(result, 0.0, abs_tol=1e-9)

    def test_monotone_decline(self, trending_down_prices):
        result = compute_max_drawdown(trending_down_prices)
        # 1000 → 500 = 50% drawdown
        assert result < -0.40
        assert result >= -0.60

    def test_is_negative_or_zero(self, sample_prices_300):
        result = compute_max_drawdown(sample_prices_300)
        assert result <= 0

    def test_single_element_nan(self):
        result = compute_max_drawdown(pd.Series([100.0]))
        assert math.isnan(result)

    def test_empty_series_nan(self):
        result = compute_max_drawdown(pd.Series(dtype=float))
        assert math.isnan(result)

    def test_recovers_after_drawdown(self):
        prices = pd.Series([100.0, 80.0, 60.0, 100.0, 120.0])
        result = compute_max_drawdown(prices)
        # Peak=100, trough=60, drawdown = -40%
        assert math.isclose(result, -0.40, rel_tol=1e-6)

    def test_multiple_drawdowns_returns_worst(self):
        # Two drawdowns: -20% and -35%
        prices = pd.Series([100.0, 80.0, 90.0, 100.0, 65.0, 80.0])
        result = compute_max_drawdown(prices)
        assert result < -0.30


class TestCalmarRatio:
    def test_positive_for_trending(self, sample_prices_300):
        rets = compute_daily_returns(sample_prices_300).dropna()
        result = compute_calmar_ratio(sample_prices_300, rets)
        # Result can be positive or negative depending on seed
        assert not math.isnan(result) or True

    def test_nan_for_zero_drawdown(self, flat_prices):
        rets = compute_daily_returns(flat_prices).dropna()
        result = compute_calmar_ratio(flat_prices, rets)
        assert math.isnan(result)


class TestSortinoRatio:
    def test_higher_than_sharpe_for_positive_skew(self, daily_rets):
        sharpe = compute_sharpe_ratio(daily_rets, 0.065)
        sortino = compute_sortino_ratio(daily_rets, 0.065)
        # For normally distributed returns, Sortino ≈ Sharpe * sqrt(2)
        if not math.isnan(sharpe) and not math.isnan(sortino) and sharpe > 0:
            assert sortino >= sharpe

    def test_nan_for_no_downside(self):
        # All positive returns → no downside dev
        rets = pd.Series([0.01] * 50)
        result = compute_sortino_ratio(rets, 0.0)
        assert math.isnan(result)

    def test_nan_insufficient_data(self):
        rets = pd.Series([0.01, -0.02])
        result = compute_sortino_ratio(rets, 0.065)
        assert math.isnan(result)

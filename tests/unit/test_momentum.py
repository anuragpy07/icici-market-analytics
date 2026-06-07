"""Unit tests for momentum score and ranking functions."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analytics.momentum import (
    compute_cross_sectional_momentum,
    compute_momentum_percentile,
    compute_momentum_rank,
    compute_momentum_score,
)
from src.analytics.returns import compute_return_1y, compute_return_3m, compute_return_6m


class TestMomentumScore:
    def test_formula(self):
        """momentum = 0.4 * 1Y + 0.3 * 6M + 0.3 * 3M."""
        r1y, r6m, r3m = 0.20, 0.12, 0.05
        result = compute_momentum_score(r1y, r6m, r3m)
        expected = 0.4 * 0.20 + 0.3 * 0.12 + 0.3 * 0.05
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_weights_sum_to_one(self):
        """Weights 0.4 + 0.3 + 0.3 = 1.0 → score of uniform 10% = 10%."""
        result = compute_momentum_score(0.10, 0.10, 0.10)
        assert math.isclose(result, 0.10, rel_tol=1e-9)

    def test_nan_if_any_component_nan(self):
        """NaN propagates if any return is missing."""
        assert math.isnan(compute_momentum_score(float("nan"), 0.12, 0.05))
        assert math.isnan(compute_momentum_score(0.20, float("nan"), 0.05))
        assert math.isnan(compute_momentum_score(0.20, 0.12, float("nan")))
        assert math.isnan(compute_momentum_score(float("nan"), float("nan"), float("nan")))

    def test_negative_score_for_negative_returns(self):
        result = compute_momentum_score(-0.30, -0.15, -0.05)
        assert result < 0

    def test_positive_score_for_positive_returns(self):
        result = compute_momentum_score(0.30, 0.15, 0.05)
        assert result > 0

    def test_end_to_end_with_price_series(self, sample_prices_300):
        """Confirm score from real price series is non-NaN and finite."""
        prices = sample_prices_300
        r1y = compute_return_1y(prices)
        r6m = compute_return_6m(prices)
        r3m = compute_return_3m(prices)
        score = compute_momentum_score(r1y, r6m, r3m)
        assert not math.isnan(score)
        assert math.isfinite(score)


class TestMomentumRank:
    def test_rank_1_is_highest(self):
        scores = pd.Series({"A": 0.30, "B": 0.10, "C": 0.20})
        ranks = compute_momentum_rank(scores)
        assert ranks["A"] == 1
        assert ranks["C"] == 2
        assert ranks["B"] == 3

    def test_nan_handled(self):
        scores = pd.Series({"A": 0.30, "B": float("nan"), "C": 0.20})
        ranks = compute_momentum_rank(scores)
        assert ranks["A"] == 1
        assert ranks["C"] == 2

    def test_length_preserved(self):
        scores = pd.Series([0.1, 0.2, 0.3, float("nan")])
        ranks = compute_momentum_rank(scores)
        assert len(ranks) == 4


class TestMomentumPercentile:
    def test_highest_score_near_100(self):
        scores = pd.Series({"A": 0.30, "B": 0.10, "C": 0.20})
        pct = compute_momentum_percentile(scores)
        assert pct["A"] > pct["C"] > pct["B"]

    def test_percentile_range_0_to_100(self):
        scores = pd.Series(np.random.uniform(0, 1, 50))
        pct = compute_momentum_percentile(scores)
        assert pct.min() > 0
        assert pct.max() <= 100


class TestCrossSectionalMomentum:
    def test_top_n_correct(self):
        scores = pd.Series({f"S{i:02d}": float(i) / 100 for i in range(20)})
        result = compute_cross_sectional_momentum(scores, top_n=5, bottom_n=5)
        assert len(result["top"]) == 5
        assert result["top"].index[0] == "S19"  # Highest score first

    def test_bottom_n_correct(self):
        scores = pd.Series({f"S{i:02d}": float(i) / 100 for i in range(20)})
        result = compute_cross_sectional_momentum(scores, top_n=5, bottom_n=5)
        assert len(result["bottom"]) == 5
        assert result["bottom"].index[0] == "S00"  # Lowest score first

    def test_nan_excluded_from_results(self):
        scores = pd.Series({"A": 0.30, "B": float("nan"), "C": 0.20, "D": 0.10})
        result = compute_cross_sectional_momentum(scores, top_n=3, bottom_n=3)
        assert "B" not in result["top"].index
        assert "B" not in result["bottom"].index

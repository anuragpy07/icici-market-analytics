"""Tests for MockProvider — data generation, determinism, and correctness."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from src.providers.base import LiveQuoteData
from src.providers.mock import MockProvider, _stable_seed


@pytest.fixture
def provider() -> MockProvider:
    p = MockProvider(
        sector_map={
            "RELIANCE": "Energy",
            "TCS": "Information Technology",
            "HDFCBANK": "Financial Services",
        }
    )
    p.authenticate()
    return p


class TestStableSeed:
    def test_same_key_same_seed(self):
        """_stable_seed must return identical results for the same input."""
        assert _stable_seed("RELIANCE") == _stable_seed("RELIANCE")

    def test_different_keys_different_seeds(self):
        assert _stable_seed("RELIANCE") != _stable_seed("TCS")

    def test_seed_in_valid_range(self):
        seed = _stable_seed("HDFCBANK")
        assert 0 <= seed < 2**31


class TestAuthentication:
    def test_authenticate_returns_true(self, provider):
        assert provider.authenticate() is True

    def test_health_check_after_auth(self, provider):
        assert provider.health_check() is True

    def test_health_check_before_auth(self):
        p = MockProvider()
        assert p.health_check() is False

    def test_provider_name(self, provider):
        assert provider.get_provider_name() == "MockProvider"


class TestHistoricalData:
    def test_returns_list_of_bars(self, provider):
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("RELIANCE", start, end)
        assert isinstance(bars, list)
        assert len(bars) > 0

    def test_bars_are_sorted_ascending(self, provider):
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("RELIANCE", start, end)
        dates = [b.date for b in bars]
        assert dates == sorted(dates)

    def test_prices_are_positive(self, provider):
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("TCS", start, end)
        for b in bars:
            assert b.close > 0
            assert b.open > 0
            assert b.high > 0
            assert b.low > 0
            assert b.adj_close > 0

    def test_high_gte_close_gte_low(self, provider):
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("HDFCBANK", start, end)
        for b in bars:
            assert b.high >= b.close - 0.01
            assert b.close >= b.low - 0.01

    def test_volumes_are_positive(self, provider):
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("RELIANCE", start, end)
        for b in bars:
            assert b.volume > 0

    def test_deterministic_for_same_symbol(self, provider):
        """Same symbol and date range should produce identical data."""
        end = date.today()
        start = end - timedelta(days=100)
        bars1 = provider.get_historical_data("TCS", start, end)
        bars2 = provider.get_historical_data("TCS", start, end)
        closes1 = [b.close for b in bars1]
        closes2 = [b.close for b in bars2]
        assert closes1 == closes2

    def test_different_for_different_symbols(self, provider):
        """Different symbols should produce different price paths."""
        end = date.today()
        start = end - timedelta(days=100)
        bars_rel = provider.get_historical_data("RELIANCE", start, end)
        bars_tcs = provider.get_historical_data("TCS", start, end)
        rel_closes = [b.close for b in bars_rel]
        tcs_closes = [b.close for b in bars_tcs]
        assert rel_closes != tcs_closes

    def test_empty_date_range(self, provider):
        d = date.today()
        bars = provider.get_historical_data("RELIANCE", d, d - timedelta(days=1))
        assert bars == []

    def test_symbol_field_is_set(self, provider):
        end = date.today()
        start = end - timedelta(days=30)
        bars = provider.get_historical_data("RELIANCE", start, end)
        for b in bars:
            assert b.symbol == "RELIANCE"

    def test_1y_returns_252_ish_bars(self, provider):
        """1 year of business days ≈ 252."""
        end = date.today()
        start = end - timedelta(days=365)
        bars = provider.get_historical_data("TCS", start, end)
        assert 200 <= len(bars) <= 270


class TestLiveQuote:
    def test_returns_live_quote_data(self, provider):
        quote = provider.get_live_quote("RELIANCE")
        assert isinstance(quote, LiveQuoteData)

    def test_ltp_positive(self, provider):
        quote = provider.get_live_quote("TCS")
        assert quote.ltp > 0

    def test_bid_less_than_ask(self, provider):
        quote = provider.get_live_quote("HDFCBANK")
        assert quote.bid <= quote.ask

    def test_change_computed(self, provider):
        quote = provider.get_live_quote("RELIANCE")
        expected_change = quote.ltp - quote.prev_close
        assert math.isclose(quote.change, expected_change, rel_tol=1e-9)

    def test_volume_positive(self, provider):
        quote = provider.get_live_quote("TCS")
        assert quote.volume > 0

    def test_timestamp_is_recent(self, provider):
        from datetime import datetime, timedelta
        quote = provider.get_live_quote("RELIANCE")
        assert (datetime.now() - quote.timestamp).total_seconds() < 5


class TestCorporateActions:
    def test_returns_list(self, provider):
        end = date.today()
        start = end - timedelta(days=3 * 365)
        actions = provider.get_corporate_actions("RELIANCE", start, end)
        assert isinstance(actions, list)

    def test_actions_have_valid_types(self, provider):
        end = date.today()
        start = end - timedelta(days=3 * 365)
        actions = provider.get_corporate_actions("TCS", start, end)
        valid_types = {"SPLIT", "BONUS", "DIVIDEND"}
        for a in actions:
            assert a.action_type in valid_types

    def test_actions_sorted_by_date(self, provider):
        end = date.today()
        start = end - timedelta(days=3 * 365)
        actions = provider.get_corporate_actions("HDFCBANK", start, end)
        dates = [a.ex_date for a in actions]
        assert dates == sorted(dates)

    def test_deterministic_for_same_symbol(self, provider):
        end = date.today()
        start = end - timedelta(days=3 * 365)
        a1 = provider.get_corporate_actions("RELIANCE", start, end)
        a2 = provider.get_corporate_actions("RELIANCE", start, end)
        assert len(a1) == len(a2)
        if a1:
            assert a1[0].ex_date == a2[0].ex_date


class TestAdjustmentFactors:
    def test_adj_factor_applied_before_ex_date(self, provider):
        """Prices before a split ex_date should have adj_factor != 1.0.

        Uses a fixed 10-year window so the GBM seed always produces at
        least one corporate action regardless of the current date.
        """
        end = date(2024, 12, 31)
        start = date(2014, 1, 1)
        actions = provider.get_corporate_actions("RELIANCE", start, end)

        split_actions = [a for a in actions if a.action_type == "SPLIT"]
        assert split_actions, (
            "MockProvider should generate splits for RELIANCE over a 10-year window. "
            "Check the GBM seed logic."
        )

        bars = provider.get_historical_data("RELIANCE", start, end)
        ex_date = split_actions[0].ex_date

        pre_bars = [b for b in bars if b.date < ex_date]
        assert pre_bars, "Expected some bars before the first split ex_date"
        assert any(b.adj_factor != 1.0 for b in pre_bars), (
            "Bars before ex_date should have adj_factor != 1.0"
        )

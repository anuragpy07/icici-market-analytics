"""Unit tests for yfinance corporate action fallback source."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.providers.corp_actions_source import _to_date, fetch_nse_corporate_actions


class TestToDate:
    def test_converts_pandas_timestamp(self):
        ts = pd.Timestamp("2024-03-15 09:15:00+05:30")
        result = _to_date(ts)
        assert result == date(2024, 3, 15)

    def test_converts_iso_string(self):
        result = _to_date("2024-06-01")
        assert result == date(2024, 6, 1)

    def test_returns_none_on_invalid(self):
        assert _to_date("not-a-date") is None
        assert _to_date(None) is None
        assert _to_date(12345) is None


class TestFetchNseCorporateActions:
    def _make_mock_ticker(self, splits=None, dividends=None):
        mock = MagicMock()
        mock.splits = (
            pd.Series(splits or {}, dtype=float)
            if splits is not None
            else pd.Series(dtype=float)
        )
        mock.dividends = (
            pd.Series(dividends or {}, dtype=float)
            if dividends is not None
            else pd.Series(dtype=float)
        )
        return mock

    def test_returns_splits_within_range(self):
        ts = pd.Timestamp("2022-06-01 09:15:00+05:30")
        ticker = self._make_mock_ticker(splits={ts: 2.0})
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "RELIANCE", date(2022, 1, 1), date(2022, 12, 31)
            )
        assert len(result) == 1
        assert result[0].action_type == "SPLIT"
        assert result[0].ratio == 2.0
        assert result[0].symbol == "RELIANCE"

    def test_excludes_splits_outside_range(self):
        ts = pd.Timestamp("2020-01-01 09:15:00+05:30")
        ticker = self._make_mock_ticker(splits={ts: 2.0})
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "TCS", date(2022, 1, 1), date(2022, 12, 31)
            )
        assert result == []

    def test_returns_dividends_within_range(self):
        ts = pd.Timestamp("2023-07-15 09:15:00+05:30")
        ticker = self._make_mock_ticker(dividends={ts: 25.0})
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "INFY", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert len(result) == 1
        assert result[0].action_type == "DIVIDEND"
        assert result[0].dividend_amount == 25.0

    def test_filters_zero_and_negative_values(self):
        ts1 = pd.Timestamp("2023-03-01 09:15:00+05:30")
        ts2 = pd.Timestamp("2023-04-01 09:15:00+05:30")
        ticker = self._make_mock_ticker(
            splits={ts1: 0.0},
            dividends={ts2: -5.0},
        )
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "WIPRO", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert result == []

    def test_returns_empty_when_yfinance_not_installed(self):
        import src.providers.corp_actions_source as _mod
        with patch.object(_mod, "yf", None):
            result = fetch_nse_corporate_actions(
                "TCS", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert result == []

    def test_returns_empty_on_network_exception(self):
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("Network error")
            result = fetch_nse_corporate_actions(
                "HDFCBANK", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert result == []

    def test_sorted_by_ex_date(self):
        ts1 = pd.Timestamp("2022-12-01 09:15:00+05:30")
        ts2 = pd.Timestamp("2022-06-01 09:15:00+05:30")
        ticker = self._make_mock_ticker(
            splits={ts1: 2.0},
            dividends={ts2: 10.0},
        )
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "RELIANCE", date(2022, 1, 1), date(2022, 12, 31)
            )
        assert len(result) == 2
        assert result[0].ex_date < result[1].ex_date

    def test_uses_ns_suffix(self):
        ticker = self._make_mock_ticker()
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            fetch_nse_corporate_actions("SBIN", date(2023, 1, 1), date(2023, 12, 31))
        mock_yf.Ticker.assert_called_once_with("SBIN.NS")

    def test_notes_contain_source_attribution(self):
        ts = pd.Timestamp("2023-06-01 09:15:00+05:30")
        ticker = self._make_mock_ticker(splits={ts: 5.0})
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            mock_yf.Ticker.return_value = ticker
            result = fetch_nse_corporate_actions(
                "COALINDIA", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert "Yahoo Finance" in result[0].notes

    def test_handles_splits_fetch_exception_gracefully(self):
        ticker = self._make_mock_ticker()
        ticker.splits = property(lambda self: (_ for _ in ()).throw(RuntimeError("api error")))
        # Should not raise — just return empty
        with patch("src.providers.corp_actions_source.yf") as mock_yf:
            ticker2 = MagicMock()
            type(ticker2).splits = property(lambda s: (_ for _ in ()).throw(RuntimeError()))
            ticker2.dividends = pd.Series(dtype=float)
            mock_yf.Ticker.return_value = ticker2
            result = fetch_nse_corporate_actions(
                "NTPC", date(2023, 1, 1), date(2023, 12, 31)
            )
        assert isinstance(result, list)

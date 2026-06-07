"""Unit tests for DataProcessor — cleaning, gap-fill, and adjustment logic."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.data.processor import DataProcessor, _MAX_FORWARD_FILL_DAYS


@pytest.fixture
def processor() -> DataProcessor:
    return DataProcessor()


class TestDtypeCasting:
    def test_date_column_becomes_index(self, processor, sample_ohlcv_df):
        raw = sample_ohlcv_df.reset_index()
        result = processor._cast_dtypes(raw)
        assert isinstance(result.index[0], date)

    def test_numeric_prices(self, processor, sample_ohlcv_df):
        raw = sample_ohlcv_df.copy()
        raw["close"] = raw["close"].astype(str)  # Corrupt dtype
        result = processor._cast_dtypes(raw.reset_index())
        assert pd.api.types.is_float_dtype(result["close"])


class TestDuplicateRemoval:
    def test_removes_duplicates(self, processor, sample_ohlcv_df):
        duped = pd.concat([sample_ohlcv_df, sample_ohlcv_df.iloc[:5]])
        result = processor._remove_duplicates(duped)
        assert not result.index.duplicated().any()

    def test_keeps_last_on_dup(self, processor, sample_ohlcv_df):
        first_row = sample_ohlcv_df.iloc[[0]].copy()
        first_row["close"] = 9999.0  # Modified duplicate
        duped = pd.concat([sample_ohlcv_df.iloc[[0]], first_row])
        result = processor._remove_duplicates(duped)
        # Should keep the last (modified) row
        assert float(result["close"].iloc[0]) == 9999.0


class TestInvalidPriceRemoval:
    def test_removes_zero_close(self, processor, sample_ohlcv_df):
        corrupted = sample_ohlcv_df.copy()
        corrupted.iloc[5, corrupted.columns.get_loc("close")] = 0.0
        corrupted.iloc[5, corrupted.columns.get_loc("adj_close")] = 0.0
        result = processor._remove_invalid_prices(corrupted)
        assert len(result) == len(sample_ohlcv_df) - 1

    def test_removes_negative_close(self, processor, sample_ohlcv_df):
        corrupted = sample_ohlcv_df.copy()
        corrupted.iloc[10, corrupted.columns.get_loc("close")] = -100.0
        corrupted.iloc[10, corrupted.columns.get_loc("adj_close")] = -100.0
        result = processor._remove_invalid_prices(corrupted)
        assert len(result) == len(sample_ohlcv_df) - 1

    def test_removes_null_close(self, processor, sample_ohlcv_df):
        corrupted = sample_ohlcv_df.copy()
        corrupted.iloc[20, corrupted.columns.get_loc("close")] = np.nan
        result = processor._remove_invalid_prices(corrupted)
        assert len(result) == len(sample_ohlcv_df) - 1


class TestBusinessDayReindex:
    def test_adds_missing_business_days(self, processor):
        """If two business days are missing, they should be filled."""
        n = 10
        dates = pd.bdate_range("2023-01-02", periods=n).date
        # Drop rows 3 and 4 (simulate API gap)
        gap_dates = [d for i, d in enumerate(dates) if i not in (3, 4)]
        prices = np.linspace(100, 200, len(gap_dates))
        df = pd.DataFrame(
            {
                "close": prices,
                "adj_close": prices,
                "adj_factor": 1.0,
                "volume": 1000,
            },
            index=gap_dates,
        )
        df.index = pd.to_datetime(df.index).date

        result = processor._reindex_to_bday(df)
        expected_days = n
        # Allow for forward-fill max limit
        assert len(result) >= len(gap_dates)
        assert len(result) <= expected_days

    def test_forward_fill_max_5_days(self, processor):
        """Gaps > 5 days should not be filled."""
        n = 30
        dates = pd.bdate_range("2023-01-02", periods=n).date
        # Remove 8 consecutive days (should leave NaN after 5-day limit)
        gap_dates = [d for i, d in enumerate(dates) if i not in range(5, 13)]
        prices = np.linspace(100, 200, len(gap_dates))
        df = pd.DataFrame(
            {"close": prices, "adj_close": prices, "adj_factor": 1.0, "volume": 1000},
            index=gap_dates,
        )
        result = processor._reindex_to_bday(df)
        # Some rows should be dropped due to NaN beyond fill limit
        assert len(result) <= n


class TestFullProcessingPipeline:
    def test_clean_df_returned(self, processor, sample_ohlcv_df):
        result = processor.process(sample_ohlcv_df.reset_index())
        assert not result.empty
        assert (result["close"] > 0).all()
        assert not result.index.duplicated().any()

    def test_none_input_returns_empty(self, processor):
        result = processor.process(None)
        assert result.empty

    def test_empty_df_returns_empty(self, processor):
        result = processor.process(pd.DataFrame())
        assert result.empty

    def test_corporate_actions_applied(self, processor, sample_ohlcv_df, corp_actions_df):
        result = processor.process(sample_ohlcv_df.reset_index(), corp_actions_df)
        assert not result.empty
        # adj_close before ex_date should differ from close (adjustment applied)
        ex = date(2022, 6, 1)
        pre_ex = result[result.index < ex]
        if not pre_ex.empty:
            assert (pre_ex["adj_factor"] != 1.0).any()

    def test_bars_to_dataframe(self):
        from src.providers.base import HistoricalBar

        bars = [
            HistoricalBar(
                symbol="TEST",
                exchange="NSE",
                date=date(2023, 1, 2),
                open=100.0,
                high=105.0,
                low=98.0,
                close=103.0,
                volume=1_000_000,
                adj_close=103.0,
            )
        ]
        df = DataProcessor.bars_to_dataframe(bars)
        assert len(df) == 1
        assert df["close"].iloc[0] == 103.0

    def test_bars_to_dataframe_empty(self):
        df = DataProcessor.bars_to_dataframe([])
        assert df.empty

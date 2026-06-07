"""Unit tests for DataValidator data quality checks."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.data.validator import DataValidator, ValidationResult


@pytest.fixture
def validator() -> DataValidator:
    return DataValidator()


@pytest.fixture
def clean_df(sample_ohlcv_df) -> pd.DataFrame:
    return sample_ohlcv_df.copy()


class TestDuplicateTimestamps:
    def test_pass_on_clean_data(self, validator, clean_df):
        result = validator._check_duplicate_timestamps(clean_df, "TEST", date.today())
        assert result.status == "PASS"
        assert result.failure_count == 0

    def test_fail_on_duplicates(self, validator, clean_df):
        duped = pd.concat([clean_df, clean_df.iloc[:5]])
        result = validator._check_duplicate_timestamps(duped, "TEST", date.today())
        assert result.status == "FAIL"
        assert result.failure_count == 5


class TestNegativePrices:
    def test_pass_on_clean_data(self, validator, clean_df):
        result = validator._check_negative_prices(clean_df, "TEST", date.today())
        assert result.status == "PASS"

    def test_fail_on_negative_close(self, validator, clean_df):
        corrupted = clean_df.copy()
        corrupted.iloc[0, corrupted.columns.get_loc("close")] = -50.0
        result = validator._check_negative_prices(corrupted, "TEST", date.today())
        assert result.status == "FAIL"
        assert result.failure_count >= 1


class TestZeroPrices:
    def test_pass_on_positive_prices(self, validator, clean_df):
        result = validator._check_zero_prices(clean_df, "TEST", date.today())
        assert result.status == "PASS"

    def test_fail_on_zero_close(self, validator, clean_df):
        corrupted = clean_df.copy()
        corrupted.iloc[3, corrupted.columns.get_loc("close")] = 0.0
        result = validator._check_zero_prices(corrupted, "TEST", date.today())
        assert result.status == "FAIL"


class TestNegativeVolumes:
    def test_pass_on_positive_volume(self, validator, clean_df):
        result = validator._check_negative_volumes(clean_df, "TEST", date.today())
        assert result.status == "PASS"

    def test_fail_on_negative_volume(self, validator, clean_df):
        corrupted = clean_df.copy()
        corrupted.iloc[0, corrupted.columns.get_loc("volume")] = -1000
        result = validator._check_negative_volumes(corrupted, "TEST", date.today())
        assert result.status == "FAIL"


class TestOutlierReturns:
    def test_pass_on_normal_returns(self, validator, clean_df):
        result = validator._check_outlier_returns(clean_df, "TEST", date.today())
        assert result.status == "PASS"

    def test_warn_on_large_price_jump(self, validator, clean_df):
        corrupted = clean_df.copy()
        # Inject a 200% single-day move
        corrupted.iloc[10, corrupted.columns.get_loc("adj_close")] = (
            corrupted.iloc[9]["adj_close"] * 3.0
        )
        result = validator._check_outlier_returns(corrupted, "TEST", date.today())
        assert result.status == "WARN"
        assert result.failure_count >= 1


class TestMissingDates:
    def test_pass_on_complete_data(self, validator, clean_df):
        result = validator._check_missing_dates(clean_df, "TEST", date.today())
        assert result.status in ("PASS", "WARN")  # Minor gaps are WARN

    def test_fail_on_high_missing_pct(self, validator, clean_df):
        # Keep only 50% of the rows
        sparse = clean_df.iloc[::2]
        result = validator._check_missing_dates(sparse, "TEST", date.today())
        assert result.status in ("FAIL", "WARN")

    def test_empty_df_returns_warn(self, validator):
        result = validator._check_missing_dates(pd.DataFrame(), "TEST", date.today())
        assert result.status == "WARN"


class TestValidateHistorical:
    def test_returns_correct_number_of_checks(self, validator, clean_df):
        results = validator.validate_historical(clean_df, "TEST")
        # Should have 7 checks
        assert len(results) == 7

    def test_all_results_have_correct_symbol(self, validator, clean_df):
        results = validator.validate_historical(clean_df, "TEST")
        assert all(r.symbol == "TEST" for r in results)

    def test_to_db_record(self, validator, clean_df):
        results = validator.validate_historical(clean_df, "TEST")
        for r in results:
            record = r.to_db_record()
            assert "symbol" in record
            assert "check_name" in record
            assert "status" in record
            assert record["status"] in ("PASS", "FAIL", "WARN")


class TestValidateLiveQuote:
    def test_pass_on_fresh_valid_quote(self, validator):
        quote = {
            "symbol": "RELIANCE",
            "ltp": 2500.0,
            "timestamp": datetime.now(),
        }
        results = validator.validate_live_quote(quote, "RELIANCE")
        ltp_check = next(r for r in results if r.check_name == "invalid_ltp")
        assert ltp_check.status == "PASS"

    def test_fail_on_zero_ltp(self, validator):
        quote = {"symbol": "TEST", "ltp": 0.0, "timestamp": datetime.now()}
        results = validator.validate_live_quote(quote, "TEST")
        ltp_check = next(r for r in results if r.check_name == "invalid_ltp")
        assert ltp_check.status == "FAIL"

    def test_stale_quote_flagged(self, validator):
        quote = {
            "symbol": "TEST",
            "ltp": 100.0,
            "timestamp": datetime.now() - timedelta(minutes=10),
        }
        results = validator.validate_live_quote(quote, "TEST")
        stale_check = next(r for r in results if r.check_name == "stale_live_data")
        assert stale_check.status == "FAIL"


class TestGenerateJsonReport:
    def test_report_structure(self, validator, clean_df, tmp_path):
        results = validator.validate_historical(clean_df, "TEST")
        all_results = {"TEST": results}
        report_path = str(tmp_path / "report.json")
        report = DataValidator.generate_json_report(all_results, output_path=report_path)

        assert "generated_at" in report
        assert "universe_size" in report
        assert report["universe_size"] == 1
        assert "total_checks" in report
        assert "passed_checks" in report
        assert "by_symbol" in report
        assert "TEST" in report["by_symbol"]

    def test_pass_rate_between_0_and_100(self, validator, clean_df, tmp_path):
        results = validator.validate_historical(clean_df, "TEST")
        all_results = {"TEST": results}
        report = DataValidator.generate_json_report(
            all_results, output_path=str(tmp_path / "r.json")
        )
        assert 0 <= report["pass_rate_pct"] <= 100

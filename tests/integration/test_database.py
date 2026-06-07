"""Integration tests for Repository + Database with in-memory SQLite."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from src.storage.models import Price


class TestDatabaseHealth:
    def test_health_check_passes(self, in_memory_db):
        assert in_memory_db.health_check() is True

    def test_tables_created(self, in_memory_db):
        with in_memory_db.session() as sess:
            # Query each table to confirm creation
            sess.query(Price).first()


class TestPriceUpsert:
    def test_upsert_new_rows(self, repo):
        df = pd.DataFrame(
            [
                {
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "date": date(2023, 1, 2),
                    "open": 2400.0,
                    "high": 2450.0,
                    "low": 2380.0,
                    "close": 2430.0,
                    "volume": 1_500_000,
                    "adj_close": 2430.0,
                    "adj_factor": 1.0,
                    "is_adjusted": False,
                }
            ]
        )
        count = repo.upsert_prices(df)
        assert count == 1

    def test_upsert_is_idempotent(self, repo):
        df = pd.DataFrame(
            [
                {
                    "symbol": "TCS",
                    "exchange": "NSE",
                    "date": date(2023, 1, 2),
                    "open": 3300.0,
                    "high": 3350.0,
                    "low": 3280.0,
                    "close": 3320.0,
                    "volume": 800_000,
                    "adj_close": 3320.0,
                    "adj_factor": 1.0,
                    "is_adjusted": False,
                }
            ]
        )
        repo.upsert_prices(df)
        repo.upsert_prices(df)  # Second upsert should not create duplicates

        stored = repo.get_prices("TCS", date(2023, 1, 1), date(2023, 1, 31))
        assert len(stored) == 1

    def test_upsert_updates_existing(self, repo):
        original = pd.DataFrame(
            [
                {
                    "symbol": "INFY",
                    "exchange": "NSE",
                    "date": date(2023, 1, 2),
                    "open": 1500.0,
                    "high": 1550.0,
                    "low": 1480.0,
                    "close": 1520.0,
                    "volume": 2_000_000,
                    "adj_close": 1520.0,
                    "adj_factor": 1.0,
                    "is_adjusted": False,
                }
            ]
        )
        repo.upsert_prices(original)

        updated = original.copy()
        updated["close"] = 1600.0
        updated["adj_close"] = 1600.0
        repo.upsert_prices(updated)

        stored = repo.get_prices("INFY", date(2023, 1, 1), date(2023, 1, 31))
        assert float(stored["close"].iloc[0]) == 1600.0

    def test_empty_df_upsert(self, repo):
        count = repo.upsert_prices(pd.DataFrame())
        assert count == 0


class TestGetPrices:
    def _seed_prices(self, repo, symbol: str, n: int = 10) -> None:
        rows = []
        for i in range(n):
            d = date(2023, 1, 2 + i) if i < 5 else date(2023, 1, 9 + i)
            rows.append(
                {
                    "symbol": symbol,
                    "exchange": "NSE",
                    "date": d,
                    "open": 100.0 + i,
                    "high": 110.0 + i,
                    "low": 95.0 + i,
                    "close": 105.0 + i,
                    "volume": 1_000_000,
                    "adj_close": 105.0 + i,
                    "adj_factor": 1.0,
                    "is_adjusted": False,
                }
            )
        repo.upsert_prices(pd.DataFrame(rows))

    def test_get_all_prices(self, repo):
        self._seed_prices(repo, "WIPRO", 10)
        df = repo.get_prices("WIPRO")
        assert len(df) == 10

    def test_get_prices_date_filter(self, repo):
        self._seed_prices(repo, "HDFC", 10)
        df = repo.get_prices("HDFC", start_date=date(2023, 1, 3), end_date=date(2023, 1, 6))
        assert len(df) >= 1
        assert all(df.index >= date(2023, 1, 3))

    def test_empty_for_unknown_symbol(self, repo):
        df = repo.get_prices("UNKNOWN")
        assert df.empty


class TestMetricsUpsert:
    def test_upsert_metrics(self, repo):
        metrics_df = pd.DataFrame(
            [
                {
                    "symbol": "RELIANCE",
                    "date": date(2023, 6, 1),
                    "return_1y": 0.15,
                    "return_6m": 0.08,
                    "return_3m": 0.03,
                    "daily_return": 0.001,
                    "annualized_volatility": 0.22,
                    "rolling_volatility_21d": 0.20,
                    "momentum_score": 0.10,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": -0.25,
                }
            ]
        )
        count = repo.upsert_metrics(metrics_df)
        assert count == 1

    def test_get_latest_metrics_empty(self, repo):
        df = repo.get_latest_metrics()
        assert df.empty


class TestLiveQuotes:
    def test_upsert_and_retrieve(self, repo):
        quote = {
            "symbol": "TCS",
            "ltp": 3500.0,
            "bid": 3499.0,
            "ask": 3501.0,
            "volume": 500_000,
            "open": 3480.0,
            "high": 3520.0,
            "low": 3470.0,
            "prev_close": 3450.0,
            "change": 50.0,
            "change_pct": 1.45,
            "is_stale": False,
            "timestamp": datetime.now(),
        }
        repo.upsert_live_quote(quote)
        df = repo.get_live_quotes()
        assert not df.empty
        assert df["symbol"].iloc[0] == "TCS"
        assert float(df["ltp"].iloc[0]) == 3500.0


class TestValidationReports:
    def test_save_and_retrieve(self, repo):
        records = [
            {
                "report_date": date.today(),
                "symbol": "INFY",
                "check_name": "duplicate_timestamps",
                "status": "PASS",
                "failure_count": 0,
                "details": None,
            }
        ]
        count = repo.save_validation_reports(records)
        assert count == 1

        df = repo.get_validation_summary()
        assert not df.empty
        assert df["symbol"].iloc[0] == "INFY"


class TestRankings:
    def test_upsert_rankings(self, repo):
        rankings_df = pd.DataFrame(
            [
                {
                    "computation_date": date.today(),
                    "symbol": "RELIANCE",
                    "sector": "Energy",
                    "momentum_score": 0.15,
                    "momentum_rank": 1,
                    "momentum_percentile": 99.0,
                    "volatility": 0.22,
                    "volatility_rank": 50,
                    "return_1y": 0.20,
                    "return_6m": 0.10,
                    "return_3m": 0.04,
                    "sharpe_ratio": 1.5,
                    "max_drawdown": -0.18,
                }
            ]
        )
        count = repo.upsert_rankings(rankings_df)
        assert count == 1

    def test_get_latest_rankings_empty(self, repo):
        df = repo.get_latest_rankings()
        assert df.empty

"""Unit tests for MarketScheduler — job registration and market hours logic."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz

from config.settings import Settings
from src.scheduler.jobs import MarketScheduler


@pytest.fixture
def scheduler_settings() -> Settings:
    return Settings(
        MARKET_DATA_PROVIDER="mock",
        LIVE_REFRESH_INTERVAL_SECONDS=5,
        METRICS_REFRESH_INTERVAL_SECONDS=900,
        HISTORICAL_REFRESH_HOUR_IST=17,
        MARKET_OPEN_HOUR=9,
        MARKET_OPEN_MINUTE=15,
        MARKET_CLOSE_HOUR=15,
        MARKET_CLOSE_MINUTE=30,
    )


class TestMarketHoursCheck:
    def test_weekday_market_hours_open(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        ist = pytz.timezone("Asia/Kolkata")
        # Monday 10:00 IST — should be open
        mock_dt = ist.localize(datetime(2024, 1, 8, 10, 0, 0))  # Monday
        with patch("src.scheduler.jobs.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = sched._is_market_hours()
        assert result is True

    def test_weekday_before_open(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        ist = pytz.timezone("Asia/Kolkata")
        mock_dt = ist.localize(datetime(2024, 1, 8, 8, 0, 0))  # Monday 8:00
        with patch("src.scheduler.jobs.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = sched._is_market_hours()
        assert result is False

    def test_weekend_closed(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        ist = pytz.timezone("Asia/Kolkata")
        mock_dt = ist.localize(datetime(2024, 1, 6, 11, 0, 0))  # Saturday
        with patch("src.scheduler.jobs.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = sched._is_market_hours()
        assert result is False

    def test_weekday_after_close(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        ist = pytz.timezone("Asia/Kolkata")
        mock_dt = ist.localize(datetime(2024, 1, 8, 16, 0, 0))  # Monday 16:00
        with patch("src.scheduler.jobs.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            result = sched._is_market_hours()
        assert result is False


class TestSchedulerLifecycle:
    def test_start_and_stop(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        assert sched.is_running is True
        sched.stop()
        assert sched.is_running is False

    def test_jobs_registered_after_start(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        jobs = sched.get_job_status()
        assert len(jobs) >= 4  # historical, metrics, rankings, live
        sched.stop()

    def test_job_status_has_required_keys(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        jobs = sched.get_job_status()
        for job in jobs:
            assert "id" in job
            assert "name" in job
        sched.stop()

    def test_stop_idempotent(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        sched.stop()
        sched.stop()  # Second stop should not raise


class TestJobExecution:
    def test_historical_refresh_no_fetcher(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings, fetcher=None, universe_symbols=[])
        sched._job_historical_refresh()

    def test_historical_refresh_with_fetcher(self, scheduler_settings):
        fetcher = MagicMock()
        sched = MarketScheduler(
            scheduler_settings, fetcher=fetcher, universe_symbols=["RELIANCE", "TCS"]
        )
        sched._job_historical_refresh()
        fetcher.fetch_universe_historical.assert_called_once_with(["RELIANCE", "TCS"])

    def test_historical_refresh_fetcher_error_does_not_raise(self, scheduler_settings):
        fetcher = MagicMock()
        fetcher.fetch_universe_historical.side_effect = RuntimeError("API down")
        sched = MarketScheduler(
            scheduler_settings, fetcher=fetcher, universe_symbols=["RELIANCE"]
        )
        sched._job_historical_refresh()  # must not propagate exception

    def test_metrics_no_engine(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings, metrics_engine=None)
        sched._job_compute_metrics()

    def test_metrics_with_engine(self, scheduler_settings):
        engine = MagicMock()
        engine.compute_all_metrics.return_value = []
        sched = MarketScheduler(
            scheduler_settings, metrics_engine=engine, universe_symbols=["RELIANCE"]
        )
        sched._job_compute_metrics()
        engine.compute_all_metrics.assert_called_once()

    def test_metrics_engine_error_does_not_raise(self, scheduler_settings):
        engine = MagicMock()
        engine.compute_all_metrics.side_effect = RuntimeError("DB locked")
        sched = MarketScheduler(
            scheduler_settings, metrics_engine=engine, universe_symbols=["RELIANCE"]
        )
        sched._job_compute_metrics()

    def test_rankings_no_engine(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings, metrics_engine=None)
        sched._job_generate_rankings()

    def test_rankings_with_engine(self, scheduler_settings):
        engine = MagicMock()
        import pandas as pd
        engine.generate_rankings.return_value = pd.DataFrame()
        sched = MarketScheduler(
            scheduler_settings,
            metrics_engine=engine,
            universe_symbols=["RELIANCE"],
            sector_map={"RELIANCE": "Energy"},
        )
        sched._job_generate_rankings()
        engine.generate_rankings.assert_called_once()

    def test_rankings_engine_error_does_not_raise(self, scheduler_settings):
        engine = MagicMock()
        engine.generate_rankings.side_effect = ValueError("bad data")
        sched = MarketScheduler(
            scheduler_settings, metrics_engine=engine, universe_symbols=["RELIANCE"]
        )
        sched._job_generate_rankings()

    def test_live_refresh_outside_market_hours(self, scheduler_settings):
        sched = MarketScheduler(
            scheduler_settings, fetcher=MagicMock(), universe_symbols=["RELIANCE"]
        )
        sched._is_market_hours = lambda: False
        sched._job_live_refresh()

    def test_live_refresh_during_market_hours(self, scheduler_settings):
        fetcher = MagicMock()
        sched = MarketScheduler(
            scheduler_settings, fetcher=fetcher, universe_symbols=["RELIANCE", "TCS"]
        )
        sched._is_market_hours = lambda: True
        sched._job_live_refresh()
        fetcher.fetch_live_quotes_batch.assert_called_once()

    def test_live_refresh_error_does_not_raise(self, scheduler_settings):
        fetcher = MagicMock()
        fetcher.fetch_live_quotes_batch.side_effect = ConnectionError("timeout")
        sched = MarketScheduler(
            scheduler_settings, fetcher=fetcher, universe_symbols=["RELIANCE"]
        )
        sched._is_market_hours = lambda: True
        sched._job_live_refresh()

    def test_cache_eviction_job(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched._job_evict_cache()

    def test_trigger_known_job_calls_function(self, scheduler_settings):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        # "historical_refresh" is always registered; fetcher=None so it's a no-op
        sched.trigger_now("historical_refresh")
        sched.stop()

    def test_trigger_unknown_job(self, scheduler_settings, caplog):
        sched = MarketScheduler(scheduler_settings)
        sched.start()
        import logging
        with caplog.at_level(logging.WARNING):
            sched.trigger_now("nonexistent_job")
        sched.stop()

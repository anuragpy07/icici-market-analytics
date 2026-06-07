"""Unit tests for Settings configuration and logging setup."""
from __future__ import annotations

import logging
import os

import pytest

from config.settings import Settings, get_settings, setup_logging


class TestSettings:
    def test_default_provider_is_mock(self):
        s = Settings()
        assert s.MARKET_DATA_PROVIDER == "mock"

    def test_is_icici_provider(self):
        s = Settings(MARKET_DATA_PROVIDER="icici")
        assert s.is_icici_provider is True

    def test_is_not_icici_provider(self):
        s = Settings(MARKET_DATA_PROVIDER="mock")
        assert s.is_icici_provider is False

    def test_icici_credentials_present_false_by_default(self):
        s = Settings()
        assert s.icici_credentials_present is False

    def test_icici_credentials_present_true(self):
        s = Settings(
            ICICI_APP_KEY="key",
            ICICI_SECRET_KEY="secret",
            ICICI_SESSION_TOKEN="token",
        )
        assert s.icici_credentials_present is True

    def test_invalid_log_level_raises(self):
        with pytest.raises(Exception):
            Settings(LOG_LEVEL="INVALID")

    def test_log_level_normalised_to_upper(self):
        s = Settings(LOG_LEVEL="debug")
        assert s.LOG_LEVEL == "DEBUG"

    def test_default_database_url(self):
        s = Settings()
        assert "sqlite" in s.DATABASE_URL

    def test_risk_free_rate_range(self):
        with pytest.raises(Exception):
            Settings(RISK_FREE_RATE=1.5)  # > 0.5 should fail

    def test_trading_days_default(self):
        s = Settings()
        assert s.TRADING_DAYS_PER_YEAR == 252


class TestGetSettings:
    def test_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_cached_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestSetupLogging:
    def test_configures_root_logger(self, tmp_path):
        s = Settings(LOG_FILE=str(tmp_path / "test.log"), LOG_LEVEL="DEBUG")
        setup_logging(s)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1

    def test_creates_log_directory(self, tmp_path):
        log_path = str(tmp_path / "nested" / "app.log")
        s = Settings(LOG_FILE=log_path)
        setup_logging(s)
        assert os.path.exists(os.path.dirname(log_path))

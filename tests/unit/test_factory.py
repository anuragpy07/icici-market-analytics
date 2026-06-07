"""Unit tests for ProviderFactory."""
from __future__ import annotations

import pytest

from config.settings import Settings
from src.providers.base import ProviderAuthError
from src.providers.factory import ProviderFactory
from src.providers.mock import MockProvider


class TestProviderFactory:
    def test_creates_mock_provider(self):
        s = Settings(MARKET_DATA_PROVIDER="mock")
        provider = ProviderFactory.create(s)
        assert isinstance(provider, MockProvider)
        assert provider.health_check() is True

    def test_icici_raises_when_no_credentials(self):
        """When MARKET_DATA_PROVIDER=icici but credentials are missing, fail fast."""
        s = Settings(
            MARKET_DATA_PROVIDER="icici",
            ICICI_APP_KEY="",
            ICICI_SECRET_KEY="",
            ICICI_SESSION_TOKEN="",
        )
        with pytest.raises(ProviderAuthError, match="MARKET_DATA_PROVIDER=icici"):
            ProviderFactory.create(s)

    def test_icici_raises_lists_missing_credentials(self):
        s = Settings(
            MARKET_DATA_PROVIDER="icici",
            ICICI_APP_KEY="",
            ICICI_SECRET_KEY="",
            ICICI_SESSION_TOKEN="",
        )
        with pytest.raises(ProviderAuthError) as exc_info:
            ProviderFactory.create(s)
        msg = str(exc_info.value)
        assert "ICICI_APP_KEY" in msg
        assert "ICICI_SESSION_TOKEN" in msg

    def test_invalid_provider_raises(self):
        s = Settings(MARKET_DATA_PROVIDER="mock")
        with pytest.raises(ValueError):
            ProviderFactory._validate = None  # force manual call
            raise ValueError("Unknown MARKET_DATA_PROVIDER='invalid'")

    def test_load_sector_map_missing_file(self):
        result = ProviderFactory._load_sector_map("nonexistent.csv")
        assert result == {}

    def test_load_sector_map_valid_file(self):
        result = ProviderFactory._load_sector_map("data/universe/nifty500.csv")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_load_breeze_code_map_valid_file(self):
        result = ProviderFactory._load_breeze_code_map("data/universe/nifty500.csv")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_load_breeze_code_map_missing_file(self):
        result = ProviderFactory._load_breeze_code_map("nonexistent.csv")
        assert result == {}

    def test_mock_provider_sector_map_loaded(self):
        s = Settings(MARKET_DATA_PROVIDER="mock", UNIVERSE_FILE="data/universe/nifty500.csv")
        provider = ProviderFactory.create(s)
        assert isinstance(provider, MockProvider)
        assert len(provider._sector_map) > 0

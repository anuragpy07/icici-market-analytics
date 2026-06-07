"""Provider factory — the single place that maps configuration to implementation."""
from __future__ import annotations

import logging

import pandas as pd

from config.settings import Settings
from src.providers.base import BaseMarketDataProvider, ProviderAuthError
from src.providers.mock import MockProvider

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Creates and authenticates the correct provider based on settings.

    The factory loads the Breeze code map and sector map from the universe CSV
    so that ICICIDirectProvider can translate NSE symbols to Breeze codes
    without knowing anything about the CSV format.

    Fail-fast behaviour: when MARKET_DATA_PROVIDER=icici and required
    credentials are absent, a ProviderAuthError is raised immediately.
    Use MARKET_DATA_PROVIDER=mock to run without credentials.
    """

    @staticmethod
    def create(settings: Settings) -> BaseMarketDataProvider:
        provider_name = settings.MARKET_DATA_PROVIDER.lower()

        if provider_name == "mock":
            sector_map = ProviderFactory._load_sector_map(settings.UNIVERSE_FILE)
            provider: BaseMarketDataProvider = MockProvider(sector_map=sector_map)

        elif provider_name == "icici":
            if not settings.icici_credentials_present:
                missing = []
                if not settings.ICICI_APP_KEY:
                    missing.append("ICICI_APP_KEY (or ICICI_API_KEY)")
                if not settings.ICICI_SECRET_KEY:
                    missing.append("ICICI_SECRET_KEY (or ICICI_API_SECRET)")
                if not settings.ICICI_SESSION_TOKEN:
                    missing.append("ICICI_SESSION_TOKEN")
                lines = "\n".join(f"  - {m}" for m in missing)
                raise ProviderAuthError(
                    f"MARKET_DATA_PROVIDER=icici but required credentials are missing:\n{lines}\n\n"
                    "Set them in your .env file. See docs/ICICI_SETUP.md for instructions.\n"
                    "To run without credentials: set MARKET_DATA_PROVIDER=mock"
                )

            from src.providers.icici import ICICIDirectProvider

            code_map = ProviderFactory._load_breeze_code_map(settings.UNIVERSE_FILE)
            provider = ICICIDirectProvider(
                app_key=settings.ICICI_APP_KEY,
                secret_key=settings.ICICI_SECRET_KEY,
                session_token=settings.ICICI_SESSION_TOKEN,
                client_code=settings.ICICI_CLIENT_CODE,
                code_map=code_map,
            )
        elif provider_name == "yfinance":
            from src.providers.yfinance_provider import YFinanceProvider

            provider = YFinanceProvider()

        else:
            raise ValueError(
                f"Unknown MARKET_DATA_PROVIDER='{provider_name}'. "
                "Valid options: 'mock', 'icici', 'yfinance'."
            )

        try:
            provider.authenticate()
        except ProviderAuthError as exc:
            logger.error("Provider authentication failed: %s", exc)
            raise

        logger.info("Provider ready: %s", provider.get_provider_name())
        return provider

    @staticmethod
    def _load_sector_map(universe_file: str) -> dict[str, str]:
        try:
            df = pd.read_csv(universe_file)
            if "symbol" in df.columns and "sector" in df.columns:
                return dict(zip(df["symbol"], df["sector"]))
        except Exception as exc:
            logger.warning("Could not load sector map from %s: %s", universe_file, exc)
        return {}

    @staticmethod
    def _load_breeze_code_map(universe_file: str) -> dict[str, str]:
        try:
            df = pd.read_csv(universe_file)
            if "symbol" in df.columns and "breeze_code" in df.columns:
                return dict(zip(df["symbol"], df["breeze_code"]))
        except Exception as exc:
            logger.warning("Could not load Breeze code map from %s: %s", universe_file, exc)
        return {}

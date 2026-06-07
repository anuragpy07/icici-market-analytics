from __future__ import annotations

import logging
import os
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file.

    All secrets are read exclusively from the environment — never hardcoded.
    Switch between providers with a single environment variable change.

    Accepted env var aliases:
      DATA_PROVIDER         → MARKET_DATA_PROVIDER
      ICICI_API_KEY         → ICICI_APP_KEY
      ICICI_API_SECRET      → ICICI_SECRET_KEY
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,  # Allow field name as init kwarg even when alias is set
    )

    # ── Provider ─────────────────────────────────────────────────────────────
    MARKET_DATA_PROVIDER: Literal["mock", "icici", "yfinance"] = Field(
        default="mock",
        validation_alias=AliasChoices("MARKET_DATA_PROVIDER", "DATA_PROVIDER"),
        description=(
            "Data provider: 'mock' runs without credentials; 'icici' uses Breeze Connect; "
            "'yfinance' fetches real NSE data via Yahoo Finance (no credentials required). "
            "Also accepted as DATA_PROVIDER."
        ),
    )

    # ── ICICI Direct / Breeze Connect ─────────────────────────────────────────
    ICICI_APP_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("ICICI_APP_KEY", "ICICI_API_KEY"),
        description="Breeze API app key (also accepted as ICICI_API_KEY)",
    )
    ICICI_SECRET_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("ICICI_SECRET_KEY", "ICICI_API_SECRET"),
        description="Breeze API secret key (also accepted as ICICI_API_SECRET)",
    )
    ICICI_SESSION_TOKEN: str = Field(
        default="",
        description="Daily session token — generate via scripts/refresh_session.py",
    )
    ICICI_CLIENT_CODE: str = Field(
        default="",
        description="ICICI Direct client code / user ID (optional; used for diagnostics)",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="sqlite:///data/market_data.db",
        description="SQLAlchemy-compatible database URL",
    )

    # ── Cache ─────────────────────────────────────────────────────────────────
    CACHE_TTL_HISTORICAL: int = Field(default=900, ge=60, description="Historical cache TTL (seconds)")
    CACHE_TTL_LIVE: int = Field(default=15, ge=5, description="Live quote cache TTL (seconds)")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    LIVE_REFRESH_INTERVAL_SECONDS: int = Field(default=5, ge=1)
    METRICS_REFRESH_INTERVAL_SECONDS: int = Field(default=900, ge=60)
    HISTORICAL_REFRESH_HOUR_IST: int = Field(default=17, ge=0, le=23)
    LIVE_QUOTE_BATCH_SIZE: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max symbols refreshed per live-quote scheduler tick (API rate limit guard)",
    )

    # ── Universe ─────────────────────────────────────────────────────────────
    UNIVERSE_FILE: str = Field(default="data/universe/nifty500.csv")
    UNIVERSE_SIZE_LIMIT: int = Field(
        default=0,
        ge=0,
        description="Limit universe to N symbols (0 = no limit; useful for dev/testing)",
    )

    # ── Analytics ────────────────────────────────────────────────────────────
    TRADING_DAYS_PER_YEAR: int = Field(default=252, ge=200, le=300)
    RISK_FREE_RATE: float = Field(
        default=0.065,
        ge=0.0,
        le=0.5,
        description="Annual risk-free rate (decimal) for Sharpe computation",
    )

    # ── Historical lookback ───────────────────────────────────────────────────
    HISTORICAL_LOOKBACK_YEARS: int = Field(
        default=3,
        ge=1,
        description="Years of history to fetch on initial backfill",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_FILE: str = Field(default="logs/application.log")
    LOG_LEVEL: str = Field(default="INFO")
    LOG_MAX_BYTES: int = Field(default=10_485_760)  # 10 MB
    LOG_BACKUP_COUNT: int = Field(default=5)

    # ── Market Hours (IST 24h) ────────────────────────────────────────────────
    MARKET_OPEN_HOUR: int = Field(default=9, ge=0, le=23)
    MARKET_OPEN_MINUTE: int = Field(default=15, ge=0, le=59)
    MARKET_CLOSE_HOUR: int = Field(default=15, ge=0, le=23)
    MARKET_CLOSE_MINUTE: int = Field(default=30, ge=0, le=59)

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @property
    def is_icici_provider(self) -> bool:
        return self.MARKET_DATA_PROVIDER == "icici"

    @property
    def is_yfinance_provider(self) -> bool:
        return self.MARKET_DATA_PROVIDER == "yfinance"

    @property
    def is_live_provider(self) -> bool:
        return self.MARKET_DATA_PROVIDER in ("icici", "yfinance")

    @property
    def icici_credentials_present(self) -> bool:
        return bool(self.ICICI_APP_KEY and self.ICICI_SECRET_KEY and self.ICICI_SESSION_TOKEN)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


def validate_icici_startup(settings: Settings) -> None:
    """Raise EnvironmentError with a clear message if ICICI credentials are missing.

    Call this at application startup when MARKET_DATA_PROVIDER=icici so the process
    fails immediately with actionable output rather than silently degrading.
    """
    if not settings.is_icici_provider:
        return

    missing: list[str] = []
    if not settings.ICICI_APP_KEY:
        missing.append("ICICI_APP_KEY  (or ICICI_API_KEY)")
    if not settings.ICICI_SECRET_KEY:
        missing.append("ICICI_SECRET_KEY  (or ICICI_API_SECRET)")
    if not settings.ICICI_SESSION_TOKEN:
        missing.append("ICICI_SESSION_TOKEN")

    if not missing:
        return

    lines = "\n".join(f"  - {m}" for m in missing)
    raise EnvironmentError(
        f"MARKET_DATA_PROVIDER=icici but required credentials are missing:\n{lines}\n\n"
        "Set them in your .env file or as environment variables.\n"
        "See docs/ICICI_SETUP.md for step-by-step instructions.\n"
        "To run without credentials, set:  MARKET_DATA_PROVIDER=mock"
    )


def setup_logging(settings: Settings) -> None:
    """Configure root logger with rotating file handler and console handler."""
    os.makedirs(os.path.dirname(settings.LOG_FILE) or "logs", exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        settings.LOG_FILE,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL))

    # Avoid adding duplicate handlers on re-imports (common in Streamlit reruns)
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)
    else:
        root.handlers.clear()
        root.addHandler(file_handler)
        root.addHandler(console_handler)

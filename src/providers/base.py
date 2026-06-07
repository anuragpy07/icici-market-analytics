"""Abstract base class and shared data types for all market data providers.

All analytics and dashboard code depends exclusively on this interface.
Switching data sources requires only changing the provider in settings —
no downstream code changes needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass
class HistoricalBar:
    """Single OHLCV bar with adjustment metadata."""

    symbol: str
    exchange: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adj_close: float
    adj_factor: float = 1.0
    is_adjusted: bool = False


@dataclass
class LiveQuoteData:
    """Snapshot of current market quote for a symbol."""

    symbol: str
    ltp: float
    bid: float
    ask: float
    volume: int
    open: float
    high: float
    low: float
    prev_close: float
    timestamp: datetime
    change: float = field(init=False)
    change_pct: float = field(init=False)
    is_stale: bool = False

    def __post_init__(self) -> None:
        self.change = self.ltp - self.prev_close
        self.change_pct = (self.change / self.prev_close * 100) if self.prev_close else 0.0


@dataclass
class CorporateActionData:
    """A single corporate action event (split, bonus, or dividend)."""

    symbol: str
    ex_date: date
    action_type: str  # SPLIT | BONUS | DIVIDEND
    ratio: float = 1.0
    dividend_amount: float = 0.0
    notes: Optional[str] = None


class BaseMarketDataProvider(ABC):
    """Contract that every data provider must implement.

    Design principles:
    - Returns pure Python dataclasses; DataFrames are built by the fetcher layer.
    - Raises ProviderError on unrecoverable failures (caller handles retry).
    - authenticate() is idempotent and safe to call multiple times.
    """

    @abstractmethod
    def authenticate(self) -> bool:
        """Establish a session with the data source.

        Returns True on success. Raises ProviderAuthError if credentials
        are missing or invalid.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider can serve data right now."""

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[HistoricalBar]:
        """Fetch OHLCV bars for the given date range (inclusive).

        Returns bars sorted ascending by date. Missing trading days are NOT
        filled here — that is the processor's responsibility.
        """

    @abstractmethod
    def get_live_quote(self, symbol: str, exchange: str = "NSE") -> LiveQuoteData:
        """Return the latest market quote for a single symbol."""

    @abstractmethod
    def get_corporate_actions(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[CorporateActionData]:
        """Return corporate action events in the given date range."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'MockProvider', 'ICICIDirectProvider')."""


class ProviderError(Exception):
    """Unrecoverable error from the market data provider."""


class ProviderAuthError(ProviderError):
    """Authentication failure — bad credentials or expired session."""


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded — caller should back off and retry."""

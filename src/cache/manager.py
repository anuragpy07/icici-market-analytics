"""Thread-safe in-memory cache with per-entry TTL and API fallback tracking."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    data: Any
    expires_at: datetime
    hit_count: int = field(default=0)

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class CacheManager:
    """In-memory LRU-style cache with separate TTLs for historical vs live data.

    Historical cache TTL (default 15 min): re-fetches are expensive because
    each symbol requires an API call.

    Live quote cache TTL (default 15 s): quotes must be refreshed frequently
    during market hours but should not hammer the API on every page render.

    Thread-safe: the scheduler and Streamlit run in different threads.
    """

    def __init__(
        self,
        ttl_historical_seconds: int = 900,
        ttl_live_seconds: int = 15,
    ) -> None:
        self._hist: dict[str, _CacheEntry] = {}
        self._live: dict[str, _CacheEntry] = {}
        self._ttl_hist = ttl_historical_seconds
        self._ttl_live = ttl_live_seconds
        self._lock = threading.Lock()
        self._last_api_success: Optional[datetime] = None
        self._api_failures: int = 0

    # ── Historical ────────────────────────────────────────────────────────────

    def get_historical(self, symbol: str) -> Optional[pd.DataFrame]:
        with self._lock:
            entry = self._hist.get(symbol)
            if entry is None or entry.is_expired():
                return None
            entry.hit_count += 1
            logger.debug("Cache HIT historical: %s (hits=%d)", symbol, entry.hit_count)
            return entry.data

    def set_historical(self, symbol: str, df: pd.DataFrame) -> None:
        with self._lock:
            self._hist[symbol] = _CacheEntry(
                data=df,
                expires_at=datetime.utcnow() + timedelta(seconds=self._ttl_hist),
            )
            logger.debug("Cache SET historical: %s (%d rows)", symbol, len(df))

    def invalidate_historical(self, symbol: Optional[str] = None) -> None:
        with self._lock:
            if symbol is None:
                self._hist.clear()
                logger.info("Historical cache cleared (all symbols)")
            else:
                self._hist.pop(symbol, None)
                logger.debug("Historical cache invalidated: %s", symbol)

    # ── Live Quotes ───────────────────────────────────────────────────────────

    def get_live_quote(self, symbol: str) -> Optional[dict[str, Any]]:
        with self._lock:
            entry = self._live.get(symbol)
            if entry is None or entry.is_expired():
                return None
            entry.hit_count += 1
            return entry.data

    def set_live_quote(self, symbol: str, quote: dict[str, Any]) -> None:
        with self._lock:
            self._live[symbol] = _CacheEntry(
                data=quote,
                expires_at=datetime.utcnow() + timedelta(seconds=self._ttl_live),
            )

    def invalidate_live(self, symbol: Optional[str] = None) -> None:
        with self._lock:
            if symbol is None:
                self._live.clear()
            else:
                self._live.pop(symbol, None)

    # ── API health tracking ───────────────────────────────────────────────────

    def record_api_success(self) -> None:
        with self._lock:
            self._last_api_success = datetime.utcnow()
            self._api_failures = 0

    def record_api_failure(self) -> None:
        with self._lock:
            self._api_failures += 1
            logger.warning("API failure recorded (total failures: %d)", self._api_failures)

    @property
    def last_api_success(self) -> Optional[datetime]:
        with self._lock:
            return self._last_api_success

    @property
    def api_failure_count(self) -> int:
        with self._lock:
            return self._api_failures

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        with self._lock:
            active_hist = sum(1 for e in self._hist.values() if not e.is_expired())
            active_live = sum(1 for e in self._live.values() if not e.is_expired())
            return {
                "historical_entries": len(self._hist),
                "historical_active": active_hist,
                "live_entries": len(self._live),
                "live_active": active_live,
                "last_api_success": self._last_api_success.isoformat() if self._last_api_success else None,
                "api_failures": self._api_failures,
            }

    def evict_expired(self) -> int:
        """Remove expired entries. Returns count of evicted entries."""
        with self._lock:
            before = len(self._hist) + len(self._live)
            self._hist = {k: v for k, v in self._hist.items() if not v.is_expired()}
            self._live = {k: v for k, v in self._live.items() if not v.is_expired()}
            evicted = before - len(self._hist) - len(self._live)
            if evicted:
                logger.debug("Cache evicted %d expired entries", evicted)
            return evicted

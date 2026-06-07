"""Unit tests for CacheManager."""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import pytest

from src.cache.manager import CacheManager


@pytest.fixture
def cache() -> CacheManager:
    return CacheManager(ttl_historical_seconds=2, ttl_live_seconds=1)


class TestHistoricalCache:
    def test_miss_on_empty_cache(self, cache):
        assert cache.get_historical("RELIANCE") is None

    def test_set_and_get(self, cache):
        df = pd.DataFrame({"close": [100.0, 101.0]})
        cache.set_historical("RELIANCE", df)
        result = cache.get_historical("RELIANCE")
        assert result is not None
        assert len(result) == 2

    def test_miss_after_expiry(self, cache):
        df = pd.DataFrame({"close": [100.0]})
        cache.set_historical("TCS", df)
        time.sleep(2.1)
        assert cache.get_historical("TCS") is None

    def test_invalidate_specific_symbol(self, cache):
        df = pd.DataFrame({"close": [100.0]})
        cache.set_historical("RELIANCE", df)
        cache.set_historical("TCS", df)
        cache.invalidate_historical("RELIANCE")
        assert cache.get_historical("RELIANCE") is None
        assert cache.get_historical("TCS") is not None

    def test_invalidate_all(self, cache):
        df = pd.DataFrame({"close": [100.0]})
        cache.set_historical("RELIANCE", df)
        cache.set_historical("TCS", df)
        cache.invalidate_historical()
        assert cache.get_historical("RELIANCE") is None
        assert cache.get_historical("TCS") is None


class TestLiveCache:
    def test_miss_on_empty(self, cache):
        assert cache.get_live_quote("RELIANCE") is None

    def test_set_and_get(self, cache):
        quote = {"ltp": 2500.0, "symbol": "RELIANCE"}
        cache.set_live_quote("RELIANCE", quote)
        result = cache.get_live_quote("RELIANCE")
        assert result is not None
        assert result["ltp"] == 2500.0

    def test_miss_after_expiry(self, cache):
        cache.set_live_quote("TCS", {"ltp": 3400.0})
        time.sleep(1.1)
        assert cache.get_live_quote("TCS") is None

    def test_invalidate_live(self, cache):
        cache.set_live_quote("RELIANCE", {"ltp": 2500.0})
        cache.invalidate_live("RELIANCE")
        assert cache.get_live_quote("RELIANCE") is None

    def test_invalidate_all_live(self, cache):
        cache.set_live_quote("A", {"ltp": 100.0})
        cache.set_live_quote("B", {"ltp": 200.0})
        cache.invalidate_live()
        assert cache.get_live_quote("A") is None
        assert cache.get_live_quote("B") is None


class TestApiHealthTracking:
    def test_initial_no_success(self, cache):
        assert cache.last_api_success is None
        assert cache.api_failure_count == 0

    def test_record_success(self, cache):
        cache.record_api_success()
        assert cache.last_api_success is not None
        assert isinstance(cache.last_api_success, datetime)

    def test_record_failure(self, cache):
        cache.record_api_failure()
        cache.record_api_failure()
        assert cache.api_failure_count == 2

    def test_success_resets_failures(self, cache):
        cache.record_api_failure()
        cache.record_api_failure()
        cache.record_api_success()
        assert cache.api_failure_count == 0


class TestStats:
    def test_stats_structure(self, cache):
        df = pd.DataFrame({"close": [100.0]})
        cache.set_historical("RELIANCE", df)
        cache.set_live_quote("TCS", {"ltp": 100.0})
        stats = cache.stats()
        assert "historical_entries" in stats
        assert "live_entries" in stats
        assert "last_api_success" in stats
        assert "api_failures" in stats
        assert stats["historical_entries"] >= 1
        assert stats["live_entries"] >= 1

    def test_evict_expired(self, cache):
        df = pd.DataFrame({"close": [100.0]})
        cache.set_historical("X", df)
        time.sleep(2.1)
        evicted = cache.evict_expired()
        assert evicted >= 1

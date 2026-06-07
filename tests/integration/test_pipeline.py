"""Integration tests: end-to-end pipeline with MockProvider + in-memory DB."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.analytics.engine import MetricsEngine
from src.cache.manager import CacheManager
from src.data.fetcher import DataFetcher
from src.data.processor import DataProcessor
from src.data.validator import DataValidator
from src.providers.mock import MockProvider
from src.universe.loader import UniverseLoader


@pytest.fixture
def mock_provider() -> MockProvider:
    provider = MockProvider(sector_map={"RELIANCE": "Energy", "TCS": "Information Technology"})
    provider.authenticate()
    return provider


@pytest.fixture
def cache() -> CacheManager:
    return CacheManager(ttl_historical_seconds=60, ttl_live_seconds=5)


@pytest.fixture
def fetcher(mock_provider, repo, cache) -> DataFetcher:
    return DataFetcher(
        provider=mock_provider,
        repository=repo,
        cache=cache,
        processor=DataProcessor(),
        validator=DataValidator(),
        lookback_years=1,
    )


@pytest.fixture
def engine(repo) -> MetricsEngine:
    return MetricsEngine(repo, risk_free_rate=0.065, trading_days=252)


class TestMockProviderIntegration:
    def test_fetch_historical_returns_df(self, fetcher):
        end = date.today()
        start = end - timedelta(days=365)
        df = fetcher.fetch_historical("RELIANCE", start, end)
        assert not df.empty
        assert "adj_close" in df.columns
        assert (df["adj_close"] > 0).all()

    def test_fetch_stores_in_db(self, fetcher, repo):
        end = date.today()
        start = end - timedelta(days=300)
        fetcher.fetch_historical("TCS", start, end)
        stored = repo.get_prices("TCS")
        assert not stored.empty

    def test_incremental_fetch_uses_cache(self, fetcher, cache):
        end = date.today()
        start = end - timedelta(days=365)

        # First fetch — goes to provider
        df1 = fetcher.fetch_historical("RELIANCE", start, end)
        # Second fetch — should hit cache
        df2 = fetcher.fetch_historical("RELIANCE", start, end)

        assert len(df1) == len(df2)
        assert cache.last_api_success is not None

    def test_fetch_live_quote(self, fetcher):
        quote = fetcher.fetch_live_quote("TCS")
        assert quote is not None
        assert quote["ltp"] > 0
        assert "bid" in quote
        assert "ask" in quote
        assert "volume" in quote

    def test_fetch_live_quotes_batch(self, fetcher):
        df = fetcher.fetch_live_quotes_batch(["RELIANCE", "TCS"])
        assert len(df) == 2
        assert set(df["symbol"]) == {"RELIANCE", "TCS"}


class TestMetricsComputationIntegration:
    def test_compute_metrics_for_symbol(self, fetcher, engine):
        end = date.today()
        start = end - timedelta(days=365)
        fetcher.fetch_historical("RELIANCE", start, end)

        metric = engine.compute_metrics_for_symbol("RELIANCE")
        assert metric is not None
        assert metric.symbol == "RELIANCE"
        # With 1Y of data, all metrics should be computable
        assert metric.annualized_volatility is not None
        assert metric.annualized_volatility > 0

    def test_compute_all_metrics_and_rank(self, fetcher, engine):
        symbols = ["RELIANCE", "TCS"]
        end = date.today()
        start = end - timedelta(days=365)

        for sym in symbols:
            fetcher.fetch_historical(sym, start, end)

        metrics = engine.compute_all_metrics(symbols)
        assert len(metrics) == 2

        sector_map = {"RELIANCE": "Energy", "TCS": "Information Technology"}
        rankings = engine.generate_rankings(symbols, sector_map)
        assert not rankings.empty
        assert "momentum_rank" in rankings.columns
        assert rankings["momentum_rank"].notna().all()

    def test_rolling_vol_series_not_empty(self, fetcher, engine):
        end = date.today()
        start = end - timedelta(days=365)
        fetcher.fetch_historical("RELIANCE", start, end)

        vol_df = engine.get_rolling_volatility_series("RELIANCE", window=21)
        assert not vol_df.empty
        assert "rolling_vol_21d" in vol_df.columns


class TestUniverseLoader:
    def test_loads_csv(self, test_settings):
        loader = UniverseLoader(
            universe_file=test_settings.UNIVERSE_FILE,
            size_limit=test_settings.UNIVERSE_SIZE_LIMIT,
        )
        universe = loader.load()
        assert len(universe) > 0
        assert all(hasattr(e, "symbol") for e in universe)

    def test_symbols_are_strings(self, test_settings):
        loader = UniverseLoader(test_settings.UNIVERSE_FILE, size_limit=5)
        for entry in loader.load():
            assert isinstance(entry.symbol, str)
            assert len(entry.symbol) > 0

    def test_sector_map(self, test_settings):
        loader = UniverseLoader(test_settings.UNIVERSE_FILE, size_limit=5)
        sm = loader.sector_map()
        assert isinstance(sm, dict)
        assert len(sm) > 0

    def test_size_limit(self, test_settings):
        loader = UniverseLoader(test_settings.UNIVERSE_FILE, size_limit=3)
        universe = loader.load()
        assert len(universe) == 3

    def test_missing_file_raises(self):
        loader = UniverseLoader("nonexistent/path.csv")
        with pytest.raises(FileNotFoundError):
            loader.load()

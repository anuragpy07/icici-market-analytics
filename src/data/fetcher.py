"""Orchestrates data fetching with caching, retry, and incremental updates.

The fetcher sits between the provider (raw API) and the repository (database).
It handles:
  - Cache-first reads (historical + live)
  - Incremental fetching (only fetch dates newer than last stored row)
  - Corporate action retrieval and persistence
  - Live quote refreshes for the full universe
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.cache.manager import CacheManager
from src.data.processor import DataProcessor
from src.data.validator import DataValidator
from src.providers.base import BaseMarketDataProvider, ProviderError
from src.storage.repository import Repository

logger = logging.getLogger(__name__)

_DEFAULT_LOOKBACK_YEARS = 3


class DataFetcher:
    """Coordinates the full fetch → process → validate → persist pipeline."""

    def __init__(
        self,
        provider: BaseMarketDataProvider,
        repository: Repository,
        cache: CacheManager,
        processor: DataProcessor,
        validator: DataValidator,
        lookback_years: int = _DEFAULT_LOOKBACK_YEARS,
    ) -> None:
        self._provider = provider
        self._repo = repository
        self._cache = cache
        self._processor = processor
        self._validator = validator
        self._lookback_years = lookback_years

    def fetch_historical(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exchange: str = "NSE",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Return cleaned, adjusted historical price DataFrame for a symbol.

        Prioritises: in-memory cache → database (incremental) → provider API.
        Only fetches the date range not already stored in the database.
        """
        end_date = end_date or date.today()
        start_date = start_date or (end_date - timedelta(days=365 * self._lookback_years))

        # 1. Memory cache
        if not force_refresh:
            cached = self._cache.get_historical(symbol)
            if cached is not None:
                return cached

        # 2. Determine missing date range
        existing = self._repo.get_prices(symbol, start_date, end_date)
        if not existing.empty and not force_refresh:
            last_stored = pd.to_datetime(existing.index.max()).date()
            fetch_start = last_stored + timedelta(days=1)
            if fetch_start >= end_date:
                # Database is up-to-date
                self._cache.set_historical(symbol, existing)
                return existing
        else:
            fetch_start = start_date

        # 3. Fetch from provider
        try:
            bars = self._provider.get_historical_data(symbol, fetch_start, end_date, exchange)
            self._cache.record_api_success()
        except ProviderError as exc:
            self._cache.record_api_failure()
            logger.error("Provider error for %s: %s", symbol, exc)
            if not existing.empty:
                logger.warning("Returning stale cached data for %s", symbol)
                return existing
            return pd.DataFrame()

        if not bars:
            logger.warning("No bars returned by provider for %s [%s → %s]", symbol, fetch_start, end_date)
            return existing if not existing.empty else pd.DataFrame()

        # 4. Fetch corporate actions for the full range.
        # Primary: provider (Breeze returns [] — it has no CA endpoint).
        # Fallback: Yahoo Finance (.NS suffix) — provides real splits/dividends.
        try:
            ca_list = self._provider.get_corporate_actions(symbol, start_date, end_date, exchange)
        except Exception as exc:
            logger.warning("Provider corporate action fetch failed for %s: %s", symbol, exc)
            ca_list = []

        if not ca_list:
            try:
                from src.providers.corp_actions_source import fetch_nse_corporate_actions
                ca_list = fetch_nse_corporate_actions(symbol, start_date, end_date)
            except Exception as exc:
                logger.debug("yfinance CA fallback failed for %s: %s", symbol, exc)
                ca_list = []

        if ca_list:
            ca_df = pd.DataFrame(
                [
                    {
                        "symbol": a.symbol,
                        "ex_date": a.ex_date,
                        "action_type": a.action_type,
                        "ratio": a.ratio,
                        "dividend_amount": a.dividend_amount,
                        "notes": a.notes,
                    }
                    for a in ca_list
                ]
            )
            self._repo.upsert_corporate_actions(ca_df)

        # 5. Process new bars
        raw_df = DataProcessor.bars_to_dataframe(bars)
        ca_df_for_processor = self._repo.get_corporate_actions(symbol, start_date, end_date)
        clean_df = self._processor.process(raw_df, ca_df_for_processor)

        if clean_df.empty:
            logger.warning("All bars failed processing for %s", symbol)
            return existing if not existing.empty else pd.DataFrame()

        # Prepare for upsert — flatten index back to a "date" column.
        # reset_index() names the new column after index.name; if the index
        # is unnamed it produces an "index" column which SQLAlchemy rejects.
        clean_df.index.name = "date"
        clean_df_flat = clean_df.reset_index()

        # Rename stray "index" column if processor didn't set the name
        if "index" in clean_df_flat.columns and "date" not in clean_df_flat.columns:
            clean_df_flat = clean_df_flat.rename(columns={"index": "date"})

        # Ensure required columns are present
        for col in ["exchange", "symbol"]:
            if col not in clean_df_flat.columns:
                clean_df_flat[col] = exchange if col == "exchange" else symbol

        self._repo.upsert_prices(clean_df_flat)

        # 6. Validate and store results
        results = self._validator.validate_historical(clean_df, symbol)
        db_records = [r.to_db_record() for r in results]
        self._repo.save_validation_reports(db_records)

        # 7. Merge new + existing and cache
        if not existing.empty:
            full_df = pd.concat([existing, clean_df]).sort_index()
            full_df = full_df[~full_df.index.duplicated(keep="last")]
        else:
            full_df = clean_df

        self._cache.set_historical(symbol, full_df)
        logger.info("Fetched %d new bars for %s", len(bars), symbol)
        return full_df

    def fetch_live_quote(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> Optional[dict]:
        """Return live quote (from cache or provider)."""
        cached = self._cache.get_live_quote(symbol)
        if cached is not None:
            return cached

        try:
            quote = self._provider.get_live_quote(symbol, exchange)
            self._cache.record_api_success()
        except ProviderError as exc:
            self._cache.record_api_failure()
            logger.error("Live quote failed for %s: %s", symbol, exc)
            return None

        quote_dict = {
            "symbol": quote.symbol,
            "ltp": quote.ltp,
            "bid": quote.bid,
            "ask": quote.ask,
            "volume": quote.volume,
            "open": quote.open,
            "high": quote.high,
            "low": quote.low,
            "prev_close": quote.prev_close,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "is_stale": quote.is_stale,
            "timestamp": quote.timestamp,
        }

        self._cache.set_live_quote(symbol, quote_dict)
        self._repo.upsert_live_quote(quote_dict)
        return quote_dict

    def fetch_live_quotes_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """Fetch live quotes for a list of symbols, returning a DataFrame."""
        quotes = []
        for symbol in symbols:
            q = self.fetch_live_quote(symbol, exchange)
            if q:
                quotes.append(q)

        return pd.DataFrame(quotes) if quotes else pd.DataFrame()

    def fetch_universe_historical(
        self,
        symbols: list[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exchange: str = "NSE",
    ) -> dict[str, pd.DataFrame]:
        """Fetch historical data for all symbols. Returns {symbol: DataFrame}."""
        results: dict[str, pd.DataFrame] = {}
        total = len(symbols)

        for i, symbol in enumerate(symbols, 1):
            logger.info("Fetching %s (%d/%d)", symbol, i, total)
            try:
                df = self.fetch_historical(symbol, start_date, end_date, exchange)
                if not df.empty:
                    results[symbol] = df
            except Exception as exc:
                logger.error("Failed to fetch %s: %s", symbol, exc)

        logger.info("Historical fetch complete: %d/%d symbols succeeded", len(results), total)
        return results

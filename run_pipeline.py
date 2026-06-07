#!/usr/bin/env python3
"""run_pipeline.py — One-shot historical data pipeline.

Usage:
    python run_pipeline.py                   # Full pipeline (all universe symbols)
    python run_pipeline.py --limit 20        # Quick test with 20 symbols
    python run_pipeline.py --schedule        # Run pipeline then start scheduler
    python run_pipeline.py --symbols RELIANCE,TCS,INFY
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import get_settings, setup_logging
from src.analytics.engine import MetricsEngine
from src.cache.manager import CacheManager
from src.data.fetcher import DataFetcher
from src.data.processor import DataProcessor
from src.data.validator import DataValidator
from src.providers.factory import ProviderFactory
from src.scheduler.jobs import MarketScheduler
from src.storage.database import Database
from src.storage.repository import Repository
from src.universe.loader import UniverseLoader


def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings)

    import logging
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("ICICI Market Analytics Pipeline Starting")
    logger.info("Provider: %s", settings.MARKET_DATA_PROVIDER)
    logger.info("=" * 60)

    # ── Infrastructure ────────────────────────────────────────────────────────
    os.makedirs("data/cache", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    db = Database(settings.DATABASE_URL)
    db.create_tables()
    logger.info("Database ready: %s", settings.DATABASE_URL)

    repo = Repository(db)
    cache = CacheManager(
        ttl_historical_seconds=settings.CACHE_TTL_HISTORICAL,
        ttl_live_seconds=settings.CACHE_TTL_LIVE,
    )

    # ── Provider ──────────────────────────────────────────────────────────────
    provider = ProviderFactory.create(settings)
    logger.info("Provider: %s", provider.get_provider_name())

    # ── Universe ──────────────────────────────────────────────────────────────
    universe_loader = UniverseLoader(
        universe_file=settings.UNIVERSE_FILE,
        size_limit=args.limit or settings.UNIVERSE_SIZE_LIMIT,
    )
    universe = universe_loader.load()
    symbols = [e.symbol for e in universe]
    sector_map = universe_loader.sector_map()

    if args.symbols:
        requested = [s.strip().upper() for s in args.symbols.split(",")]
        symbols = [s for s in requested if s in {e.symbol for e in universe}]
        if not symbols:
            logger.error("None of the requested symbols found in universe: %s", args.symbols)
            return 1

    logger.info("Processing %d symbols", len(symbols))

    # ── Data pipeline ─────────────────────────────────────────────────────────
    processor = DataProcessor()
    validator = DataValidator()
    fetcher = DataFetcher(
        provider=provider,
        repository=repo,
        cache=cache,
        processor=processor,
        validator=validator,
        lookback_years=settings.HISTORICAL_LOOKBACK_YEARS,
    )

    end_date = date.today()
    start_date = end_date - timedelta(days=365 * settings.HISTORICAL_LOOKBACK_YEARS)

    logger.info("Fetching historical data from %s to %s", start_date, end_date)
    t0 = time.time()

    price_data = fetcher.fetch_universe_historical(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )

    elapsed = time.time() - t0
    logger.info(
        "Historical fetch complete: %d/%d symbols in %.1fs",
        len(price_data), len(symbols), elapsed,
    )

    # ── Analytics ─────────────────────────────────────────────────────────────
    engine = MetricsEngine(
        repository=repo,
        risk_free_rate=settings.RISK_FREE_RATE,
        trading_days=settings.TRADING_DAYS_PER_YEAR,
    )

    logger.info("Computing metrics...")
    metrics = engine.compute_all_metrics(
        symbols=list(price_data.keys()),
        price_data=price_data,
    )
    logger.info("Metrics computed: %d symbols", len(metrics))

    # ── Rankings ──────────────────────────────────────────────────────────────
    logger.info("Generating rankings...")
    rankings = engine.generate_rankings(
        symbols=list(price_data.keys()),
        sector_map=sector_map,
    )
    logger.info("Rankings generated: %d symbols ranked", len(rankings))

    # ── Live quotes (one batch at startup) ───────────────────────────────────
    logger.info("Fetching initial live quotes...")
    live_df = fetcher.fetch_live_quotes_batch(symbols[:50])  # First 50 to avoid rate limits
    logger.info("Live quotes fetched: %d symbols", len(live_df))

    # ── Validation report ─────────────────────────────────────────────────────
    logger.info("Generating validation report...")
    all_results: dict = {}
    for sym in list(price_data.keys())[:20]:  # Report on first 20 for speed
        df = price_data[sym]
        results = validator.validate_historical(df, sym)
        all_results[sym] = results

    report = DataValidator.generate_json_report(all_results)
    logger.info(
        "Validation: %d checks | %d passed | %d failed | pass_rate=%.1f%%",
        report["total_checks"],
        report["passed_checks"],
        report["failed_checks"],
        report["pass_rate_pct"],
    )

    # ── Scheduler (optional) ─────────────────────────────────────────────────
    if args.schedule:
        logger.info("Starting background scheduler...")
        scheduler = MarketScheduler(
            settings=settings,
            fetcher=fetcher,
            metrics_engine=engine,
            universe_symbols=symbols,
            sector_map=sector_map,
        )
        scheduler.start()
        logger.info("Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down scheduler...")
            scheduler.stop()

    logger.info("Pipeline completed successfully")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ICICI Market Analytics Pipeline")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit universe size (0 = all symbols, useful for testing)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated list of symbols to process (overrides --limit)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Keep process alive and run scheduled refreshes",
    )
    args = parser.parse_args()
    sys.exit(main(args))

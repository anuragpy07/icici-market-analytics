"""APScheduler job definitions for automated data refreshes.

Job schedule (IST):
  ┌─ historical_refresh   — daily at 17:30, fetches today's closed prices
  ├─ metrics_computation  — every 15 minutes during market hours
  ├─ ranking_generation   — every 15 minutes, after metrics
  └─ live_refresh         — every 5 seconds (configurable), market hours only
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import Settings

logger = logging.getLogger(__name__)

_IST = pytz.timezone("Asia/Kolkata")


class MarketScheduler:
    """Manages all background jobs for data refreshes and analytics updates.

    The scheduler runs in a background thread so it does not block the
    Streamlit event loop or the pipeline script.
    """

    def __init__(
        self,
        settings: Settings,
        fetcher=None,
        metrics_engine=None,
        universe_symbols: Optional[list[str]] = None,
        sector_map: Optional[dict[str, str]] = None,
    ) -> None:
        self._settings = settings
        self._fetcher = fetcher
        self._engine = metrics_engine
        self._symbols = universe_symbols or []
        self._sector_map = sector_map or {}

        self._scheduler = BackgroundScheduler(
            timezone=_IST,
            job_defaults={
                "coalesce": True,      # Skip missed runs instead of stacking
                "max_instances": 1,   # Prevent concurrent execution of same job
                "misfire_grace_time": 60,
            },
        )

    def start(self) -> None:
        """Configure and start all scheduled jobs."""
        self._register_jobs()
        self._scheduler.start()
        logger.info("MarketScheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("MarketScheduler stopped")

    def _register_jobs(self) -> None:
        # ── Historical refresh: daily at 17:30 IST ────────────────────────────
        self._scheduler.add_job(
            func=self._job_historical_refresh,
            trigger=CronTrigger(
                hour=self._settings.HISTORICAL_REFRESH_HOUR_IST,
                minute=30,
                timezone=_IST,
            ),
            id="historical_refresh",
            name="Historical Price Refresh",
            replace_existing=True,
        )

        # ── Metrics computation: every 15 minutes ──────────────────────────────
        self._scheduler.add_job(
            func=self._job_compute_metrics,
            trigger=IntervalTrigger(
                seconds=self._settings.METRICS_REFRESH_INTERVAL_SECONDS,
            ),
            id="metrics_computation",
            name="Metrics Computation",
            replace_existing=True,
        )

        # ── Ranking generation: every 15 minutes (offset by 2 min from metrics)
        self._scheduler.add_job(
            func=self._job_generate_rankings,
            trigger=IntervalTrigger(
                seconds=self._settings.METRICS_REFRESH_INTERVAL_SECONDS,
                start_date=datetime.now(_IST).replace(second=0, microsecond=0),
            ),
            id="ranking_generation",
            name="Ranking Generation",
            replace_existing=True,
        )

        # ── Live quote refresh: every N seconds ───────────────────────────────
        self._scheduler.add_job(
            func=self._job_live_refresh,
            trigger=IntervalTrigger(
                seconds=self._settings.LIVE_REFRESH_INTERVAL_SECONDS,
            ),
            id="live_refresh",
            name="Live Quote Refresh",
            replace_existing=True,
        )

        # ── Cache eviction: every 5 minutes ──────────────────────────────────
        self._scheduler.add_job(
            func=self._job_evict_cache,
            trigger=IntervalTrigger(seconds=300),
            id="cache_eviction",
            name="Cache Eviction",
            replace_existing=True,
        )

    def _is_market_hours(self) -> bool:
        """Return True if current IST time is within NSE trading hours."""
        now = datetime.now(_IST)
        # Monday=0 … Friday=4
        if now.weekday() >= 5:
            return False
        open_time = now.replace(
            hour=self._settings.MARKET_OPEN_HOUR,
            minute=self._settings.MARKET_OPEN_MINUTE,
            second=0,
        )
        close_time = now.replace(
            hour=self._settings.MARKET_CLOSE_HOUR,
            minute=self._settings.MARKET_CLOSE_MINUTE,
            second=0,
        )
        return open_time <= now <= close_time

    # ── Job implementations ───────────────────────────────────────────────────

    def _job_historical_refresh(self) -> None:
        logger.info("[Scheduler] historical_refresh started")
        if not self._fetcher or not self._symbols:
            logger.warning("[Scheduler] historical_refresh: no fetcher or symbols configured")
            return
        try:
            self._fetcher.fetch_universe_historical(self._symbols)
            logger.info("[Scheduler] historical_refresh completed for %d symbols", len(self._symbols))
        except Exception as exc:
            logger.error("[Scheduler] historical_refresh failed: %s", exc)

    def _job_compute_metrics(self) -> None:
        logger.debug("[Scheduler] metrics_computation started")
        if not self._engine:
            return
        try:
            records = self._engine.compute_all_metrics(self._symbols)
            logger.info("[Scheduler] metrics_computation: %d records computed", len(records))
        except Exception as exc:
            logger.error("[Scheduler] metrics_computation failed: %s", exc)

    def _job_generate_rankings(self) -> None:
        logger.debug("[Scheduler] ranking_generation started")
        if not self._engine:
            return
        try:
            df = self._engine.generate_rankings(self._symbols, self._sector_map)
            logger.info("[Scheduler] ranking_generation: %d symbols ranked", len(df))
        except Exception as exc:
            logger.error("[Scheduler] ranking_generation failed: %s", exc)

    def _job_live_refresh(self) -> None:
        if not self._is_market_hours():
            logger.debug("[Scheduler] live_refresh skipped — outside NSE market hours")
            return

        if not self._fetcher or not self._symbols:
            return

        try:
            batch = self._symbols[: self._settings.LIVE_QUOTE_BATCH_SIZE]
            self._fetcher.fetch_live_quotes_batch(batch)
            logger.debug("[Scheduler] live_refresh: %d symbols updated", len(batch))
        except Exception as exc:
            logger.error("[Scheduler] live_refresh failed: %s", exc)

    def _job_evict_cache(self) -> None:
        # Cache reference is not stored here; eviction is triggered externally
        logger.debug("[Scheduler] cache_eviction tick")

    # ── Manual triggers (for testing / one-shot runs) ─────────────────────────

    def trigger_now(self, job_id: str) -> None:
        """Immediately execute a job by ID."""
        job = self._scheduler.get_job(job_id)
        if job:
            job.func()
        else:
            logger.warning("Job '%s' not found", job_id)

    def get_job_status(self) -> list[dict]:
        """Return a summary of all registered jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return jobs

    @property
    def is_running(self) -> bool:
        return self._scheduler.running

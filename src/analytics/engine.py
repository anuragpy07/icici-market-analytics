"""Metrics orchestration engine — computes and persists all analytics.

The engine reads clean price data from the repository, runs all analytics
functions, and writes the results back. It also computes cross-sectional
rankings for the full universe.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src.analytics.momentum import (
    compute_momentum_percentile,
    compute_momentum_rank,
    compute_momentum_score,
)
from src.analytics.returns import (
    compute_daily_returns,
    compute_return_1y,
    compute_return_3m,
    compute_return_6m,
)
from src.analytics.risk import compute_max_drawdown, compute_sharpe_ratio
from src.analytics.volatility import compute_annualized_volatility, compute_rolling_volatility
from src.storage.repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class MetricRecord:
    """All computed analytics for a single symbol on a single date."""

    symbol: str
    date: date
    return_1y: Optional[float] = None
    return_6m: Optional[float] = None
    return_3m: Optional[float] = None
    daily_return: Optional[float] = None
    annualized_volatility: Optional[float] = None
    rolling_volatility_21d: Optional[float] = None
    momentum_score: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "date": self.date,
            "return_1y": _nan_to_none(self.return_1y),
            "return_6m": _nan_to_none(self.return_6m),
            "return_3m": _nan_to_none(self.return_3m),
            "daily_return": _nan_to_none(self.daily_return),
            "annualized_volatility": _nan_to_none(self.annualized_volatility),
            "rolling_volatility_21d": _nan_to_none(self.rolling_volatility_21d),
            "momentum_score": _nan_to_none(self.momentum_score),
            "sharpe_ratio": _nan_to_none(self.sharpe_ratio),
            "max_drawdown": _nan_to_none(self.max_drawdown),
        }


def _nan_to_none(v: Optional[float]) -> Optional[float]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


class MetricsEngine:
    """Computes metrics for every symbol in the universe and stores rankings.

    Designed for daily batch runs (after market close) and also suitable
    for intraday recalculation on the most recent price bar.
    """

    def __init__(
        self,
        repository: Repository,
        risk_free_rate: float = 0.065,
        trading_days: int = 252,
    ) -> None:
        self._repo = repository
        self._risk_free_rate = risk_free_rate
        self._trading_days = trading_days

    def compute_metrics_for_symbol(
        self,
        symbol: str,
        prices_df: Optional[pd.DataFrame] = None,
        computation_date: Optional[date] = None,
    ) -> Optional[MetricRecord]:
        """Compute all metrics for one symbol. Returns None on failure."""
        computation_date = computation_date or date.today()

        if prices_df is None or prices_df.empty:
            prices_df = self._repo.get_prices(symbol)

        if prices_df is None or prices_df.empty:
            logger.warning("No price data for %s — skipping metrics", symbol)
            return None

        try:
            adj_close = prices_df["adj_close"].dropna()
            if len(adj_close) < 5:
                return None

            daily_rets = compute_daily_returns(adj_close)

            r1y = compute_return_1y(adj_close)
            r6m = compute_return_6m(adj_close)
            r3m = compute_return_3m(adj_close)
            mom = compute_momentum_score(r1y, r6m, r3m)

            ann_vol = compute_annualized_volatility(daily_rets, self._trading_days)
            rolling_vol = compute_rolling_volatility(daily_rets, window=21, trading_days=self._trading_days)
            rolling_vol_latest = float(rolling_vol.dropna().iloc[-1]) if not rolling_vol.dropna().empty else None

            sharpe = compute_sharpe_ratio(daily_rets, self._risk_free_rate, self._trading_days)
            mdd = compute_max_drawdown(adj_close)

            daily_return_latest = float(daily_rets.dropna().iloc[-1]) if not daily_rets.dropna().empty else None

            return MetricRecord(
                symbol=symbol,
                date=computation_date,
                return_1y=r1y,
                return_6m=r6m,
                return_3m=r3m,
                daily_return=daily_return_latest,
                annualized_volatility=ann_vol,
                rolling_volatility_21d=rolling_vol_latest,
                momentum_score=mom,
                sharpe_ratio=sharpe,
                max_drawdown=mdd,
            )

        except Exception as exc:
            logger.error("Metric computation failed for %s: %s", symbol, exc)
            return None

    def compute_all_metrics(
        self,
        symbols: Optional[list[str]] = None,
        computation_date: Optional[date] = None,
        price_data: Optional[dict[str, pd.DataFrame]] = None,
    ) -> list[MetricRecord]:
        """Compute metrics for all symbols and persist to database.

        Args:
            symbols: List of symbols (defaults to all in the price table).
            computation_date: Date to stamp on the metric rows.
            price_data: Pre-loaded price DataFrames (avoids redundant DB reads).
        """
        computation_date = computation_date or date.today()
        symbols = symbols or self._repo.get_all_symbols_with_prices()

        if not symbols:
            logger.warning("No symbols found in price table")
            return []

        logger.info("Computing metrics for %d symbols (date=%s)", len(symbols), computation_date)

        records: list[MetricRecord] = []
        for symbol in symbols:
            prices = price_data.get(symbol) if price_data else None
            metric = self.compute_metrics_for_symbol(symbol, prices, computation_date)
            if metric:
                records.append(metric)

        if records:
            metrics_df = pd.DataFrame([r.to_dict() for r in records])
            self._repo.upsert_metrics(metrics_df)
            logger.info("Persisted %d metric rows", len(records))

        return records

    def generate_rankings(
        self,
        symbols: Optional[list[str]] = None,
        sector_map: Optional[dict[str, str]] = None,
        computation_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Compute cross-sectional momentum and volatility rankings.

        Rankings are stored in the rankings table and returned as a DataFrame.
        """
        computation_date = computation_date or date.today()

        metrics_df = self._repo.get_latest_metrics(symbols)
        if metrics_df.empty:
            logger.warning("No metrics available for ranking")
            return pd.DataFrame()

        scores = metrics_df.set_index("symbol")["momentum_score"]
        ranks = compute_momentum_rank(scores)
        percentiles = compute_momentum_percentile(scores)

        vol_series = metrics_df.set_index("symbol")["annualized_volatility"].dropna()
        vol_ranks = vol_series.rank(ascending=True, na_option="bottom").astype("Int64")

        rankings_df = metrics_df.copy()
        rankings_df["computation_date"] = computation_date
        rankings_df["sector"] = rankings_df["symbol"].map(sector_map or {})
        rankings_df["momentum_rank"] = rankings_df["symbol"].map(ranks.to_dict())
        rankings_df["momentum_percentile"] = rankings_df["symbol"].map(percentiles.to_dict())
        rankings_df["volatility_rank"] = rankings_df["symbol"].map(vol_ranks.to_dict())
        rankings_df["volatility"] = rankings_df["annualized_volatility"]

        # Keep only ranking columns
        ranking_cols = [
            "computation_date", "symbol", "sector",
            "momentum_score", "momentum_rank", "momentum_percentile",
            "volatility", "volatility_rank",
            "return_1y", "return_6m", "return_3m",
            "sharpe_ratio", "max_drawdown",
        ]
        existing_cols = [c for c in ranking_cols if c in rankings_df.columns]
        rankings_df = rankings_df[existing_cols].sort_values("momentum_rank")

        self._repo.upsert_rankings(rankings_df)
        logger.info("Rankings generated for %d symbols", len(rankings_df))
        return rankings_df

    def get_rolling_volatility_series(
        self,
        symbol: str,
        window: int = 21,
    ) -> pd.DataFrame:
        """Return rolling volatility history for a symbol (for charts)."""
        prices_df = self._repo.get_prices(symbol)
        if prices_df is None or prices_df.empty:
            return pd.DataFrame()

        adj_close = prices_df["adj_close"].dropna()
        daily_rets = compute_daily_returns(adj_close)
        rolling_vol = compute_rolling_volatility(daily_rets, window=window, trading_days=self._trading_days)

        return pd.DataFrame(
            {
                "date": adj_close.index,
                "adj_close": adj_close.values,
                "daily_return": daily_rets.values,
                f"rolling_vol_{window}d": rolling_vol.values,
            }
        ).set_index("date")

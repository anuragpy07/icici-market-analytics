"""Synthetic market data provider for offline development and testing.

Generates deterministic, statistically realistic OHLCV data using
Geometric Brownian Motion (GBM). Each symbol is seeded by a SHA-256
hash of its name so the data is fully reproducible across Python
processes (unlike the built-in hash() which is randomised per-process
by PYTHONHASHSEED).

Design:
  1. GBM is run on the BACKWARD-ADJUSTED (continuous) price series.
  2. Raw close = adj_close / adj_factor, so the raw series correctly
     shows the price *drop* at each split ex-date.
  3. Corporate actions are generated deterministically with a separate
     seeded RNG so they don't consume from the price-path stream.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from src.providers.base import (
    BaseMarketDataProvider,
    CorporateActionData,
    HistoricalBar,
    LiveQuoteData,
)

logger = logging.getLogger(__name__)

# Sector-specific GBM parameters.
# mu: annual log-drift; sigma: annualised volatility; s0_range: starting
# price band in INR for the *adjusted* (most-recent-scale) price.
# Calibrated so simulated 1Y returns span roughly -40% to +80% and
# annualised vol spans 15%-55%, consistent with Nifty 500 empirics.
#   Expected arithmetic 1Y return ≈ exp(mu) - 1
#   P5 / P95 1Y return           ≈ exp(mu ± 2·sigma) - 1
_SECTOR_PARAMS: dict[str, dict] = {
    "Information Technology": {"mu": 0.12, "sigma": 0.26, "s0_range": (800.0,  4500.0)},
    "Financial Services":     {"mu": 0.11, "sigma": 0.28, "s0_range": (400.0,  2500.0)},
    "Consumer Goods":         {"mu": 0.09, "sigma": 0.18, "s0_range": (300.0,  3000.0)},
    "Consumer Staples":       {"mu": 0.08, "sigma": 0.16, "s0_range": (300.0,  3000.0)},
    "Energy":                 {"mu": 0.08, "sigma": 0.24, "s0_range": (150.0,  2800.0)},
    "Healthcare":             {"mu": 0.10, "sigma": 0.22, "s0_range": (400.0,  2000.0)},
    "Materials":              {"mu": 0.08, "sigma": 0.24, "s0_range": (200.0,  1500.0)},
    "Industrials":            {"mu": 0.09, "sigma": 0.21, "s0_range": (200.0,  1800.0)},
    "Consumer Discretionary": {"mu": 0.10, "sigma": 0.24, "s0_range": (300.0,  2500.0)},
    "Utilities":              {"mu": 0.06, "sigma": 0.15, "s0_range": (150.0,   600.0)},
    "Real Estate":            {"mu": 0.09, "sigma": 0.27, "s0_range": (100.0,   800.0)},
    "Communication Services": {"mu": 0.07, "sigma": 0.22, "s0_range": (100.0,   700.0)},
    "default":                {"mu": 0.09, "sigma": 0.22, "s0_range": (200.0,  2000.0)},
}


def _stable_seed(key: str) -> int:
    """Return a deterministic 31-bit seed from a string.

    Uses SHA-256 so the result is identical across Python processes,
    unlike the built-in hash() which is randomised by PYTHONHASHSEED.
    """
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest, 16) % (2**31)


class MockProvider(BaseMarketDataProvider):
    """Offline data provider with GBM-simulated prices.

    All data is deterministic given the same symbol and date range —
    re-running the pipeline always produces identical history.
    """

    def __init__(self, sector_map: Optional[dict[str, str]] = None) -> None:
        self._sector_map: dict[str, str] = sector_map or {}
        self._authenticated = False

    def authenticate(self) -> bool:
        self._authenticated = True
        logger.info("MockProvider authenticated (no credentials required)")
        return True

    def health_check(self) -> bool:
        return self._authenticated

    def get_provider_name(self) -> str:
        return "MockProvider"

    def get_historical_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[HistoricalBar]:
        rng = np.random.default_rng(_stable_seed(symbol))
        params = self._sector_params(symbol)
        dates = pd.bdate_range(start=start_date, end=end_date)

        if len(dates) == 0:
            return []

        date_list = dates.date.tolist()

        # Corporate actions use a separate RNG so they don't consume from
        # the price-path stream (preserves determinism when action count varies).
        corp_actions = self.get_corporate_actions(symbol, start_date, end_date, exchange)

        # Compute backward adj_factors first so the GBM can be run on the
        # *adjusted* (continuous) price series.
        adj_factors = self._build_adj_factors_for_dates(date_list, corp_actions)

        # GBM produces the adj_close series (smooth, no split jumps).
        adj_closes = self._simulate_gbm(rng, params, len(dates))

        # Raw OHLC: open/high/low/close from the same GBM in adj space,
        # then divided by adj_factor to reconstruct the raw market price
        # (which correctly shows price drops at each split ex-date).
        adj_opens, adj_highs, adj_lows, volumes = self._generate_ohlcv_from_closes(
            rng, adj_closes
        )

        bars: list[HistoricalBar] = []
        for i, dt in enumerate(dates):
            af = adj_factors[i]
            raw_close = round(float(adj_closes[i]) / af, 2)
            raw_open  = round(float(adj_opens[i])  / af, 2)
            raw_high  = round(float(adj_highs[i])  / af, 2)
            raw_low   = round(float(adj_lows[i])   / af, 2)

            bars.append(
                HistoricalBar(
                    symbol=symbol,
                    exchange=exchange,
                    date=dt.date(),
                    open=raw_open,
                    high=raw_high,
                    low=raw_low,
                    close=raw_close,
                    volume=int(volumes[i]),
                    adj_close=round(float(adj_closes[i]), 2),
                    adj_factor=af,
                    is_adjusted=True,
                )
            )

        logger.debug("MockProvider generated %d bars for %s", len(bars), symbol)
        return bars

    def get_live_quote(self, symbol: str, exchange: str = "NSE") -> LiveQuoteData:
        """Return a synthetic live quote anchored to today's simulated close."""
        today = date.today()
        rng = np.random.default_rng(_stable_seed(f"{symbol}_live_{today.isoformat()}"))
        params = self._sector_params(symbol)

        yesterday = today - timedelta(days=1)
        recent = self.get_historical_data(symbol, yesterday - timedelta(days=5), yesterday, exchange)
        prev_close = recent[-1].close if recent else 1000.0

        intraday_move = float(rng.normal(0, params["sigma"] / np.sqrt(252)))
        ltp = round(prev_close * (1 + intraday_move), 2)
        spread_pct = float(rng.uniform(0.0005, 0.002))
        bid = round(ltp * (1 - spread_pct / 2), 2)
        ask = round(ltp * (1 + spread_pct / 2), 2)
        intraday_vol = int(float(rng.lognormal(14, 0.5)))

        return LiveQuoteData(
            symbol=symbol,
            ltp=max(ltp, 0.01),
            bid=max(bid, 0.01),
            ask=max(ask, 0.01),
            volume=intraday_vol,
            open=round(prev_close * (1 + float(rng.normal(0, 0.005))), 2),
            high=round(max(ltp, prev_close) * (1 + float(rng.uniform(0, 0.01))), 2),
            low=round(min(ltp, prev_close) * (1 - float(rng.uniform(0, 0.01))), 2),
            prev_close=prev_close,
            timestamp=datetime.now(),
        )

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[CorporateActionData]:
        """Generate 0–2 deterministic corporate actions per year of history."""
        rng = np.random.default_rng(_stable_seed(f"{symbol}_corp"))
        total_days = (end_date - start_date).days
        years = max(total_days / 365.0, 0.0)
        n_actions = int(rng.integers(0, max(1, int(years * 1.5) + 1)))

        actions: list[CorporateActionData] = []
        for _ in range(n_actions):
            offset = int(rng.integers(30, max(31, total_days - 30)))
            ex_date = start_date + timedelta(days=int(offset))
            if ex_date >= end_date:  # pragma: no cover  (guard; offset arithmetic prevents this)
                continue

            if float(rng.random()) < 0.6:
                ratio = float(rng.choice([2.0, 5.0, 10.0]))
                actions.append(
                    CorporateActionData(
                        symbol=symbol,
                        ex_date=ex_date,
                        action_type="SPLIT",
                        ratio=ratio,
                        dividend_amount=0.0,
                        notes=f"Stock split {ratio:.0f}:1",
                    )
                )
            else:
                div_amount = round(float(rng.uniform(1.0, 25.0)), 2)
                actions.append(
                    CorporateActionData(
                        symbol=symbol,
                        ex_date=ex_date,
                        action_type="DIVIDEND",
                        ratio=1.0,
                        dividend_amount=div_amount,
                        notes=f"Dividend INR {div_amount:.2f}",
                    )
                )

        return sorted(actions, key=lambda a: a.ex_date)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _sector_params(self, symbol: str) -> dict:
        sector = self._sector_map.get(symbol, "default")
        return _SECTOR_PARAMS.get(sector, _SECTOR_PARAMS["default"])

    def _simulate_gbm(
        self,
        rng: np.random.Generator,
        params: dict,
        n: int,
    ) -> np.ndarray:
        """Generate a log-normal GBM path representing the backward-adjusted price.

        Uses Ito-corrected drift: loc = (mu - 0.5·sigma²)·dt so that
        E[arithmetic return over T years] = exp(mu·T) - 1.
        """
        mu = params["mu"]
        sigma = params["sigma"]
        s0_lo, s0_hi = params.get("s0_range", (200.0, 2000.0))
        dt = 1.0 / 252

        s0 = float(rng.uniform(s0_lo, s0_hi))
        log_returns = rng.normal(
            loc=(mu - 0.5 * sigma**2) * dt,
            scale=sigma * np.sqrt(dt),
            size=n,
        )
        return s0 * np.exp(np.cumsum(log_returns))

    def _generate_ohlcv_from_closes(
        self,
        rng: np.random.Generator,
        closes: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        n = len(closes)

        opens = np.empty(n)
        opens[0] = closes[0] * (1 + float(rng.normal(0, 0.003)))
        opens[1:] = closes[:-1] * (1 + rng.normal(0, 0.004, n - 1))

        intraday_range = rng.uniform(0.005, 0.025, n)
        highs = np.maximum(opens, closes) * (1 + intraday_range)
        lows  = np.minimum(opens, closes) * (1 - intraday_range)

        base_vol = float(rng.uniform(500_000, 5_000_000))
        volumes = rng.lognormal(np.log(base_vol), 0.6, n).astype(np.int64)
        volumes = np.clip(volumes, 1000, None)

        return opens, highs, lows, volumes

    def _build_adj_factors_for_dates(
        self,
        dates: list[date],
        corp_actions: list[CorporateActionData],
    ) -> list[float]:
        """Compute backward-adjusted cumulative factors per date.

        For splits/bonus: factor = 1 / ratio applied to all bars *before* ex_date.
        For dividends: factor = (1 - div/close_at_ex) applied to bars before ex_date.
        Since GBM generates the *adjusted* price, we need the adj_factor to
        reconstruct raw = adj / factor; dividends use a fixed 2% approximation
        so the factor is date-only (no dependency on price level at that date).
        """
        n = len(dates)
        factors = [1.0] * n

        for action in sorted(corp_actions, key=lambda a: a.ex_date):
            for i, d in enumerate(dates):
                if d >= action.ex_date:
                    if action.action_type in ("SPLIT", "BONUS"):
                        adj = 1.0 / action.ratio
                    elif action.action_type == "DIVIDEND":
                        # Approximate: div adj ≈ 1 - (div / typical_price)
                        # Use a fixed 2% haircut so adj_factor is price-independent.
                        adj = max(1.0 - action.dividend_amount / 500.0, 0.90)
                    else:  # pragma: no cover  (MockProvider only produces SPLIT/DIVIDEND)
                        adj = 1.0

                    for j in range(i):
                        factors[j] *= adj
                    break

        return factors

"""Corporate action data source backed by Yahoo Finance.

The ICICI Direct Breeze API does not expose a corporate actions endpoint.
This module provides splits and dividends for NSE-listed stocks via Yahoo
Finance (yfinance), which uses the `.NS` suffix for NSE equities.

Used by DataFetcher as a fallback when the primary provider returns [].
Requires: pip install yfinance
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from src.providers.base import CorporateActionData

logger = logging.getLogger(__name__)

try:
    import yfinance as yf  # type: ignore[import]
except ImportError:
    yf = None  # type: ignore[assignment]


def fetch_nse_corporate_actions(
    symbol: str,
    start_date: date,
    end_date: date,
    timeout: int = 10,
) -> list[CorporateActionData]:
    """Fetch splits and dividends for an NSE symbol from Yahoo Finance.

    Args:
        symbol:     NSE symbol (e.g. "RELIANCE"). Appended with ".NS" internally.
        start_date: Inclusive start date.
        end_date:   Inclusive end date.
        timeout:    HTTP request timeout in seconds.

    Returns:
        List of CorporateActionData sorted by ex_date ascending.
        Returns [] on any error (network, missing symbol, yfinance unavailable).
    """
    if yf is None:
        logger.debug("yfinance not installed — skipping corporate action fallback")
        return []

    try:
        ticker = yf.Ticker(f"{symbol}.NS")

        actions: list[CorporateActionData] = []

        # ── Splits ────────────────────────────────────────────────────────────
        try:
            splits = ticker.splits
            if splits is not None and not splits.empty:
                for ts, ratio in splits.items():
                    ex_dt = _to_date(ts)
                    if ex_dt is None:
                        continue
                    if not (start_date <= ex_dt <= end_date):
                        continue
                    if ratio <= 0:
                        continue
                    actions.append(
                        CorporateActionData(
                            symbol=symbol,
                            ex_date=ex_dt,
                            action_type="SPLIT",
                            ratio=float(ratio),
                            dividend_amount=0.0,
                            notes=f"Split {ratio:.0f}:1 (source: Yahoo Finance)",
                        )
                    )
        except Exception as exc:
            logger.debug("yfinance splits fetch failed for %s: %s", symbol, exc)

        # ── Dividends ─────────────────────────────────────────────────────────
        try:
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for ts, amount in divs.items():
                    ex_dt = _to_date(ts)
                    if ex_dt is None:
                        continue
                    if not (start_date <= ex_dt <= end_date):
                        continue
                    if amount <= 0:
                        continue
                    actions.append(
                        CorporateActionData(
                            symbol=symbol,
                            ex_date=ex_dt,
                            action_type="DIVIDEND",
                            ratio=1.0,
                            dividend_amount=float(amount),
                            notes=f"Dividend INR {amount:.2f} (source: Yahoo Finance)",
                        )
                    )
        except Exception as exc:
            logger.debug("yfinance dividends fetch failed for %s: %s", symbol, exc)

        actions.sort(key=lambda a: a.ex_date)
        if actions:
            logger.info(
                "yfinance: %d corporate actions for %s (%d splits, %d dividends)",
                len(actions),
                symbol,
                sum(1 for a in actions if a.action_type == "SPLIT"),
                sum(1 for a in actions if a.action_type == "DIVIDEND"),
            )
        return actions

    except Exception as exc:
        logger.warning("yfinance corporate action fetch failed for %s: %s", symbol, exc)
        return []


def _to_date(ts: object) -> Optional[date]:
    """Convert a pandas Timestamp or datetime-like to a plain date."""
    try:
        if hasattr(ts, "date"):
            return ts.date()  # type: ignore[union-attr]
        if isinstance(ts, str):
            return datetime.fromisoformat(ts).date()
        return None
    except Exception:
        return None

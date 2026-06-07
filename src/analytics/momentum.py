"""Momentum score computation.

Formula (per assignment specification):
  momentum_score = 0.4 * return_1y + 0.3 * return_6m + 0.3 * return_3m

The weights emphasise the 12-1 momentum signal (strongest in academic
literature) while maintaining contributions from shorter horizons.

NaN propagation: if any component is NaN (insufficient history), the
composite score is NaN — the symbol is excluded from rankings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_W_1Y = 0.4
_W_6M = 0.3
_W_3M = 0.3


def compute_momentum_score(
    return_1y: float,
    return_6m: float,
    return_3m: float,
) -> float:
    """Weighted composite momentum score.

    Returns NaN if any component return is NaN (insufficient history).
    """
    if any(np.isnan(r) for r in (return_1y, return_6m, return_3m)):
        return float("nan")
    return float(_W_1Y * return_1y + _W_6M * return_6m + _W_3M * return_3m)


def compute_cross_sectional_momentum(
    scores: pd.Series,
    top_n: int = 20,
    bottom_n: int = 20,
) -> dict[str, pd.Series]:
    """Rank all symbols and return top/bottom portfolios.

    Args:
        scores: Series indexed by symbol with momentum scores.
        top_n:  Number of top-ranked symbols to return.
        bottom_n: Number of bottom-ranked symbols to return.

    Returns dict with keys 'top' and 'bottom'.
    """
    valid = scores.dropna().sort_values(ascending=False)
    return {
        "top": valid.head(top_n),
        "bottom": valid.tail(bottom_n).sort_values(),
    }


def compute_momentum_rank(scores: pd.Series) -> pd.Series:
    """Return integer ranks (1 = highest momentum) for all symbols."""
    return scores.rank(ascending=False, na_option="bottom").astype("Int64")


def compute_momentum_percentile(scores: pd.Series) -> pd.Series:
    """Return percentile (0–100) for each symbol's momentum score."""
    return scores.rank(pct=True) * 100

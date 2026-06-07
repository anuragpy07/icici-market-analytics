"""DataFrame formatting utilities for Streamlit display."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def format_returns_table(df: pd.DataFrame) -> pd.DataFrame:
    """Format a metrics/rankings DataFrame for display in Streamlit.

    Converts float columns to human-readable percentages and rounds
    floating-point values to 2 decimal places.
    """
    if df.empty:
        return df

    display = df.copy()

    pct_cols = ["return_1y", "return_6m", "return_3m", "momentum_score",
                "annualized_volatility", "rolling_volatility_21d",
                "volatility", "momentum_percentile", "max_drawdown"]

    for col in pct_cols:
        if col in display.columns:
            if col == "momentum_percentile":
                display[col] = display[col].apply(
                    lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
                )
            else:
                display[col] = display[col].apply(
                    lambda v: f"{v * 100:.2f}%" if pd.notna(v) else "—"
                )

    float_cols = ["sharpe_ratio", "daily_return"]
    for col in float_cols:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: f"{v:.3f}" if pd.notna(v) else "—"
            )

    int_cols = ["momentum_rank", "volatility_rank"]
    for col in int_cols:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: str(int(v)) if pd.notna(v) else "—"
            )

    return display


def format_live_quotes_table(df: pd.DataFrame) -> pd.DataFrame:
    """Format live quote DataFrame for Streamlit display."""
    if df.empty:
        return df

    display = df.copy()

    price_cols = ["ltp", "bid", "ask", "open", "high", "low", "prev_close"]
    for col in price_cols:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: f"₹{v:,.2f}" if pd.notna(v) else "—"
            )

    if "volume" in display.columns:
        display["volume"] = display["volume"].apply(
            lambda v: f"{int(v):,}" if pd.notna(v) else "—"
        )

    if "change" in display.columns:
        display["change"] = display["change"].apply(
            lambda v: f"{'+' if v > 0 else ''}{v:.2f}" if pd.notna(v) else "—"
        )

    if "change_pct" in display.columns:
        display["change_pct"] = display["change_pct"].apply(
            lambda v: f"{'+' if v > 0 else ''}{v:.2f}%" if pd.notna(v) else "—"
        )

    if "timestamp" in display.columns:
        display["timestamp"] = display["timestamp"].apply(
            lambda v: v.strftime("%H:%M:%S") if hasattr(v, "strftime") else str(v)
        )

    return display


def color_returns(val: str) -> str:
    """Streamlit-compatible cell colouring for return columns."""
    if val == "—" or not isinstance(val, str):
        return ""
    try:
        v = float(val.replace("%", ""))
        if v > 0:
            return "color: #16A34A; font-weight: bold"
        elif v < 0:
            return "color: #DC2626; font-weight: bold"
    except ValueError:
        pass
    return ""


def apply_returns_styling(df: pd.DataFrame, pct_cols: Optional[list[str]] = None):
    """Return a Styler with green/red colouring on return columns."""
    default_pct = ["return_1y", "return_6m", "return_3m", "momentum_score", "change_pct", "change"]
    cols_to_colour = pct_cols or default_pct
    existing = [c for c in cols_to_colour if c in df.columns]

    styler = df.style
    for col in existing:
        styler = styler.map(color_returns, subset=[col])
    return styler

"""Volatility Analysis — rolling volatility charts and cross-symbol comparison."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import streamlit as st

from app._bootstrap import ensure_bootstrap
from app.components.charts import (
    plot_price_chart,
    plot_rolling_volatility,
    plot_sector_heatmap,
    plot_volatility_comparison,
)
from config.settings import get_settings
from src.analytics.engine import MetricsEngine
from src.storage.database import Database
from src.storage.repository import Repository

st.set_page_config(page_title="Volatility Analysis", page_icon="📉", layout="wide")
ensure_bootstrap()
st.title("📉 Volatility Analysis")

settings = get_settings()
db = Database(settings.DATABASE_URL)
repo = Repository(db)
engine = MetricsEngine(repo, settings.RISK_FREE_RATE, settings.TRADING_DAYS_PER_YEAR)


@st.cache_data(ttl=60)
def _load_rankings() -> pd.DataFrame:
    return repo.get_latest_rankings()


@st.cache_data(ttl=60)
def _load_symbols() -> list[str]:
    return repo.get_all_symbols_with_prices()


rankings = _load_rankings()
available_symbols = _load_symbols()

if not available_symbols:
    st.warning("No price data available. Run `python run_pipeline.py` first.")
    st.stop()

# ── Symbol selector ───────────────────────────────────────────────────────────
col_sym, col_win = st.columns([3, 1])

with col_sym:
    default_syms = available_symbols[:5] if len(available_symbols) >= 5 else available_symbols
    selected_symbols = st.multiselect(
        "Select symbols to analyse",
        options=available_symbols,
        default=default_syms,
        max_selections=10,
    )

with col_win:
    window = st.selectbox("Rolling window (days)", [10, 21, 42, 63], index=1)

st.markdown("---")

if not selected_symbols:
    st.info("Select at least one symbol above")
    st.stop()

# ── Individual symbol deep-dive ───────────────────────────────────────────────
primary_symbol = st.selectbox(
    "Deep-dive symbol",
    options=selected_symbols,
    index=0,
)


@st.cache_data(ttl=60)
def _get_vol_series(symbol: str, win: int) -> pd.DataFrame:
    return engine.get_rolling_volatility_series(symbol, window=win)


vol_df = _get_vol_series(primary_symbol, window)

col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.plotly_chart(
        plot_rolling_volatility(vol_df, primary_symbol, window),
        use_container_width=True,
    )

with col_chart2:
    prices_df = repo.get_prices(primary_symbol)
    st.plotly_chart(
        plot_price_chart(prices_df.tail(252), primary_symbol, show_volume=True),
        use_container_width=True,
    )

# ── Multi-symbol volatility comparison ────────────────────────────────────────
st.markdown("---")
st.subheader("Volatility Comparison")


@st.cache_data(ttl=60)
def _multi_vol(syms: tuple[str, ...], win: int) -> dict[str, pd.Series]:
    result: dict[str, pd.Series] = {}
    for sym in syms:
        df = engine.get_rolling_volatility_series(sym, window=win)
        col = f"rolling_vol_{win}d"
        if not df.empty and col in df.columns:
            result[sym] = df[col].dropna()
    return result


multi_vol = _multi_vol(tuple(selected_symbols), window)

st.plotly_chart(
    plot_volatility_comparison(multi_vol, window),
    use_container_width=True,
)

# ── Current volatility table ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("Current Volatility Metrics")

if not rankings.empty:
    vol_table = (
        rankings[rankings["symbol"].isin(selected_symbols)]
        .dropna(subset=["volatility"])
        .sort_values("volatility", ascending=False)[
            ["symbol", "sector", "volatility", "volatility_rank",
             "return_1y", "sharpe_ratio", "max_drawdown"]
        ]
    )

    if not vol_table.empty:
        vol_table_fmt = vol_table.copy()
        for col in ["volatility", "return_1y", "max_drawdown"]:
            if col in vol_table_fmt.columns:
                vol_table_fmt[col] = vol_table_fmt[col].apply(
                    lambda v: f"{v * 100:.2f}%" if pd.notna(v) else "—"
                )
        if "sharpe_ratio" in vol_table_fmt.columns:
            vol_table_fmt["sharpe_ratio"] = vol_table_fmt["sharpe_ratio"].apply(
                lambda v: f"{v:.3f}" if pd.notna(v) else "—"
            )

        st.dataframe(vol_table_fmt, use_container_width=True, hide_index=True)

# ── Sector heatmap ────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Sector Volatility Heatmap")

if not rankings.empty and "sector" in rankings.columns:
    st.plotly_chart(
        plot_sector_heatmap(rankings, metric="volatility"),
        use_container_width=True,
    )

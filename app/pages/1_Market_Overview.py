"""Market Overview — universe stats, top gainers and losers."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import streamlit as st

from app._bootstrap import ensure_bootstrap
from app.components.tables import format_returns_table
from config.settings import get_settings
from src.storage.database import Database
from src.storage.repository import Repository

st.set_page_config(page_title="Market Overview", page_icon="📊", layout="wide")
ensure_bootstrap()
st.title("📊 Market Overview")

settings = get_settings()
db = Database(settings.DATABASE_URL)
repo = Repository(db)


@st.cache_data(ttl=60)
def _load_rankings() -> pd.DataFrame:
    return repo.get_latest_rankings()


@st.cache_data(ttl=60)
def _load_live_quotes() -> pd.DataFrame:
    return repo.get_live_quotes()


def _metric_card(label: str, value: str, delta: str | None = None) -> None:
    st.metric(label=label, value=value, delta=delta)


rankings = _load_rankings()
live_quotes = _load_live_quotes()

# ── Header KPIs ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

with col1:
    n_symbols = len(rankings) if not rankings.empty else 0
    _metric_card("Universe Size", f"{n_symbols} stocks")

with col2:
    last_refresh = repo.get_last_api_call_time()
    refresh_str = last_refresh.strftime("%H:%M:%S") if last_refresh else "N/A"
    _metric_card("Latest Refresh", refresh_str)

with col3:
    if not live_quotes.empty and "change_pct" in live_quotes.columns:
        gainers = (live_quotes["change_pct"] > 0).sum()
        _metric_card("Advancing", f"{gainers} stocks")
    else:
        _metric_card("Advancing", "—")

with col4:
    if not live_quotes.empty and "change_pct" in live_quotes.columns:
        losers = (live_quotes["change_pct"] < 0).sum()
        _metric_card("Declining", f"{losers} stocks")
    else:
        _metric_card("Declining", "—")

st.markdown("---")

# ── Gainers / Losers from live quotes ─────────────────────────────────────────
if not live_quotes.empty and "change_pct" in live_quotes.columns:
    col_g, col_l = st.columns(2)

    with col_g:
        st.subheader("🟢 Top Gainers (Today)")
        gainers_df = (
            live_quotes[live_quotes["change_pct"] > 0]
            .sort_values("change_pct", ascending=False)
            .head(10)[["symbol", "ltp", "change", "change_pct"]]
        )
        if not gainers_df.empty:
            styled = gainers_df.style.format(
                {"ltp": "₹{:.2f}", "change": "+{:.2f}", "change_pct": "+{:.2f}%"}
            ).background_gradient(subset=["change_pct"], cmap="Greens")
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("No gainers yet today")

    with col_l:
        st.subheader("🔴 Top Losers (Today)")
        losers_df = (
            live_quotes[live_quotes["change_pct"] < 0]
            .sort_values("change_pct", ascending=True)
            .head(10)[["symbol", "ltp", "change", "change_pct"]]
        )
        if not losers_df.empty:
            styled = losers_df.style.format(
                {"ltp": "₹{:.2f}", "change": "{:.2f}", "change_pct": "{:.2f}%"}
            ).background_gradient(subset=["change_pct"], cmap="Reds_r")
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("No losers yet today")

elif not rankings.empty:
    # Fall back to momentum-based ranking if no live quotes
    col_g, col_l = st.columns(2)

    with col_g:
        st.subheader("🟢 Top Momentum Stocks (Historical)")
        top = (
            rankings.dropna(subset=["momentum_score"])
            .sort_values("momentum_score", ascending=False)
            .head(10)[["symbol", "sector", "momentum_score", "return_1y"]]
        )
        display = format_returns_table(top)
        st.dataframe(display, use_container_width=True, hide_index=True)

    with col_l:
        st.subheader("🔴 Bottom Momentum Stocks (Historical)")
        bottom = (
            rankings.dropna(subset=["momentum_score"])
            .sort_values("momentum_score", ascending=True)
            .head(10)[["symbol", "sector", "momentum_score", "return_1y"]]
        )
        display = format_returns_table(bottom)
        st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.warning(
        "No market data available. Run `python run_pipeline.py` to populate the database."
    )

# ── Sector breakdown ──────────────────────────────────────────────────────────
if not rankings.empty and "sector" in rankings.columns:
    st.markdown("---")
    st.subheader("📂 Sector Breakdown")

    sector_agg = (
        rankings.dropna(subset=["sector", "momentum_score"])
        .groupby("sector")
        .agg(
            stocks=("symbol", "count"),
            avg_momentum=("momentum_score", "mean"),
            avg_vol=("volatility", "mean"),
        )
        .reset_index()
        .sort_values("avg_momentum", ascending=False)
    )

    sector_agg["avg_momentum"] = (sector_agg["avg_momentum"] * 100).round(2)
    sector_agg["avg_vol"] = (sector_agg["avg_vol"] * 100).round(2)
    sector_agg.columns = ["Sector", "# Stocks", "Avg Momentum (%)", "Avg Ann. Vol (%)"]

    st.dataframe(
        sector_agg.style.background_gradient(subset=["Avg Momentum (%)"], cmap="RdYlGn"),
        use_container_width=True,
        hide_index=True,
    )

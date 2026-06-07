"""Momentum Rankings — sortable table with top/bottom 20 and search."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import streamlit as st

from app._bootstrap import ensure_bootstrap
from app.components.charts import plot_momentum_bar
from app.components.tables import format_returns_table, apply_returns_styling
from config.settings import get_settings
from src.storage.database import Database
from src.storage.repository import Repository

st.set_page_config(page_title="Momentum Rankings", page_icon="🚀", layout="wide")
ensure_bootstrap()
st.title("🚀 Momentum Rankings")
st.markdown(
    "Composite momentum score = **0.4 × 1Y return + 0.3 × 6M return + 0.3 × 3M return** "
    "(all return windows exclude the latest month)"
)

settings = get_settings()
db = Database(settings.DATABASE_URL)
repo = Repository(db)


@st.cache_data(ttl=60)
def _load() -> pd.DataFrame:
    return repo.get_latest_rankings()


df = _load()

if df.empty:
    st.warning("No ranking data. Run `python run_pipeline.py` first.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
col_search, col_sector, col_n = st.columns([2, 2, 1])

with col_search:
    search = st.text_input("Search symbol", placeholder="e.g. RELIANCE")

with col_sector:
    sectors = ["All"] + sorted(df["sector"].dropna().unique().tolist())
    selected_sector = st.selectbox("Filter by sector", sectors)

with col_n:
    top_n = st.number_input("Top / Bottom N", min_value=5, max_value=100, value=20)

# Apply filters
filtered = df.copy()
if search:
    filtered = filtered[filtered["symbol"].str.upper().str.contains(search.upper())]
if selected_sector != "All":
    filtered = filtered[filtered["sector"] == selected_sector]

st.markdown("---")

# ── Top N chart ───────────────────────────────────────────────────────────────
tab_top, tab_bottom, tab_all = st.tabs([f"Top {top_n}", f"Bottom {top_n}", "All Symbols"])

with tab_top:
    top_df = (
        filtered.dropna(subset=["momentum_score"])
        .sort_values("momentum_score", ascending=False)
        .head(int(top_n))
    )
    if not top_df.empty:
        st.plotly_chart(
            plot_momentum_bar(top_df, top_n=int(top_n), mode="top"),
            use_container_width=True,
        )
        display_cols = ["symbol", "sector", "momentum_rank", "momentum_score",
                        "return_1y", "return_6m", "return_3m",
                        "annualized_volatility" if "annualized_volatility" in top_df.columns else "volatility",
                        "sharpe_ratio", "max_drawdown"]
        display_cols = [c for c in display_cols if c in top_df.columns]
        st.dataframe(
            apply_returns_styling(format_returns_table(top_df[display_cols])),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No stocks match the current filters")

with tab_bottom:
    bottom_df = (
        filtered.dropna(subset=["momentum_score"])
        .sort_values("momentum_score", ascending=True)
        .head(int(top_n))
    )
    if not bottom_df.empty:
        st.plotly_chart(
            plot_momentum_bar(bottom_df, bottom_n=int(top_n), mode="bottom"),
            use_container_width=True,
        )
        display_cols = ["symbol", "sector", "momentum_rank", "momentum_score",
                        "return_1y", "return_6m", "return_3m",
                        "volatility" if "volatility" in bottom_df.columns else "annualized_volatility",
                        "sharpe_ratio", "max_drawdown"]
        display_cols = [c for c in display_cols if c in bottom_df.columns]
        st.dataframe(
            apply_returns_styling(format_returns_table(bottom_df[display_cols])),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No stocks match the current filters")

with tab_all:
    sort_col = st.selectbox(
        "Sort by",
        ["momentum_rank", "momentum_score", "return_1y", "return_6m",
         "volatility", "sharpe_ratio", "max_drawdown"],
        index=0,
    )
    sort_asc = st.checkbox("Ascending", value=True)

    sort_col_actual = sort_col if sort_col in filtered.columns else "momentum_score"
    all_sorted = filtered.sort_values(sort_col_actual, ascending=sort_asc)

    display_cols = ["symbol", "sector", "momentum_rank", "momentum_score",
                    "return_1y", "return_6m", "return_3m",
                    "volatility", "sharpe_ratio", "max_drawdown"]
    display_cols = [c for c in display_cols if c in all_sorted.columns]

    st.dataframe(
        apply_returns_styling(format_returns_table(all_sorted[display_cols])),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"Showing {len(all_sorted)} symbols")

"""Live Market Monitor — real-time LTP, bid, ask, volume with auto-refresh."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime

import pytz
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from app._bootstrap import ensure_bootstrap
from app.components.tables import format_live_quotes_table
from config.settings import get_settings
from src.storage.database import Database
from src.storage.repository import Repository

st.set_page_config(page_title="Live Monitor", page_icon="🔴", layout="wide")
ensure_bootstrap()

settings = get_settings()
db = Database(settings.DATABASE_URL)
repo = Repository(db)

_IST = pytz.timezone("Asia/Kolkata")

# Auto-refresh every 5 seconds
_refresh_count = st_autorefresh(
    interval=settings.LIVE_REFRESH_INTERVAL_SECONDS * 1000,
    limit=None,
    key="live_monitor_refresh",
)


def _is_market_open() -> bool:
    now = datetime.now(_IST)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(
        hour=settings.MARKET_OPEN_HOUR,
        minute=settings.MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    close_t = now.replace(
        hour=settings.MARKET_CLOSE_HOUR,
        minute=settings.MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )
    return open_t <= now <= close_t


now_ist = datetime.now(_IST)
market_open = _is_market_open()

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("🔴 Live Market Monitor")
    st.caption(f"Auto-refreshes every {settings.LIVE_REFRESH_INTERVAL_SECONDS}s · IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")

with col_status:
    if market_open:
        st.success("🟢 Market OPEN")
    else:
        st.error("🔴 Market CLOSED")
    st.caption(f"Refresh #{_refresh_count}")

st.markdown("---")

# ── Load live quotes ──────────────────────────────────────────────────────────
live_df = repo.get_live_quotes()

if live_df.empty:
    if market_open:
        st.warning(
            "No live quotes in database. The scheduler will populate this "
            "during market hours once the pipeline is running."
        )
    else:
        st.info(
            "Market is currently closed. Live quotes are only fetched during "
            "NSE trading hours (09:15 – 15:30 IST on weekdays).\n\n"
            "Last known quotes are displayed below if available."
        )

    # Try to show any historical quotes as fallback
    all_quotes = repo.get_live_quotes()
    if all_quotes.empty:
        st.stop()
    live_df = all_quotes

# ── Summary KPIs ──────────────────────────────────────────────────────────────
if not live_df.empty and "change_pct" in live_df.columns:
    col1, col2, col3, col4 = st.columns(4)

    gainers = (live_df["change_pct"] > 0).sum()
    losers = (live_df["change_pct"] < 0).sum()
    unchanged = (live_df["change_pct"] == 0).sum()
    total_vol = live_df["volume"].sum() if "volume" in live_df.columns else 0

    col1.metric("Advancing", f"{gainers}", delta=None)
    col2.metric("Declining", f"{losers}", delta=None)
    col3.metric("Unchanged", f"{unchanged}")
    col4.metric("Total Volume", f"{total_vol:,.0f}")

st.markdown("---")

# ── Filters ───────────────────────────────────────────────────────────────────
col_search, col_sort = st.columns([2, 1])
with col_search:
    search = st.text_input("Filter symbol", placeholder="e.g. RELIANCE")
with col_sort:
    sort_by = st.selectbox("Sort by", ["change_pct", "ltp", "volume", "symbol"], index=0)
    sort_asc = st.checkbox("Ascending", value=False)

# ── Live quotes table ─────────────────────────────────────────────────────────
display_df = live_df.copy()

if search:
    display_df = display_df[display_df["symbol"].str.upper().str.contains(search.upper())]

if sort_by in display_df.columns:
    display_df = display_df.sort_values(sort_by, ascending=sort_asc)

# Select display columns
show_cols = ["symbol", "ltp", "change", "change_pct", "bid", "ask",
             "volume", "open", "high", "low", "prev_close", "timestamp"]
show_cols = [c for c in show_cols if c in display_df.columns]

formatted = format_live_quotes_table(display_df[show_cols])

# Style change_pct column
def _colour_change(val: str) -> str:
    if isinstance(val, str) and "%" in val:
        try:
            v = float(val.replace("%", "").replace("+", ""))
            if v > 0:
                return "background-color: rgba(22,163,74,0.15); color: #16A34A; font-weight: bold"
            elif v < 0:
                return "background-color: rgba(220,38,38,0.15); color: #DC2626; font-weight: bold"
        except ValueError:
            pass
    return ""

if "change_pct" in formatted.columns:
    styled = formatted.style.map(_colour_change, subset=["change_pct"])
    if "change" in formatted.columns:
        styled = styled.map(_colour_change, subset=["change"])
    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.dataframe(formatted, use_container_width=True, hide_index=True)

st.caption(f"Showing {len(display_df)} of {len(live_df)} symbols")

# ── Stale data warning ────────────────────────────────────────────────────────
if not live_df.empty and "timestamp" in live_df.columns:
    latest_ts = live_df["timestamp"].max()
    if hasattr(latest_ts, "timestamp"):
        age_seconds = (datetime.now() - latest_ts.replace(tzinfo=None)).total_seconds()
        if age_seconds > 60:
            st.warning(
                f"⚠️ Data may be stale — last quote received {age_seconds:.0f}s ago. "
                "Ensure the scheduler is running."
            )

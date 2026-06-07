"""Streamlit application entry point — Home / navigation hub."""
from __future__ import annotations

import os
import sys

# Ensure repo root is on sys.path regardless of cwd (local, Docker, Streamlit Cloud)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="ICICI Market Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app._bootstrap import ensure_bootstrap, _run_bootstrap as _bootstrap  # noqa: E402
from config.settings import get_settings, setup_logging  # noqa: E402

settings = get_settings()
setup_logging(settings)


def _sidebar_info(bootstrap: dict) -> None:
    st.sidebar.title("📈 Market Analytics")
    st.sidebar.markdown("---")

    # ── Provider status banner ─────────────────────────────────────────────
    provider = settings.MARKET_DATA_PROVIDER.upper()
    if settings.is_icici_provider:
        if settings.icici_credentials_present:
            st.sidebar.success(f"🟢 **{provider}** — Live data")
            st.sidebar.caption("Session: credentials present")
        else:
            st.sidebar.warning(f"🟡 **{provider}** → using MockProvider")
            st.sidebar.caption("Session: credentials missing — set in .env")
    elif settings.is_yfinance_provider:
        st.sidebar.success("🟢 **YFINANCE** — Live NSE data")
        st.sidebar.caption("Real NSE prices via Yahoo Finance")
    else:
        st.sidebar.info(f"🔵 **{provider}** — Demo mode")
        st.sidebar.caption("No credentials required")

    # Last successful data refresh
    if bootstrap.get("timestamp"):
        st.sidebar.caption(f"Last pipeline run: {bootstrap['timestamp']}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Universe:** Nifty 500")
    st.sidebar.markdown(f"**Risk-Free Rate:** {settings.RISK_FREE_RATE * 100:.1f}%")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Pages**\n"
        "- 📊 Market Overview\n"
        "- 🚀 Momentum Rankings\n"
        "- 📉 Volatility Analysis\n"
        "- 🔴 Live Monitor\n"
        "- ✅ Data Quality"
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(bootstrap["message"])


_bootstrap_result = ensure_bootstrap()

_sidebar_info(_bootstrap_result)

st.title("ICICI Direct Market Analytics System")
st.markdown(
    """
    A **production-grade** live market analytics platform for Indian equities
    (Nifty 500 universe), powered by ICICI Direct Breeze APIs.
    """
)

col1, col2, col3 = st.columns(3)
col1.info("📊 **Market Overview**\nTop gainers, losers, and universe stats")
col2.info("🚀 **Momentum Rankings**\nTop/Bottom 20 by composite momentum score")
col3.info("📉 **Volatility Analysis**\nRolling volatility charts and comparisons")

col4, col5, _ = st.columns(3)
col4.info("🔴 **Live Monitor**\nReal-time LTP, bid/ask, volume — auto-refresh 5s")
col5.info("✅ **Data Quality**\nValidation failures, missing data, API health")

_provider_row = {
    "icici": "ICICI Direct Breeze Connect",
    "yfinance": "Yahoo Finance — real NSE data (yfinance)",
    "mock": "MockProvider (GBM simulation)",
}.get(settings.MARKET_DATA_PROVIDER, "MockProvider")

_provider_note = {
    "icici": "> **Live ICICI mode** — authenticated via Breeze Connect API.",
    "yfinance": "> **Live NSE data** — real prices via Yahoo Finance. "
                "Switch to ICICI by setting `MARKET_DATA_PROVIDER=icici` and adding Breeze credentials.",
    "mock": "> **Running in MockProvider mode** — switch to ICICI by setting "
            "`MARKET_DATA_PROVIDER=icici` and adding credentials in `.env`.",
}.get(settings.MARKET_DATA_PROVIDER, "")

st.markdown("---")
st.markdown(
    f"""
    ### Architecture
    | Layer | Technology |
    |---|---|
    | Data Provider | {_provider_row} |
    | Storage | SQLite + SQLAlchemy ORM |
    | Cache | In-memory TTL cache (15 min historical / 15 s live) |
    | Scheduling | APScheduler (background thread) |
    | Analytics | Custom quant engine (pandas / numpy) |
    | Dashboard | Streamlit + Plotly |

    {_provider_note}
    """
)

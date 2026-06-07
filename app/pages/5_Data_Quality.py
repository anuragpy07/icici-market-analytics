"""Data Quality Dashboard — validation failures, missing data, API health."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from app._bootstrap import ensure_bootstrap
from config.settings import get_settings
from src.storage.database import Database
from src.storage.repository import Repository

st.set_page_config(page_title="Data Quality", page_icon="✅", layout="wide")
ensure_bootstrap()
st.title("✅ Data Quality Dashboard")

settings = get_settings()
db = Database(settings.DATABASE_URL)
repo = Repository(db)


@st.cache_data(ttl=120)
def _load_validation() -> pd.DataFrame:
    return repo.get_validation_summary()


@st.cache_data(ttl=60)
def _last_api_call() -> datetime | None:
    return repo.get_last_api_call_time()


validation_df = _load_validation()
last_api = _last_api_call()

# ── Health KPIs ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

if not validation_df.empty:
    total = len(validation_df)
    passed = (validation_df["status"] == "PASS").sum()
    failed = (validation_df["status"] == "FAIL").sum()
    warned = (validation_df["status"] == "WARN").sum()
    pass_rate = passed / total * 100 if total > 0 else 0

    col1.metric("Total Checks", f"{total:,}")
    col2.metric("Passed", f"{passed:,}", delta=f"{pass_rate:.1f}%")
    col3.metric("Failed", f"{failed:,}", delta=f"-{failed}" if failed > 0 else "0", delta_color="inverse")
    col4.metric("Warnings", f"{warned:,}", delta=None)
else:
    col1.metric("Total Checks", "—")
    col2.metric("Passed", "—")
    col3.metric("Failed", "—")
    col4.metric("Warnings", "—")

# ── API Health ────────────────────────────────────────────────────────────────
st.markdown("---")
col_api1, col_api2 = st.columns(2)

with col_api1:
    st.subheader("🌐 API Health")
    if settings.MARKET_DATA_PROVIDER == "mock":
        st.success("✅ Mock mode — pipeline ran successfully (no real API calls)")
        if last_api:
            st.caption(f"Last pipeline run: {last_api.strftime('%Y-%m-%d %H:%M:%S')}")
    elif last_api:
        age = (datetime.now() - last_api.replace(tzinfo=None)).total_seconds()
        if age < 300:
            st.success(f"✅ Last successful API call: {last_api.strftime('%Y-%m-%d %H:%M:%S')} ({age:.0f}s ago)")
        elif age < 1800:
            st.warning(f"⚠️ Last successful API call: {last_api.strftime('%Y-%m-%d %H:%M:%S')} ({age / 60:.1f} min ago)")
        else:
            st.error(f"❌ Last successful API call: {last_api.strftime('%Y-%m-%d %H:%M:%S')} ({age / 3600:.1f}h ago)")
    else:
        st.info("No API calls recorded yet. Run the pipeline first.")

with col_api2:
    st.subheader("🗄️ Database Health")
    db_ok = db.health_check()
    if db_ok:
        st.success("✅ Database connection healthy")
    else:
        st.error("❌ Database connection failed")

    provider_name = settings.MARKET_DATA_PROVIDER.upper()
    provider_desc = {
        "MOCK": "offline mode — no real API calls",
        "YFINANCE": "live NSE data via Yahoo Finance",
        "ICICI": "live ICICI Direct Breeze integration",
    }.get(provider_name, provider_name.lower())
    st.info(f"📡 Provider: **{provider_name}** ({provider_desc})")

st.markdown("---")

# ── Validation failures breakdown ─────────────────────────────────────────────
if validation_df.empty:
    st.info("No validation data found. Run `python run_pipeline.py` to generate reports.")
    st.stop()

st.subheader("🔍 Validation Results")

# Summary by check type
check_summary = (
    validation_df.groupby(["check_name", "status"])
    .size()
    .reset_index(name="count")
)

col_chart, col_table = st.columns([1, 1])

with col_chart:
    status_counts = validation_df["status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]
    color_map = {"PASS": "#16A34A", "FAIL": "#DC2626", "WARN": "#D97706"}
    fig = px.pie(
        status_counts,
        values="Count",
        names="Status",
        color="Status",
        color_discrete_map=color_map,
        title="Check Status Distribution",
    )
    fig.update_layout(height=300, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

with col_table:
    pivot = (
        check_summary.pivot(index="check_name", columns="status", values="count")
        .fillna(0)
        .astype(int)
        .reset_index()
    )
    pivot.columns.name = None
    st.dataframe(pivot, use_container_width=True, hide_index=True)

st.markdown("---")

# ── Symbols with failures ──────────────────────────────────────────────────────
st.subheader("⚠️ Symbols with Failures")
failed_symbols = (
    validation_df[validation_df["status"] == "FAIL"]
    .groupby("symbol")
    .agg(
        failure_count=("failure_count", "sum"),
        failed_checks=("check_name", lambda x: ", ".join(x.unique())),
    )
    .reset_index()
    .sort_values("failure_count", ascending=False)
)

if not failed_symbols.empty:
    st.dataframe(failed_symbols, use_container_width=True, hide_index=True)
else:
    st.success("✅ No symbols with FAIL-level validation errors")

# ── Missing data counts ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📅 Missing Data Summary")

missing_data = validation_df[
    validation_df["check_name"] == "missing_dates"
].copy()

if not missing_data.empty:
    missing_data["failure_count"] = pd.to_numeric(missing_data["failure_count"], errors="coerce")
    top_missing = missing_data.sort_values("failure_count", ascending=False).head(20)
    top_missing_display = top_missing[["symbol", "status", "failure_count", "details"]].copy()
    top_missing_display.columns = ["Symbol", "Status", "Missing Days", "Details"]

    st.dataframe(top_missing_display, use_container_width=True, hide_index=True)
else:
    st.info("No missing date information available")

# ── JSON report download ───────────────────────────────────────────────────────
st.markdown("---")


@st.cache_data(ttl=120)
def _read_report_json(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


report_json = _read_report_json("data/validation_report.json")
if report_json:
    st.download_button(
        label="📥 Download Validation Report (JSON)",
        data=report_json,
        file_name="validation_report.json",
        mime="application/json",
    )
else:
    st.caption("Validation report JSON will appear here after running the pipeline")

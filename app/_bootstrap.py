"""Shared bootstrap — ensures the data pipeline has run before any page renders.

Import and call ensure_bootstrap() at the top of every page script so that
navigating directly to a sub-page (skipping app/main.py) still populates the DB.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _db_is_ready(db_path: str) -> bool:
    """Return True only when both prices AND rankings tables have data."""
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        prices = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        rankings = conn.execute("SELECT COUNT(*) FROM rankings").fetchone()[0]
        conn.close()
        return prices > 0 and rankings > 0
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _run_bootstrap() -> dict:
    """Run the pipeline once per server process until both prices AND rankings exist.

    Checking only prices was insufficient — if a previous run wrote prices but
    crashed before computing rankings, the bootstrap would skip re-running and
    all dashboard pages would show 'No data'.
    """
    data_dir = os.path.join(_ROOT, "data")
    logs_dir = os.path.join(_ROOT, "logs")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    db_path = os.path.join(data_dir, "market_data.db")

    if not _db_is_ready(db_path):
        limit = int(os.environ.get("UNIVERSE_SIZE_LIMIT", "20")) or 20
        result = subprocess.run(
            [sys.executable, os.path.join(_ROOT, "run_pipeline.py"), "--limit", str(limit)],
            capture_output=True,
            text=True,
            cwd=_ROOT,
            timeout=600,  # 10-minute hard cap for cloud environments
        )
        return {
            "message": f"Bootstrap complete (exit {result.returncode}, {limit} symbols)",
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "rows": 0,
        }

    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        conn.close()
    except Exception:
        rows = 0

    return {
        "message": f"Database ready ({rows:,} price rows)",
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "rows": rows,
    }


def ensure_bootstrap() -> dict:
    """Call from any page to guarantee data exists before rendering.

    After a fresh pipeline run, clears all @st.cache_data caches so every
    page reloads its queries from the newly populated database rather than
    returning stale empty results cached before the pipeline completed.
    """
    db_path = os.path.join(_ROOT, "data", "market_data.db")
    was_ready = _db_is_ready(db_path)

    with st.spinner("Initialising data pipeline — first load takes ~30 s…"):
        result = _run_bootstrap()

    # If the pipeline just ran (DB wasn't ready before), flush all query caches
    # so pages don't serve stale empty DataFrames cached before the pipeline ran.
    if not was_ready:
        st.cache_data.clear()

    return result

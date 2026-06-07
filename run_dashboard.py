#!/usr/bin/env python3
"""run_dashboard.py — Launch the Streamlit dashboard with optional background pipeline.

Usage:
    python run_dashboard.py                  # Dashboard only (reads from DB)
    python run_dashboard.py --run-pipeline   # Run pipeline first, then launch dashboard
    python run_dashboard.py --port 8502      # Custom port
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_pipeline_first(limit: int) -> None:
    """Run the data pipeline synchronously before launching the dashboard."""
    cmd = [sys.executable, "run_pipeline.py"]
    if limit:
        cmd += ["--limit", str(limit)]
    print(f"Running pipeline: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("WARNING: Pipeline exited with errors. Dashboard may show incomplete data.")


def launch_dashboard(port: int) -> None:
    """Launch the Streamlit multi-page application."""
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        "app/main.py",
        f"--server.port={port}",
        "--server.headless=true",   # required for cloud / Docker / CI
        "--server.runOnSave=false",
        # Theme is set via .streamlit/config.toml so cloud picks it up too
    ]
    print(f"\nLaunching dashboard on http://localhost:{port}")
    print("Press Ctrl+C to stop.\n")
    os.execv(sys.executable, cmd)  # Replace current process with Streamlit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ICICI Market Analytics Dashboard")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8501)),
        help="Streamlit port (default: 8501, or $PORT env var for cloud/Render)",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run the data pipeline before launching the dashboard",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Symbol limit when --run-pipeline is used (default: 20 for quick start)",
    )
    args = parser.parse_args()

    if args.run_pipeline:
        run_pipeline_first(args.limit)

    launch_dashboard(args.port)

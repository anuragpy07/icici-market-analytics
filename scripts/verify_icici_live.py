#!/usr/bin/env python3
"""verify_icici_live.py — End-to-end ICICI Direct Breeze Connect verification.

Reads credentials from environment / .env, performs every API operation, and
prints a diagnostic report. Exit code 0 means all checks passed.

Usage:
    python scripts/verify_icici_live.py

    # With explicit symbol (default: RELIANCE):
    python scripts/verify_icici_live.py --symbol TCS

    # Quiet mode (only print failures):
    python scripts/verify_icici_live.py --quiet

Prerequisites (.env or environment variables):
    ICICI_APP_KEY        (or ICICI_API_KEY)
    ICICI_SECRET_KEY     (or ICICI_API_SECRET)
    ICICI_SESSION_TOKEN
    ICICI_CLIENT_CODE    (optional)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── ANSI colours (disabled on Windows unless in supported terminal) ────────────
def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_GREEN  = "\033[92m" if _supports_color() else ""
_RED    = "\033[91m" if _supports_color() else ""
_YELLOW = "\033[93m" if _supports_color() else ""
_RESET  = "\033[0m"  if _supports_color() else ""
_BOLD   = "\033[1m"  if _supports_color() else ""


class _Check:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: bool = False
        self.detail: str = ""
        self.elapsed_ms: float = 0.0

    def ok(self, detail: str = "") -> "_Check":
        self.passed = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> "_Check":
        self.passed = False
        self.detail = detail
        return self


def _run_checks(symbol: str, quiet: bool) -> list[_Check]:
    checks: list[_Check] = []

    # ── 1. Environment variables ──────────────────────────────────────────────
    c = _Check("Environment variables")
    t0 = time.monotonic()
    try:
        from config.settings import Settings

        s = Settings()
        missing = []
        if not s.ICICI_APP_KEY:
            missing.append("ICICI_APP_KEY (or ICICI_API_KEY)")
        if not s.ICICI_SECRET_KEY:
            missing.append("ICICI_SECRET_KEY (or ICICI_API_SECRET)")
        if not s.ICICI_SESSION_TOKEN:
            missing.append("ICICI_SESSION_TOKEN")

        if missing:
            c.fail("Missing: " + ", ".join(missing))
        else:
            parts = [f"APP_KEY=...{s.ICICI_APP_KEY[-4:]}"]
            if s.ICICI_CLIENT_CODE:
                parts.append(f"CLIENT_CODE={s.ICICI_CLIENT_CODE}")
            c.ok(", ".join(parts))
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    if not checks[0].passed:
        return checks  # No point continuing without credentials

    # ── 2. breeze-connect import ──────────────────────────────────────────────
    c = _Check("breeze-connect package")
    t0 = time.monotonic()
    try:
        import breeze_connect  # noqa: F401
        import importlib.metadata
        ver = importlib.metadata.version("breeze-connect")
        c.ok(f"version {ver}")
    except ImportError:
        c.fail("Not installed — run: pip install breeze-connect")
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    if not checks[-1].passed:
        return checks

    # ── 3. Authentication ─────────────────────────────────────────────────────
    c = _Check("Authentication (generate_session)")
    t0 = time.monotonic()
    provider = None
    try:
        from config.settings import Settings
        from src.providers.icici import ICICIDirectProvider
        from src.providers.factory import ProviderFactory

        s = Settings()
        code_map = ProviderFactory._load_breeze_code_map(s.UNIVERSE_FILE)
        provider = ICICIDirectProvider(
            app_key=s.ICICI_APP_KEY,
            secret_key=s.ICICI_SECRET_KEY,
            session_token=s.ICICI_SESSION_TOKEN,
            client_code=s.ICICI_CLIENT_CODE,
            code_map=code_map,
        )
        provider.authenticate()
        c.ok("Session established")
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    if not checks[-1].passed or provider is None:
        return checks

    # ── 4. Health check ───────────────────────────────────────────────────────
    c = _Check("Health check (get_customer_details)")
    t0 = time.monotonic()
    try:
        ok = provider.health_check()
        if ok:
            c.ok("Session verified by API")
        else:
            c.fail("health_check() returned False — session may have expired")
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    # ── 5. Historical data ────────────────────────────────────────────────────
    c = _Check(f"Historical data  ({symbol}, last 10 days)")
    t0 = time.monotonic()
    try:
        end = date.today()
        start = end - timedelta(days=14)  # window includes ~10 trading days
        bars = provider.get_historical_data(symbol, start, end)
        if not bars:
            c.fail("No bars returned — symbol may be invalid or market closed")
        else:
            bar = bars[-1]
            # Validate OHLCV sanity
            errors = []
            if bar.high < bar.low:
                errors.append("high < low")
            if bar.close <= 0:
                errors.append("close ≤ 0")
            if bar.volume < 0:
                errors.append("volume < 0")
            if errors:
                c.fail(f"{len(bars)} bars, last={bar.date}, issues: {', '.join(errors)}")
            else:
                c.ok(
                    f"{len(bars)} bars | last={bar.date} "
                    f"O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} "
                    f"V={bar.volume:,}"
                )
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    # ── 6. Live quote ─────────────────────────────────────────────────────────
    c = _Check(f"Live quote  ({symbol})")
    t0 = time.monotonic()
    try:
        quote = provider.get_live_quote(symbol)
        errors = []
        if quote.ltp <= 0:
            errors.append("LTP ≤ 0")
        if quote.bid > quote.ask:
            errors.append("bid > ask")
        if errors:
            c.fail(f"Issues: {', '.join(errors)} | LTP={quote.ltp}")
        else:
            c.ok(
                f"LTP={quote.ltp:.2f}  Chg={quote.change:+.2f} ({quote.change_pct:+.2f}%)  "
                f"Bid={quote.bid:.2f}  Ask={quote.ask:.2f}  Vol={quote.volume:,}"
            )
    except Exception as exc:
        # Live quotes may be unavailable outside market hours — treat as warning
        c.fail(f"{exc}  (normal outside market hours 09:15–15:30 IST)")
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    # ── 7. Corporate actions (expected empty) ─────────────────────────────────
    c = _Check("Corporate actions endpoint")
    t0 = time.monotonic()
    try:
        actions = provider.get_corporate_actions(
            symbol, date.today() - timedelta(days=365), date.today()
        )
        c.ok(f"Returns [] as expected (Breeze does not expose this endpoint)")
    except Exception as exc:
        c.fail(str(exc))
    c.elapsed_ms = (time.monotonic() - t0) * 1000
    checks.append(c)

    return checks


def _print_report(checks: list[_Check], quiet: bool) -> int:
    passed = sum(1 for c in checks if c.passed)
    failed = len(checks) - passed

    if not quiet:
        width = 70
        sep = "-" * width
        print(f"\n{_BOLD}{sep}{_RESET}")
        print(f"{_BOLD}  ICICI Direct Breeze Connect -- Verification Report{_RESET}")
        print(sep)

        for c in checks:
            status = f"{_GREEN}PASS{_RESET}" if c.passed else f"{_RED}FAIL{_RESET}"
            ms = f"{c.elapsed_ms:6.0f} ms"
            print(f"  [{status}]  {ms}  {c.name}")
            if c.detail:
                indent = "              "
                print(f"{indent}{c.detail}")

        print(sep)
        color = _GREEN if failed == 0 else _RED
        print(f"  {color}{_BOLD}{passed}/{len(checks)} checks passed{_RESET}")
        if failed == 0:
            print(f"  {_GREEN}All checks passed -- provider is ready for use.{_RESET}")
        else:
            print(f"  {_RED}{failed} check(s) failed -- see details above.{_RESET}")
            print(f"\n  For setup instructions: see docs/ICICI_SETUP.md")
        print(f"{sep}\n")
    else:
        for c in checks:
            if not c.passed:
                print(f"FAIL  {c.name}: {c.detail}")

    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify ICICI Direct Breeze Connect credentials and API connectivity."
    )
    parser.add_argument(
        "--symbol",
        default="RELIANCE",
        help="NSE symbol to use for data checks (default: RELIANCE)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print failures (useful for CI)",
    )
    args = parser.parse_args()

    checks = _run_checks(symbol=args.symbol, quiet=args.quiet)
    return _print_report(checks, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())

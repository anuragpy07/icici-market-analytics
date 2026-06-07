"""Data quality validation with structured reporting.

Each check returns a ValidationResult. The aggregated report is saved to
the database AND serialised to data/validation_report.json for inspection.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_OUTLIER_RETURN_THRESHOLD = 0.50  # Flag daily returns > 50%
_STALE_LIVE_QUOTE_SECONDS = 300  # 5 minutes


@dataclass
class ValidationResult:
    """Outcome of a single data quality check."""

    symbol: str
    check_name: str
    status: str  # PASS | FAIL | WARN
    failure_count: int = 0
    details: Optional[dict[str, Any]] = field(default=None)
    report_date: date = field(default_factory=date.today)

    def to_db_record(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date,
            "symbol": self.symbol,
            "check_name": self.check_name,
            "status": self.status,
            "failure_count": self.failure_count,
            "details": json.dumps(self.details) if self.details else None,
        }


class DataValidator:
    """Runs a battery of data quality checks on OHLCV DataFrames.

    Design: checks are pure functions — no side effects. Persistence
    is handled by the calling layer (pipeline or fetcher).
    """

    def validate_historical(
        self,
        df: pd.DataFrame,
        symbol: str,
        report_date: Optional[date] = None,
    ) -> list[ValidationResult]:
        """Run all historical data checks. Returns one result per check."""
        report_date = report_date or date.today()
        results = []

        checks = [
            self._check_duplicate_timestamps,
            self._check_negative_prices,
            self._check_zero_prices,
            self._check_negative_volumes,
            self._check_null_prices,
            self._check_outlier_returns,
            self._check_missing_dates,
        ]

        for check_fn in checks:
            try:
                result = check_fn(df, symbol, report_date)
                results.append(result)
            except Exception as exc:
                logger.error("Check %s failed for %s: %s", check_fn.__name__, symbol, exc)
                results.append(
                    ValidationResult(
                        symbol=symbol,
                        check_name=check_fn.__name__.lstrip("_check_"),
                        status="WARN",
                        failure_count=0,
                        details={"error": str(exc)},
                        report_date=report_date,
                    )
                )

        pass_count = sum(1 for r in results if r.status == "PASS")
        fail_count = sum(1 for r in results if r.status == "FAIL")
        logger.debug(
            "Validation for %s: %d PASS, %d FAIL / %d total checks",
            symbol,
            pass_count,
            fail_count,
            len(results),
        )
        return results

    def validate_live_quote(
        self,
        quote: dict[str, Any],
        symbol: str,
        report_date: Optional[date] = None,
    ) -> list[ValidationResult]:
        """Validate a live quote snapshot."""
        report_date = report_date or date.today()
        results = []

        # Check staleness
        ts = quote.get("timestamp")
        if ts:
            ts_naive = ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
            age_seconds = (datetime.now() - ts_naive).total_seconds()
            is_stale = age_seconds > _STALE_LIVE_QUOTE_SECONDS
            results.append(
                ValidationResult(
                    symbol=symbol,
                    check_name="stale_live_data",
                    status="FAIL" if is_stale else "PASS",
                    failure_count=1 if is_stale else 0,
                    details={"age_seconds": round(age_seconds, 1)},
                    report_date=report_date,
                )
            )

        # Check LTP validity
        ltp = quote.get("ltp", 0)
        results.append(
            ValidationResult(
                symbol=symbol,
                check_name="invalid_ltp",
                status="FAIL" if ltp <= 0 else "PASS",
                failure_count=1 if ltp <= 0 else 0,
                details={"ltp": ltp},
                report_date=report_date,
            )
        )

        return results

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_duplicate_timestamps(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        dupes = df.index.duplicated().sum()
        return ValidationResult(
            symbol=symbol,
            check_name="duplicate_timestamps",
            status="FAIL" if dupes > 0 else "PASS",
            failure_count=int(dupes),
            details={"duplicate_count": int(dupes)},
            report_date=report_date,
        )

    def _check_negative_prices(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        cols = [c for c in ["open", "high", "low", "close", "adj_close"] if c in df.columns]
        neg_mask = (df[cols] < 0).any(axis=1)
        count = int(neg_mask.sum())
        return ValidationResult(
            symbol=symbol,
            check_name="negative_prices",
            status="FAIL" if count > 0 else "PASS",
            failure_count=count,
            details={"negative_row_count": count},
            report_date=report_date,
        )

    def _check_zero_prices(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        if "close" not in df.columns:
            return ValidationResult(symbol=symbol, check_name="zero_prices", status="WARN", report_date=report_date)
        count = int((df["close"] == 0).sum())
        return ValidationResult(
            symbol=symbol,
            check_name="zero_prices",
            status="FAIL" if count > 0 else "PASS",
            failure_count=count,
            details={"zero_close_count": count},
            report_date=report_date,
        )

    def _check_negative_volumes(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        if "volume" not in df.columns:
            return ValidationResult(symbol=symbol, check_name="negative_volumes", status="WARN", report_date=report_date)
        count = int((pd.to_numeric(df["volume"], errors="coerce").fillna(0) < 0).sum())
        return ValidationResult(
            symbol=symbol,
            check_name="negative_volumes",
            status="FAIL" if count > 0 else "PASS",
            failure_count=count,
            details={"negative_volume_count": count},
            report_date=report_date,
        )

    def _check_null_prices(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        if "close" not in df.columns:
            return ValidationResult(symbol=symbol, check_name="null_prices", status="WARN", report_date=report_date)
        count = int(df["close"].isna().sum())
        return ValidationResult(
            symbol=symbol,
            check_name="null_prices",
            status="FAIL" if count > 0 else "PASS",
            failure_count=count,
            details={"null_close_count": count},
            report_date=report_date,
        )

    def _check_outlier_returns(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        if "adj_close" not in df.columns or len(df) < 2:
            return ValidationResult(symbol=symbol, check_name="outlier_returns", status="WARN", report_date=report_date)

        returns = df["adj_close"].pct_change().dropna()
        outliers = returns[returns.abs() > _OUTLIER_RETURN_THRESHOLD]
        count = len(outliers)

        details: dict[str, Any] = {"outlier_count": count}
        if count > 0:
            details["worst_return"] = float(outliers.abs().max())
            details["worst_date"] = str(outliers.abs().idxmax())

        return ValidationResult(
            symbol=symbol,
            check_name="outlier_returns",
            status="WARN" if count > 0 else "PASS",
            failure_count=count,
            details=details,
            report_date=report_date,
        )

    def _check_missing_dates(
        self, df: pd.DataFrame, symbol: str, report_date: date
    ) -> ValidationResult:
        if df.empty:
            return ValidationResult(symbol=symbol, check_name="missing_dates", status="WARN", report_date=report_date)

        start = pd.to_datetime(df.index.min())
        end = pd.to_datetime(df.index.max())
        expected = len(pd.bdate_range(start, end))
        actual = len(df)
        missing = max(0, expected - actual)
        pct_missing = missing / expected * 100 if expected > 0 else 0

        return ValidationResult(
            symbol=symbol,
            check_name="missing_dates",
            status="FAIL" if pct_missing > 5 else ("WARN" if pct_missing > 0 else "PASS"),
            failure_count=missing,
            details={
                "expected_trading_days": expected,
                "actual_days": actual,
                "missing_days": missing,
                "pct_missing": round(pct_missing, 2),
            },
            report_date=report_date,
        )

    # ── Report generation ─────────────────────────────────────────────────────

    @staticmethod
    def generate_json_report(
        all_results: dict[str, list[ValidationResult]],
        output_path: str = "data/validation_report.json",
    ) -> dict[str, Any]:
        """Aggregate all validation results and write to JSON file."""
        total_checks = sum(len(v) for v in all_results.values())
        passed = sum(1 for results in all_results.values() for r in results if r.status == "PASS")
        failed = sum(1 for results in all_results.values() for r in results if r.status == "FAIL")
        warned = sum(1 for results in all_results.values() for r in results if r.status == "WARN")

        symbols_with_failures = [
            sym
            for sym, results in all_results.items()
            if any(r.status == "FAIL" for r in results)
        ]

        # Most common failure type
        failure_counts: dict[str, int] = {}
        for results in all_results.values():
            for r in results:
                if r.status == "FAIL":
                    failure_counts[r.check_name] = failure_counts.get(r.check_name, 0) + 1

        most_common_failure = (
            max(failure_counts, key=failure_counts.get) if failure_counts else None  # type: ignore
        )

        report: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "universe_size": len(all_results),
            "total_checks": total_checks,
            "passed_checks": passed,
            "failed_checks": failed,
            "warned_checks": warned,
            "pass_rate_pct": round(passed / total_checks * 100, 2) if total_checks else 0,
            "symbols_with_failures": symbols_with_failures,
            "most_common_failure": most_common_failure,
            "by_symbol": {
                sym: {
                    "overall_status": (
                        "FAIL"
                        if any(r.status == "FAIL" for r in results)
                        else "WARN"
                        if any(r.status == "WARN" for r in results)
                        else "PASS"
                    ),
                    "checks": [
                        {
                            "name": r.check_name,
                            "status": r.status,
                            "failure_count": r.failure_count,
                            "details": r.details,
                        }
                        for r in results
                    ],
                }
                for sym, results in all_results.items()
            },
        }

        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Validation report written to %s", output_path)
        except Exception as exc:
            logger.warning("Could not write validation report: %s", exc)

        return report

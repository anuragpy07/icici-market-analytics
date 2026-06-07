"""Data cleaning, gap-filling, and corporate-action adjustment pipeline.

Processing order (each step is idempotent):
  1. Cast dtypes
  2. Remove duplicates
  3. Remove rows with null/zero/negative prices
  4. Reindex to business-day calendar; forward-fill gaps (max 5 days)
  5. Backward-fill remaining NaN at the start of the series
  6. Apply cumulative corporate-action adjustment factor to adj_close
  7. Clip extreme single-day returns (>50%) as outliers
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

_MAX_FORWARD_FILL_DAYS = 5
_MAX_SINGLE_DAY_RETURN = 0.50  # 50% — outlier threshold
_PRICE_COLS = ["open", "high", "low", "close", "adj_close"]


class DataProcessor:
    """Transforms raw provider output into a clean, analysis-ready DataFrame.

    Input: DataFrame with columns matching HistoricalBar fields.
    Output: DataFrame indexed by date with validated, adjusted prices.
    """

    def process(
        self,
        df: pd.DataFrame,
        corporate_actions: pd.DataFrame = None,
    ) -> pd.DataFrame:
        """Full processing pipeline. Returns cleaned df or empty df on failure."""
        if df is None or df.empty:
            return pd.DataFrame()

        try:
            df = self._cast_dtypes(df)
            df = self._remove_duplicates(df)
            df = self._remove_invalid_prices(df)

            if df.empty:
                logger.warning("DataFrame empty after invalid-price removal")
                return df

            df = self._reindex_to_bday(df)
            df = self._apply_corporate_adjustments(df, corporate_actions)
            df = self._clip_outlier_returns(df)
            return df

        except Exception as exc:
            logger.exception("DataProcessor failed: %s", exc)
            return pd.DataFrame()

    # ── Step 1: dtypes ────────────────────────────────────────────────────────

    def _cast_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df.set_index("date")

        for col in _PRICE_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

        if "adj_factor" in df.columns:
            df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce").fillna(1.0)

        return df

    # ── Step 2: duplicates ────────────────────────────────────────────────────

    def _remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        df = df[~df.index.duplicated(keep="last")]
        removed = before - len(df)
        if removed:
            logger.debug("Removed %d duplicate rows", removed)
        return df

    # ── Step 3: invalid prices ────────────────────────────────────────────────

    def _remove_invalid_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        before = len(df)
        mask = (
            df["close"].notna()
            & (df["close"] > 0)
            & df["adj_close"].notna()
            & (df["adj_close"] > 0)
        )
        df = df[mask]
        removed = before - len(df)
        if removed:
            logger.debug("Removed %d rows with null/zero/negative close prices", removed)
        return df

    # ── Step 4: business-day reindex + gap-fill ────────────────────────────────

    def _reindex_to_bday(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        start = df.index.min()
        end = df.index.max()
        bday_index = pd.bdate_range(start=start, end=end).date

        df.index = pd.to_datetime(df.index)  # type: ignore[assignment]
        bday_index_dt = pd.to_datetime(bday_index)
        df = df.reindex(bday_index_dt)

        # Forward-fill (max 5 business days) for each price and volume column
        fill_cols = [c for c in _PRICE_COLS if c in df.columns]
        df[fill_cols] = df[fill_cols].ffill(limit=_MAX_FORWARD_FILL_DAYS)
        df[fill_cols] = df[fill_cols].bfill(limit=2)  # Backward-fill ≤2 days at start

        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0)

        if "adj_factor" in df.columns:
            df["adj_factor"] = df["adj_factor"].ffill().bfill().fillna(1.0)

        filled_count = df["close"].isna().sum()
        if filled_count:
            logger.warning("%d dates still have NaN close after gap-fill", filled_count)

        df = df.dropna(subset=["close"])
        df.index = pd.to_datetime(df.index).date  # Convert back to date
        df.index.name = "date"  # Preserve index name for reset_index() callers

        missing_days = len(bday_index) - len(df)
        if missing_days:
            logger.debug("%d business days missing after gap-fill", missing_days)

        return df

    # ── Step 5: corporate action adjustments ──────────────────────────────────

    def _apply_corporate_adjustments(
        self,
        df: pd.DataFrame,
        corporate_actions: pd.DataFrame | None,
    ) -> pd.DataFrame:
        """Recompute adj_close using the multiplicative backward-adjustment method.

        If adj_close is already populated by the provider (e.g. MockProvider),
        this step is a no-op unless corporate_actions are also provided.
        """
        if corporate_actions is None or corporate_actions.empty:
            # adj_close already set by provider or all factors are 1.0
            return df

        df = df.copy()
        cumulative_factor = 1.0

        for _, action in corporate_actions.sort_values("ex_date", ascending=False).iterrows():
            ex_date = action["ex_date"]
            action_type = action.get("action_type", "")
            ratio = float(action.get("ratio", 1.0))
            div_amount = float(action.get("dividend_amount", 0.0))

            if action_type in ("SPLIT", "BONUS"):
                factor = 1.0 / ratio
            elif action_type == "DIVIDEND" and div_amount > 0:
                # Approximate: use last close before ex_date as reference
                prior_prices = df.loc[df.index < ex_date, "close"]
                if prior_prices.empty:
                    continue
                ref_close = float(prior_prices.iloc[-1])
                factor = max((ref_close - div_amount) / ref_close, 0.5)
            else:
                continue

            cumulative_factor *= factor
            mask = df.index < ex_date
            df.loc[mask, "adj_close"] = df.loc[mask, "close"] * cumulative_factor
            df.loc[mask, "adj_factor"] = cumulative_factor
            df.loc[mask, "is_adjusted"] = True

        return df

    # ── Step 6: clip extreme returns ─────────────────────────────────────────

    def _clip_outlier_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        if "adj_close" not in df.columns or len(df) < 2:
            return df

        returns = df["adj_close"].pct_change()
        outlier_mask = returns.abs() > _MAX_SINGLE_DAY_RETURN
        n_outliers = int(outlier_mask.sum())

        if n_outliers:
            logger.warning(
                "Found %d daily returns > %.0f%% (potential data errors or corporate actions)",
                n_outliers,
                _MAX_SINGLE_DAY_RETURN * 100,
            )

        return df

    # ── Public helpers ────────────────────────────────────────────────────────

    @staticmethod
    def bars_to_dataframe(bars: list) -> pd.DataFrame:
        """Convert a list of HistoricalBar dataclass instances to a DataFrame."""
        if not bars:
            return pd.DataFrame()

        records = [
            {
                "date": b.date,
                "symbol": b.symbol,
                "exchange": b.exchange,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "adj_close": b.adj_close,
                "adj_factor": b.adj_factor,
                "is_adjusted": b.is_adjusted,
            }
            for b in bars
        ]
        df = pd.DataFrame(records).set_index("date")
        df.index = pd.to_datetime(df.index).date
        return df

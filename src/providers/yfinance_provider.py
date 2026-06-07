"""Live NSE market data provider using Yahoo Finance (yfinance).

No credentials required. Uses '{symbol}.NS' Yahoo Finance ticker format.
Suitable for Streamlit Cloud deployment where ICICI Breeze credentials
are not available or IP whitelisting is not possible.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pandas as pd

from src.providers.base import (
    BaseMarketDataProvider,
    CorporateActionData,
    HistoricalBar,
    LiveQuoteData,
    ProviderError,
)

logger = logging.getLogger(__name__)


def _require_yfinance():
    try:
        import yfinance as yf  # type: ignore[import]
        return yf
    except ImportError as exc:
        raise ImportError(
            "yfinance is not installed. Run: pip install yfinance"
        ) from exc


def _to_date(ts) -> date | None:
    try:
        if isinstance(ts, date) and not isinstance(ts, datetime):
            return ts
        if hasattr(ts, "date"):
            return ts.date()
        return pd.Timestamp(ts).date()
    except Exception:
        return None


class YFinanceProvider(BaseMarketDataProvider):
    """Real NSE market data via Yahoo Finance.

    Fetches actual historical OHLCV bars and live quotes for NSE-listed equities.
    Prices are already split/dividend-adjusted by Yahoo Finance (auto_adjust=True).
    Corporate actions (splits + dividends) are fetched from Yahoo Finance actions.
    """

    def __init__(self) -> None:
        self._authenticated = False
        self._yf = None

    def authenticate(self) -> bool:
        self._yf = _require_yfinance()
        self._authenticated = True
        logger.info("YFinanceProvider ready (no credentials required)")
        return True

    def health_check(self) -> bool:
        if not self._authenticated:
            return False
        try:
            yf = self._yf or _require_yfinance()
            hist = yf.Ticker("RELIANCE.NS").history(period="2d", auto_adjust=True)
            return not hist.empty
        except Exception as exc:
            logger.warning("YFinanceProvider health check failed: %s", exc)
            return False

    def get_provider_name(self) -> str:
        return "YFinanceProvider"

    def get_historical_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[HistoricalBar]:
        yf = self._yf or _require_yfinance()
        ticker_symbol = f"{symbol}.NS"

        try:
            ticker = yf.Ticker(ticker_symbol)
            # auto_adjust=True: 'Close' column is the backward-adjusted close price.
            # End date is exclusive in yfinance, so add 1 day to include end_date.
            hist = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                actions=False,
            )

            if hist.empty:
                logger.warning("YFinance: no historical data for %s", ticker_symbol)
                return []

            bars: list[HistoricalBar] = []
            for ts, row in hist.iterrows():
                bar_date = _to_date(ts)
                if bar_date is None:
                    continue

                adj_close = round(float(row["Close"]), 2)
                bars.append(
                    HistoricalBar(
                        symbol=symbol,
                        exchange=exchange,
                        date=bar_date,
                        open=round(float(row["Open"]), 2),
                        high=round(float(row["High"]), 2),
                        low=round(float(row["Low"]), 2),
                        close=adj_close,
                        volume=int(row.get("Volume", 0) or 0),
                        adj_close=adj_close,
                        adj_factor=1.0,
                        is_adjusted=True,
                    )
                )

            bars.sort(key=lambda b: b.date)
            logger.debug("YFinanceProvider: %d bars for %s", len(bars), symbol)
            return bars

        except Exception as exc:
            logger.error("YFinanceProvider historical fetch failed for %s: %s", symbol, exc)
            raise ProviderError(f"YFinance fetch failed for {symbol}: {exc}") from exc

    def get_live_quote(self, symbol: str, exchange: str = "NSE") -> LiveQuoteData:
        yf = self._yf or _require_yfinance()
        ticker_symbol = f"{symbol}.NS"

        try:
            ticker = yf.Ticker(ticker_symbol)

            ltp = prev_close = day_open = day_high = day_low = volume = None

            # fast_info is lightweight (no full download)
            try:
                fi = ticker.fast_info
                ltp = float(fi.last_price)
                prev_close = float(fi.previous_close)
                day_open = float(fi.open) if fi.open else ltp
                day_high = float(fi.day_high) if fi.day_high else ltp
                day_low = float(fi.day_low) if fi.day_low else ltp
                volume = int(fi.three_month_average_volume or 0)
            except Exception:
                pass

            # Fallback: use recent daily history
            if ltp is None:
                hist = ticker.history(period="5d", auto_adjust=True)
                if hist.empty:
                    raise ProviderError(f"No quote data for {symbol}")
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) >= 2 else latest
                ltp = float(latest["Close"])
                prev_close = float(prev["Close"])
                day_open = float(latest["Open"])
                day_high = float(latest["High"])
                day_low = float(latest["Low"])
                volume = int(latest.get("Volume", 0) or 0)

            spread = max(round(ltp * 0.0005, 2), 0.05)

            return LiveQuoteData(
                symbol=symbol,
                ltp=round(ltp, 2),
                bid=round(ltp - spread, 2),
                ask=round(ltp + spread, 2),
                volume=volume,
                open=round(day_open, 2),
                high=round(day_high, 2),
                low=round(day_low, 2),
                prev_close=round(prev_close, 2),
                timestamp=datetime.now(),
            )

        except ProviderError:
            raise
        except Exception as exc:
            logger.error("YFinanceProvider live quote failed for %s: %s", symbol, exc)
            raise ProviderError(f"YFinance quote failed for {symbol}: {exc}") from exc

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[CorporateActionData]:
        yf = self._yf or _require_yfinance()
        ticker_symbol = f"{symbol}.NS"

        try:
            ticker = yf.Ticker(ticker_symbol)
            actions: list[CorporateActionData] = []

            splits = ticker.splits
            if splits is not None and not splits.empty:
                for ts, ratio in splits.items():
                    ex_dt = _to_date(ts)
                    if ex_dt and start_date <= ex_dt <= end_date and ratio > 0:
                        actions.append(CorporateActionData(
                            symbol=symbol,
                            ex_date=ex_dt,
                            action_type="SPLIT",
                            ratio=float(ratio),
                            dividend_amount=0.0,
                            notes=f"Split {ratio:.0f}:1 (Yahoo Finance)",
                        ))

            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for ts, amount in divs.items():
                    ex_dt = _to_date(ts)
                    if ex_dt and start_date <= ex_dt <= end_date and amount > 0:
                        actions.append(CorporateActionData(
                            symbol=symbol,
                            ex_date=ex_dt,
                            action_type="DIVIDEND",
                            ratio=1.0,
                            dividend_amount=float(amount),
                            notes=f"Dividend INR {amount:.2f} (Yahoo Finance)",
                        ))

            actions.sort(key=lambda a: a.ex_date)
            return actions

        except Exception as exc:
            logger.warning("YFinanceProvider CA fetch failed for %s: %s", symbol, exc)
            return []

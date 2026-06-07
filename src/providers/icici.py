"""ICICI Direct Breeze Connect data provider.

Authentication flow:
1. Set ICICI_APP_KEY (or ICICI_API_KEY) and ICICI_SECRET_KEY (or ICICI_API_SECRET) in .env.
2. Run `python scripts/refresh_session.py` — it prints the login URL and writes the token.
   Or manually:
     a. Open the login URL: https://api.icicidirect.com/apiuser/login?api_key=<YOUR_KEY>
     b. Log in with your ICICI Direct credentials.
     c. Copy the 'apisession' value from the redirect URL query string.
     d. Set ICICI_SESSION_TOKEN=<value> in .env.
3. Session tokens expire at midnight IST — refresh daily via `python scripts/refresh_session.py`.

Breeze stock codes differ from NSE symbols (e.g. RELIANCE → RELIND).
The mapping is maintained in self._code_map loaded from the universe CSV.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.providers.base import (
    BaseMarketDataProvider,
    CorporateActionData,
    HistoricalBar,
    LiveQuoteData,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)

_BREEZE_LOGIN_URL = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"


def _require_breeze() -> Any:
    """Lazy import so the module loads without breeze-connect installed (for tests).

    The breeze_connect SDK does `sys.path.insert(1, <sdk_dir>)` then `import config`.
    Because our project also has a `config/` package at root level, Python resolves
    the name to our package instead of the SDK's `config.py`, causing:
        AttributeError: module 'config' has no attribute 'SECURITY_MASTER_URL'

    Fix: insert the SDK's own directory at sys.path[0] *before* the import, so the
    SDK's config.py wins the name resolution race. Also evict any stale 'config' entry
    from sys.modules that came from our project's config/ package rather than the SDK.
    """
    import importlib.util as _ilu
    import sys as _sys

    try:
        _spec = _ilu.find_spec("breeze_connect")
        if _spec and _spec.submodule_search_locations:
            _sdk_dir = list(_spec.submodule_search_locations)[0]
            if _sdk_dir not in _sys.path:
                _sys.path.insert(0, _sdk_dir)
            # Evict stale 'config' if it was loaded from our project's config/ package
            # rather than the SDK's config.py (both share the same module name).
            _cached = _sys.modules.get("config")
            if _cached is not None and not hasattr(_cached, "SECURITY_MASTER_URL"):
                del _sys.modules["config"]

        from breeze_connect import BreezeConnect  # type: ignore[import]
        return BreezeConnect
    except ImportError as exc:
        raise ImportError(
            "breeze-connect is not installed. "
            "Run: pip install breeze-connect"
        ) from exc


class ICICIDirectProvider(BaseMarketDataProvider):
    """Production provider backed by ICICI Direct Breeze Connect API.

    Rate limits: ~1 historical request / second, ~3 live requests / second.
    The retry decorator handles transient network failures with exponential
    backoff.
    """

    _INTERVAL_MAP = {
        "1D": "1day",
        "1W": "1week",
        "1M": "1month",
        "5T": "5minute",
        "15T": "15minute",
        "30T": "30minute",
        "60T": "1hour",
    }

    def __init__(
        self,
        app_key: str,
        secret_key: str,
        session_token: str,
        code_map: Optional[dict[str, str]] = None,
        client_code: str = "",
    ) -> None:
        if not app_key or not secret_key:
            raise ProviderAuthError(
                "ICICI_APP_KEY and ICICI_SECRET_KEY must be set in the environment."
            )

        self._app_key = app_key
        self._secret_key = secret_key
        self._session_token = session_token
        self._client_code = client_code
        # NSE symbol → Breeze stock_code mapping (e.g. RELIANCE → RELIND)
        self._code_map: dict[str, str] = code_map or {}
        self._breeze: Any = None
        self._authenticated = False
        self._last_successful_call: Optional[datetime] = None

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def login_url(self) -> str:
        """URL the user must open in a browser to generate a session token."""
        return _BREEZE_LOGIN_URL.format(api_key=self._app_key)

    @property
    def last_successful_call(self) -> Optional[datetime]:
        """UTC timestamp of the last API call that returned data. None if never called."""
        return self._last_successful_call

    # ── BaseMarketDataProvider interface ──────────────────────────────────────

    def authenticate(self) -> bool:
        """Establish a Breeze Connect session.

        Raises ProviderAuthError if credentials are invalid or the session
        token is missing. Use `scripts/refresh_session.py` to generate one.
        """
        BreezeConnect = _require_breeze()
        try:
            self._breeze = BreezeConnect(api_key=self._app_key)

            if not self._session_token:
                raise ProviderAuthError(
                    "ICICI_SESSION_TOKEN is missing.\n"
                    f"  1. Open in your browser: {self.login_url}\n"
                    "  2. Log in with your ICICI Direct credentials.\n"
                    "  3. After redirect, copy the 'apisession' value from the URL.\n"
                    "  4. Set ICICI_SESSION_TOKEN=<value> in your .env file.\n"
                    "  Or run: python scripts/refresh_session.py"
                )

            self._breeze.generate_session(
                api_secret=self._secret_key,
                session_token=self._session_token,
            )
            self._authenticated = True
            self._last_successful_call = datetime.now(timezone.utc)
            logger.info("ICICIDirectProvider authenticated successfully")
            return True

        except ProviderAuthError:
            raise
        except Exception as exc:
            raise ProviderAuthError(f"Breeze authentication failed: {exc}") from exc

    def health_check(self) -> bool:
        """Return True if the current session is alive and can serve data."""
        if not self._authenticated or self._breeze is None:
            return False
        try:
            result = self._breeze.get_customer_details(api_session=self._session_token)
            ok = (
                result is not None
                and isinstance(result, dict)
                and result.get("Status") == 200
            )
            if ok:
                self._last_successful_call = datetime.now(timezone.utc)
            return ok
        except Exception as exc:
            logger.warning("ICICIDirectProvider health check failed: %s", exc)
            return False

    def get_provider_name(self) -> str:
        return "ICICIDirectProvider"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, ProviderRateLimitError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def get_historical_data(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[HistoricalBar]:
        self._ensure_authenticated()
        stock_code = self._resolve_code(symbol)

        raw = self._breeze.get_historical_data_v2(
            interval="1day",
            from_date=f"{start_date.isoformat()}T07:00:00.000Z",
            to_date=f"{end_date.isoformat()}T07:00:00.000Z",
            stock_code=stock_code,
            exchange_code=exchange,
            product_type="cash",
        )

        if not raw or "Success" not in raw or not raw["Success"]:
            logger.warning("No historical data returned for %s (%s)", symbol, stock_code)
            return []

        bars: list[HistoricalBar] = []
        for row in raw["Success"]:
            try:
                bar_date = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S").date()
                close = float(row["close"])
                bars.append(
                    HistoricalBar(
                        symbol=symbol,
                        exchange=exchange,
                        date=bar_date,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=close,
                        volume=int(float(row.get("volume", 0))),
                        adj_close=close,  # raw close; processor applies corporate actions
                        adj_factor=1.0,
                        is_adjusted=False,
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed bar for %s: %s | row=%s", symbol, exc, row)

        bars.sort(key=lambda b: b.date)
        self._last_successful_call = datetime.now(timezone.utc)
        logger.debug("Fetched %d bars for %s from ICICI", len(bars), symbol)
        return bars

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=1, max=5),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def get_live_quote(self, symbol: str, exchange: str = "NSE") -> LiveQuoteData:
        self._ensure_authenticated()
        stock_code = self._resolve_code(symbol)

        raw = self._breeze.get_quotes(
            stock_code=stock_code,
            exchange_code=exchange,
            expiry_date="",
            product_type="cash",
            right="",
            strike_price="",
        )

        if not raw or "Success" not in raw or not raw["Success"]:
            raise ProviderError(f"No live quote returned for {symbol} ({stock_code})")

        row = raw["Success"][0]
        ltp = float(row.get("ltp", row.get("last_rate", 0)))
        prev_close = float(row.get("previous_close", ltp))

        self._last_successful_call = datetime.now(timezone.utc)
        return LiveQuoteData(
            symbol=symbol,
            ltp=ltp,
            bid=float(row.get("best_bid_rate", ltp)),
            ask=float(row.get("best_offer_rate", ltp)),
            volume=int(float(row.get("total_quantity_traded", 0))),
            open=float(row.get("open_rate", ltp)),
            high=float(row.get("high_rate", ltp)),
            low=float(row.get("low_rate", ltp)),
            prev_close=prev_close,
            timestamp=datetime.now(),
        )

    def get_corporate_actions(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        exchange: str = "NSE",
    ) -> list[CorporateActionData]:
        """Breeze does not expose a corporate actions endpoint; returns empty list.

        Price adjustment is handled by the processor layer using NSE bhav copy data.
        """
        logger.debug(
            "Corporate action fetch not supported by Breeze API — "
            "apply adjustments via external source for %s",
            symbol,
        )
        return []

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_authenticated(self) -> None:
        if not self._authenticated:
            raise ProviderAuthError(
                "ICICIDirectProvider is not authenticated. Call authenticate() first."
            )

    def _resolve_code(self, symbol: str) -> str:
        """Map NSE symbol to Breeze stock_code. Falls back to the symbol itself."""
        code = self._code_map.get(symbol, symbol)
        if code != symbol:
            logger.debug("Symbol mapping: %s → %s", symbol, code)
        return code

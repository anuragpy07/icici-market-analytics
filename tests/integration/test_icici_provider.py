"""Integration tests for ICICIDirectProvider using mocked Breeze responses.

All tests run entirely offline — no ICICI credentials or network access required.
The BreezeConnect class is patched at the _require_breeze level so that no real
import of breeze_connect is needed at test time.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.providers.base import HistoricalBar, LiveQuoteData, ProviderAuthError, ProviderError
from src.providers.icici import ICICIDirectProvider, _BREEZE_LOGIN_URL


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_breeze_mock() -> MagicMock:
    """Return a pre-configured MagicMock that behaves like a live BreezeConnect instance."""
    m = MagicMock()
    m.generate_session.return_value = {"Status": 200}
    m.get_customer_details.return_value = {
        "Status": 200,
        "Success": [{"client_id": "TEST123", "client_name": "Test User"}],
    }
    m.get_historical_data_v2.return_value = {
        "Status": 200,
        "Success": [
            {
                "datetime": "2024-01-02 00:00:00",
                "open": "2400.0",
                "high": "2450.0",
                "low": "2380.0",
                "close": "2420.0",
                "volume": "1500000",
            },
            {
                "datetime": "2024-01-03 00:00:00",
                "open": "2420.0",
                "high": "2470.0",
                "low": "2410.0",
                "close": "2455.0",
                "volume": "1800000",
            },
        ],
    }
    m.get_quotes.return_value = {
        "Status": 200,
        "Success": [
            {
                "ltp": "2455.0",
                "previous_close": "2420.0",
                "best_bid_rate": "2454.5",
                "best_offer_rate": "2455.5",
                "total_quantity_traded": "2000000",
                "open_rate": "2420.0",
                "high_rate": "2475.0",
                "low_rate": "2415.0",
            }
        ],
    }
    return m


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def breeze_mock():
    return _make_breeze_mock()


@pytest.fixture()
def mock_breeze_class(breeze_mock):
    """Patch _require_breeze so no real breeze_connect import occurs."""
    mock_class = MagicMock(return_value=breeze_mock)
    with patch("src.providers.icici._require_breeze", return_value=mock_class):
        yield mock_class, breeze_mock


@pytest.fixture()
def authenticated_provider(mock_breeze_class):
    """Return a fully authenticated ICICIDirectProvider backed by mocked Breeze."""
    _, _ = mock_breeze_class
    provider = ICICIDirectProvider(
        app_key="test_app_key",
        secret_key="test_secret_key",
        session_token="test_session_token",
        code_map={"RELIANCE": "RELIND", "TCS": "TCS"},
        client_code="TEST123",
    )
    provider.authenticate()
    return provider


# ── TestICICIDirectProviderInit ───────────────────────────────────────────────


class TestICICIDirectProviderInit:
    def test_raises_without_app_key(self):
        with pytest.raises(ProviderAuthError, match="ICICI_APP_KEY"):
            ICICIDirectProvider(app_key="", secret_key="secret", session_token="token")

    def test_raises_without_secret_key(self):
        with pytest.raises(ProviderAuthError, match="ICICI_SECRET_KEY"):
            ICICIDirectProvider(app_key="key", secret_key="", session_token="token")

    def test_login_url_contains_api_key(self):
        p = ICICIDirectProvider(app_key="mykey123", secret_key="mysecret", session_token="")
        assert "mykey123" in p.login_url
        assert "icicidirect" in p.login_url

    def test_code_map_defaults_to_empty(self):
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert p._code_map == {}

    def test_code_map_stored(self):
        code_map = {"RELIANCE": "RELIND"}
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t", code_map=code_map)
        assert p._code_map == code_map

    def test_provider_name(self):
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert p.get_provider_name() == "ICICIDirectProvider"

    def test_not_authenticated_by_default(self):
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert p._authenticated is False

    def test_last_successful_call_none_before_auth(self):
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert p.last_successful_call is None

    def test_client_code_stored(self):
        p = ICICIDirectProvider(
            app_key="k", secret_key="s", session_token="t", client_code="CLIENTXYZ"
        )
        assert p._client_code == "CLIENTXYZ"


# ── TestAuthentication ────────────────────────────────────────────────────────


class TestAuthentication:
    def test_authenticate_success(self, mock_breeze_class):
        _, breeze_mock = mock_breeze_class
        provider = ICICIDirectProvider(
            app_key="key", secret_key="secret", session_token="token"
        )
        result = provider.authenticate()
        assert result is True
        assert provider._authenticated is True
        breeze_mock.generate_session.assert_called_once_with(
            api_secret="secret", session_token="token"
        )

    def test_authenticate_sets_last_successful_call(self, mock_breeze_class):
        _, _ = mock_breeze_class
        provider = ICICIDirectProvider(
            app_key="key", secret_key="secret", session_token="token"
        )
        before = datetime.now()
        provider.authenticate()
        assert provider.last_successful_call is not None
        assert provider.last_successful_call.timestamp() >= before.timestamp()

    def test_authenticate_missing_session_token_raises(self, mock_breeze_class):
        _, _ = mock_breeze_class
        provider = ICICIDirectProvider(
            app_key="key", secret_key="secret", session_token=""
        )
        with pytest.raises(ProviderAuthError, match="ICICI_SESSION_TOKEN"):
            provider.authenticate()

    def test_missing_session_token_error_contains_login_url(self, mock_breeze_class):
        _, _ = mock_breeze_class
        provider = ICICIDirectProvider(
            app_key="myapikey", secret_key="secret", session_token=""
        )
        with pytest.raises(ProviderAuthError) as exc_info:
            provider.authenticate()
        assert "icicidirect" in str(exc_info.value)

    def test_authenticate_breeze_exception_wraps_as_auth_error(self, mock_breeze_class):
        _, breeze_mock = mock_breeze_class
        breeze_mock.generate_session.side_effect = RuntimeError("network error")
        provider = ICICIDirectProvider(
            app_key="key", secret_key="secret", session_token="token"
        )
        with pytest.raises(ProviderAuthError, match="Breeze authentication failed"):
            provider.authenticate()

    def test_authenticate_is_idempotent(self, mock_breeze_class):
        _, _ = mock_breeze_class
        provider = ICICIDirectProvider(
            app_key="key", secret_key="secret", session_token="token"
        )
        provider.authenticate()
        provider.authenticate()  # second call — should not raise
        assert provider._authenticated is True


# ── TestHealthCheck ───────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_returns_false_when_not_authenticated(self):
        provider = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert provider.health_check() is False

    def test_returns_false_when_breeze_is_none(self):
        provider = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        provider._authenticated = True
        provider._breeze = None
        assert provider.health_check() is False

    def test_returns_true_when_session_valid(self, authenticated_provider):
        assert authenticated_provider.health_check() is True

    def test_health_check_passes_session_token(self, authenticated_provider):
        authenticated_provider.health_check()
        authenticated_provider._breeze.get_customer_details.assert_called_with(
            api_session="test_session_token"
        )

    def test_returns_false_on_exception(self, authenticated_provider):
        authenticated_provider._breeze.get_customer_details.side_effect = RuntimeError("timeout")
        assert authenticated_provider.health_check() is False

    def test_returns_false_on_non_200_status(self, authenticated_provider):
        authenticated_provider._breeze.get_customer_details.return_value = {"Status": 401}
        assert authenticated_provider.health_check() is False

    def test_returns_false_on_empty_response(self, authenticated_provider):
        authenticated_provider._breeze.get_customer_details.return_value = None
        assert authenticated_provider.health_check() is False

    def test_updates_last_successful_call_on_success(self, authenticated_provider):
        before = datetime.now()
        authenticated_provider.health_check()
        assert authenticated_provider.last_successful_call is not None
        assert authenticated_provider.last_successful_call.timestamp() >= before.timestamp()


# ── TestGetHistoricalData ─────────────────────────────────────────────────────


class TestGetHistoricalData:
    def test_returns_list_of_bars(self, authenticated_provider):
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert isinstance(bars, list)
        assert len(bars) == 2

    def test_bars_sorted_ascending(self, authenticated_provider):
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert bars[0].date < bars[1].date

    def test_bar_is_historicalbar_instance(self, authenticated_provider):
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert isinstance(bars[0], HistoricalBar)

    def test_bar_fields_correctly_parsed(self, authenticated_provider):
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        bar = bars[0]
        assert bar.symbol == "RELIANCE"
        assert bar.exchange == "NSE"
        assert bar.close == 2420.0
        assert bar.open == 2400.0
        assert bar.high == 2450.0
        assert bar.low == 2380.0
        assert bar.volume == 1_500_000
        assert bar.adj_close == bar.close   # ICICI returns unadjusted; adj=raw initially
        assert bar.adj_factor == 1.0
        assert bar.is_adjusted is False

    def test_symbol_mapped_to_breeze_code(self, authenticated_provider):
        authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        kwargs = authenticated_provider._breeze.get_historical_data_v2.call_args.kwargs
        assert kwargs["stock_code"] == "RELIND"

    def test_exchange_passed_through(self, authenticated_provider):
        authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31), exchange="BSE"
        )
        kwargs = authenticated_provider._breeze.get_historical_data_v2.call_args.kwargs
        assert kwargs["exchange_code"] == "BSE"

    def test_unmapped_symbol_used_as_is(self, authenticated_provider):
        authenticated_provider.get_historical_data(
            "NEWSTOCK", date(2024, 1, 1), date(2024, 1, 31)
        )
        kwargs = authenticated_provider._breeze.get_historical_data_v2.call_args.kwargs
        assert kwargs["stock_code"] == "NEWSTOCK"

    def test_empty_success_list_returns_empty(self, authenticated_provider):
        authenticated_provider._breeze.get_historical_data_v2.return_value = {"Success": []}
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert bars == []

    def test_none_response_returns_empty(self, authenticated_provider):
        authenticated_provider._breeze.get_historical_data_v2.return_value = None
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert bars == []

    def test_no_success_key_returns_empty(self, authenticated_provider):
        authenticated_provider._breeze.get_historical_data_v2.return_value = {"Error": "oops"}
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert bars == []

    def test_malformed_row_skipped_valid_rows_kept(self, authenticated_provider):
        authenticated_provider._breeze.get_historical_data_v2.return_value = {
            "Success": [
                {
                    "datetime": "2024-01-02 00:00:00",
                    "open": "100.0",
                    "high": "110.0",
                    "low": "95.0",
                    "close": "105.0",
                    "volume": "50000",
                },
                {"datetime": "INVALID_DATE", "open": "xxx"},  # bad row — should be skipped
            ]
        }
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert len(bars) == 1
        assert bars[0].close == 105.0

    def test_missing_volume_defaults_to_zero(self, authenticated_provider):
        authenticated_provider._breeze.get_historical_data_v2.return_value = {
            "Success": [
                {
                    "datetime": "2024-01-02 00:00:00",
                    "open": "100.0",
                    "high": "110.0",
                    "low": "95.0",
                    "close": "105.0",
                    # no volume key
                }
            ]
        }
        bars = authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert bars[0].volume == 0

    def test_raises_when_not_authenticated(self):
        provider = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        with pytest.raises(ProviderAuthError):
            provider.get_historical_data("RELIANCE", date(2024, 1, 1), date(2024, 1, 31))

    def test_updates_last_successful_call(self, authenticated_provider):
        before = datetime.now()
        authenticated_provider.get_historical_data(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 31)
        )
        assert authenticated_provider.last_successful_call is not None
        assert authenticated_provider.last_successful_call.timestamp() >= before.timestamp()


# ── TestGetLiveQuote ──────────────────────────────────────────────────────────


class TestGetLiveQuote:
    def test_returns_live_quote(self, authenticated_provider):
        quote = authenticated_provider.get_live_quote("RELIANCE")
        assert isinstance(quote, LiveQuoteData)

    def test_quote_fields_correctly_parsed(self, authenticated_provider):
        quote = authenticated_provider.get_live_quote("RELIANCE")
        assert quote.symbol == "RELIANCE"
        assert quote.ltp == 2455.0
        assert quote.prev_close == 2420.0
        assert quote.bid == 2454.5
        assert quote.ask == 2455.5
        assert quote.volume == 2_000_000
        assert quote.open == 2420.0
        assert quote.high == 2475.0
        assert quote.low == 2415.0

    def test_change_calculated_correctly(self, authenticated_provider):
        quote = authenticated_provider.get_live_quote("RELIANCE")
        assert abs(quote.change - (2455.0 - 2420.0)) < 0.01
        expected_pct = (35.0 / 2420.0) * 100
        assert abs(quote.change_pct - expected_pct) < 0.01

    def test_bid_lte_ask(self, authenticated_provider):
        quote = authenticated_provider.get_live_quote("RELIANCE")
        assert quote.bid <= quote.ask

    def test_symbol_mapped_to_breeze_code(self, authenticated_provider):
        authenticated_provider.get_live_quote("RELIANCE")
        kwargs = authenticated_provider._breeze.get_quotes.call_args.kwargs
        assert kwargs["stock_code"] == "RELIND"

    def test_empty_success_raises_provider_error(self, authenticated_provider):
        authenticated_provider._breeze.get_quotes.return_value = {"Success": []}
        with pytest.raises(ProviderError):
            authenticated_provider.get_live_quote("RELIANCE")

    def test_no_success_key_raises(self, authenticated_provider):
        authenticated_provider._breeze.get_quotes.return_value = {}
        with pytest.raises(ProviderError):
            authenticated_provider.get_live_quote("RELIANCE")

    def test_none_response_raises(self, authenticated_provider):
        authenticated_provider._breeze.get_quotes.return_value = None
        with pytest.raises(ProviderError):
            authenticated_provider.get_live_quote("RELIANCE")

    def test_raises_when_not_authenticated(self):
        provider = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        with pytest.raises(ProviderAuthError):
            provider.get_live_quote("RELIANCE")

    def test_updates_last_successful_call(self, authenticated_provider):
        before = datetime.now()
        authenticated_provider.get_live_quote("RELIANCE")
        assert authenticated_provider.last_successful_call.timestamp() >= before.timestamp()

    def test_fallback_to_last_rate_field(self, authenticated_provider):
        authenticated_provider._breeze.get_quotes.return_value = {
            "Success": [
                {
                    "last_rate": "3000.0",
                    "previous_close": "2950.0",
                    "best_bid_rate": "2999.0",
                    "best_offer_rate": "3001.0",
                    "total_quantity_traded": "100000",
                    "open_rate": "2950.0",
                    "high_rate": "3010.0",
                    "low_rate": "2940.0",
                }
            ]
        }
        quote = authenticated_provider.get_live_quote("RELIANCE")
        assert quote.ltp == 3000.0


# ── TestCorporateActions ──────────────────────────────────────────────────────


class TestCorporateActions:
    def test_always_returns_empty_list(self, authenticated_provider):
        result = authenticated_provider.get_corporate_actions(
            "RELIANCE", date(2024, 1, 1), date(2024, 12, 31)
        )
        assert result == []

    def test_returns_empty_without_authentication_too(self):
        provider = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        result = provider.get_corporate_actions(
            "RELIANCE", date(2024, 1, 1), date(2024, 12, 31)
        )
        assert result == []


# ── TestCodeMapping ───────────────────────────────────────────────────────────


class TestCodeMapping:
    def test_mapped_symbol_resolved(self):
        p = ICICIDirectProvider(
            app_key="k", secret_key="s", session_token="t",
            code_map={"RELIANCE": "RELIND"},
        )
        assert p._resolve_code("RELIANCE") == "RELIND"

    def test_unmapped_symbol_returns_itself(self):
        p = ICICIDirectProvider(
            app_key="k", secret_key="s", session_token="t",
            code_map={"RELIANCE": "RELIND"},
        )
        assert p._resolve_code("TCS") == "TCS"

    def test_empty_code_map_passthrough(self):
        p = ICICIDirectProvider(app_key="k", secret_key="s", session_token="t")
        assert p._resolve_code("RELIANCE") == "RELIANCE"
        assert p._resolve_code("INFY") == "INFY"

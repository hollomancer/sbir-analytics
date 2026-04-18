"""Direct tests for :class:`BaseAsyncAPIClient`.

``BaseAsyncAPIClient`` provides the shared rate-limiting, retry, and
error-translation machinery used by the USAspending and SAM.gov API
clients. The concrete subclasses have their own tests, but the base
class itself had no direct coverage — regressions in shared behavior
could only surface indirectly.

These tests exercise the base class through a minimal stub subclass
(``_StubAPIClient``) so the behavior under test is isolated from any
concrete client's config-loading, state-file, or auth logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.exceptions import APIError, ConfigurationError, RateLimitError

pytestmark = pytest.mark.fast


# ==================== Stub subclass ====================


class _StubAPIClient(BaseAsyncAPIClient):
    """Minimal concrete subclass for direct base-class testing.

    The leading underscore keeps pytest from collecting it as a test class
    (``python_classes = ["Test*"]``).
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.example.com/v1",
        rate_limit_per_minute: int = 60,
        api_name: str = "stub",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__()
        self.base_url = base_url
        self.rate_limit_per_minute = rate_limit_per_minute
        self.api_name = api_name
        self._client = http_client or AsyncMock(spec=httpx.AsyncClient)


# ==================== Fixtures ====================


@pytest.fixture
def mock_http_client() -> AsyncMock:
    mock = AsyncMock(spec=httpx.AsyncClient)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def client(mock_http_client: AsyncMock) -> _StubAPIClient:
    return _StubAPIClient(http_client=mock_http_client)


def _make_mock_response(
    status_code: int = 200,
    json_payload: dict | None = None,
) -> Mock:
    """Build a mock ``httpx.Response`` with the given status and JSON body."""
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_payload or {}
    resp.text = str(json_payload or "")
    resp.raise_for_status = Mock()
    return resp


# ==================== Lifecycle ====================


class TestLifecycle:
    """Tests for ``aclose`` and construction."""

    async def test_aclose_delegates_to_http_client(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        await client.aclose()
        mock_http_client.aclose.assert_awaited_once()

    async def test_initial_state(self, client: _StubAPIClient) -> None:
        assert client.request_times == []
        assert client.api_name == "stub"
        assert client.rate_limit_per_minute == 60


# ==================== Rate limiting ====================


class TestRateLimiting:
    """Tests for ``_wait_for_rate_limit`` sliding-window logic."""

    async def test_under_limit_no_wait(self, client: _StubAPIClient) -> None:
        """Under the limit: record the request and return immediately."""
        for _ in range(10):
            client.request_times.append(datetime.now())

        await client._wait_for_rate_limit()

        assert len(client.request_times) == 11

    async def test_records_timestamp_on_every_call(
        self, client: _StubAPIClient
    ) -> None:
        assert client.request_times == []
        await client._wait_for_rate_limit()
        assert len(client.request_times) == 1
        await client._wait_for_rate_limit()
        assert len(client.request_times) == 2

    async def test_evicts_timestamps_older_than_sixty_seconds(
        self, client: _StubAPIClient
    ) -> None:
        """Timestamps outside the 60s window are purged before the check."""
        old = datetime.now() - timedelta(seconds=90)
        for _ in range(client.rate_limit_per_minute):
            client.request_times.append(old)
        # Sprinkle in a few recent timestamps to verify they survive
        for _ in range(3):
            client.request_times.append(datetime.now())

        await client._wait_for_rate_limit()

        # All 60 old timestamps evicted; 3 recent survived; 1 new appended
        assert len(client.request_times) == 4

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_at_limit_waits_until_oldest_slot_frees(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
    ) -> None:
        """When saturated, caller sleeps until the oldest slot expires."""
        client.rate_limit_per_minute = 5
        # All 5 slots used 20 seconds ago → window frees in ~40s
        base = datetime.now() - timedelta(seconds=20)
        for i in range(5):
            client.request_times.append(base + timedelta(seconds=i))

        await client._wait_for_rate_limit()

        mock_sleep.assert_awaited_once()
        assert mock_sleep.await_args is not None
        wait_seconds = mock_sleep.await_args[0][0]
        # Oldest is ~20s old, wait ≈ 60 - 20 + 1 = 41 (small tolerance for clock skew)
        assert 39 <= wait_seconds <= 42


# ==================== Default headers ====================


class TestDefaultHeaders:
    """Tests for ``_build_headers`` and its override contract."""

    def test_build_headers_contains_defaults(self, client: _StubAPIClient) -> None:
        headers = client._build_headers()
        assert headers["Accept"] == "application/json"
        assert headers["User-Agent"] == "SBIR-Analytics/0.1.0"

    def test_build_headers_is_override_point(self) -> None:
        """Subclasses can extend ``_build_headers`` to inject auth."""

        class _AuthClient(_StubAPIClient):
            def _build_headers(self) -> dict[str, str]:
                base = super()._build_headers()
                base["Authorization"] = "Bearer test-token"
                return base

        auth_client = _AuthClient()
        headers = auth_client._build_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Accept"] == "application/json"


# ==================== HTTP request success path ====================


class TestMakeRequestSuccess:
    """Tests for the happy path through ``_make_request``."""

    async def test_get_returns_json(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        payload = {"ok": True, "data": [1, 2, 3]}
        mock_http_client.get.return_value = _make_mock_response(200, payload)

        result = await client._make_request("GET", "/things")

        assert result == payload
        mock_http_client.get.assert_awaited_once()

    async def test_post_sends_body_as_json(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        payload = {"created": "abc"}
        mock_http_client.post.return_value = _make_mock_response(200, payload)

        result = await client._make_request(
            "POST", "/things", params={"name": "widget"}
        )

        assert result == payload
        call_kwargs = mock_http_client.post.call_args[1]
        assert call_kwargs["json"] == {"name": "widget"}

    async def test_method_is_case_insensitive(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("get", "/things")

        mock_http_client.get.assert_awaited_once()

    async def test_url_join_strips_redundant_slashes(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """Trailing slash on base_url and leading slash on endpoint both trimmed."""
        client.base_url = "https://api.example.com/v1/"
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "/things")

        called_url = mock_http_client.get.call_args[0][0]
        assert called_url == "https://api.example.com/v1/things"

    async def test_url_join_handles_no_slashes(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        client.base_url = "https://api.example.com/v1"
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "things")

        called_url = mock_http_client.get.call_args[0][0]
        assert called_url == "https://api.example.com/v1/things"

    async def test_absolute_url_endpoint_bypasses_base_url(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """When endpoint is an absolute URL, base_url is ignored.

        Used by cross-host clients like press_wire which poll multiple
        RSS hostnames under a single client instance.
        """
        client.base_url = "https://api.example.com/v1"
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "https://other.example.com/rss")

        called_url = mock_http_client.get.call_args[0][0]
        assert called_url == "https://other.example.com/rss"

    async def test_absolute_http_url_also_works(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "http://legacy.example.com/feed")

        called_url = mock_http_client.get.call_args[0][0]
        assert called_url == "http://legacy.example.com/feed"

    async def test_custom_headers_merged_with_defaults(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "/things", headers={"X-Custom": "hello"})

        call_headers = mock_http_client.get.call_args[1]["headers"]
        assert call_headers["X-Custom"] == "hello"
        assert call_headers["Accept"] == "application/json"
        assert call_headers["User-Agent"] == "SBIR-Analytics/0.1.0"

    async def test_custom_headers_can_override_defaults(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request(
            "GET", "/things", headers={"User-Agent": "Custom/9.9"}
        )

        call_headers = mock_http_client.get.call_args[1]["headers"]
        assert call_headers["User-Agent"] == "Custom/9.9"

    async def test_get_passes_query_params(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.return_value = _make_mock_response(200, {})

        await client._make_request("GET", "/things", params={"q": "widget"})

        call_kwargs = mock_http_client.get.call_args[1]
        assert call_kwargs["params"] == {"q": "widget"}


# ==================== HTTP request error path ====================


class TestMakeRequestErrors:
    """Tests for error translation in ``_make_request``."""

    async def test_unsupported_method_raises_configuration_error(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        # Ensure the http client has a put method so the method check is the failure
        mock_http_client.put = AsyncMock()

        with pytest.raises(ConfigurationError, match="Unsupported HTTP method: PUT"):
            await client._make_request("PUT", "/things")

    async def test_http_404_raises_non_retryable_api_error(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 404
        resp.text = "Not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        with pytest.raises(APIError) as exc_info:
            await client._make_request("GET", "/missing")

        err = exc_info.value
        assert "HTTP 404" in str(err)
        assert err.component == "api.stub"
        assert err.details["endpoint"] == "/missing"
        assert err.details["http_status"] == 404
        # 404 is not in the retryable set — APIError should leave retryable=False
        assert err.retryable is False

    async def test_http_500_marks_error_retryable(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=resp
        )

        with pytest.raises(APIError) as exc_info:
            await client._make_request("GET", "/boom")

        err = exc_info.value
        assert err.details["http_status"] == 500
        # APIError auto-marks 500/502/503/504 as retryable
        assert err.retryable is True

    async def test_http_429_raises_rate_limit_error(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        resp = Mock()
        resp.status_code = 429
        resp.text = "Too Many Requests"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "429", request=Mock(), response=resp
        )

        with pytest.raises(RateLimitError) as exc_info:
            await client._make_request("GET", "/things")

        err = exc_info.value
        # RateLimitError is an APIError subclass
        assert isinstance(err, APIError)
        assert err.details["endpoint"] == "/things"
        assert err.details["http_status"] == 429
        # Rate limits are always retryable
        assert err.retryable is True
        assert err.component == "api.stub"

    async def test_network_error_raises_retryable_api_error(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        mock_http_client.get.side_effect = httpx.RequestError("connection refused")

        with pytest.raises(APIError) as exc_info:
            await client._make_request("GET", "/things")

        err = exc_info.value
        assert "Request error" in str(err)
        assert err.retryable is True
        assert err.component == "api.stub"

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_persistent_timeout_exhausts_retries_then_raises_408(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
        mock_http_client: AsyncMock,
    ) -> None:
        """A persistent TimeoutException → 3 attempts → APIError(408)."""
        mock_http_client.get.side_effect = httpx.TimeoutException("deadline")

        with pytest.raises(APIError) as exc_info:
            await client._make_request("GET", "/slow")

        err = exc_info.value
        assert "timeout after retries" in str(err).lower()
        assert err.details["http_status"] == 408
        assert err.retryable is False
        # stop_after_attempt(3) → 3 HTTP calls total
        assert mock_http_client.get.await_count == 3


# ==================== Retry semantics ====================


class TestRequestRaw:
    """Tests for ``_request_raw`` — the body-agnostic primitive that
    returns the raw :class:`httpx.Response`. Used by clients that need
    XML, text, or binary bodies. ``_make_request`` is a thin JSON
    wrapper around this method.
    """

    async def test_returns_raw_response(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """The raw httpx.Response is returned unmodified — caller decodes."""
        mock_resp = _make_mock_response(200, {"any": "json"})
        mock_resp.text = "<xml>arbitrary body</xml>"
        mock_http_client.get.return_value = mock_resp

        result = await client._request_raw("GET", "/things")

        assert result is mock_resp
        # No .json() call from the base layer
        mock_resp.json.assert_not_called()

    async def test_caller_can_extract_text(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """A non-JSON client extracts ``.text`` from the response."""
        mock_resp = _make_mock_response(200)
        mock_resp.text = "<feed><entry/></feed>"
        mock_http_client.get.return_value = mock_resp

        response = await client._request_raw("GET", "/atom")

        assert response.text == "<feed><entry/></feed>"

    async def test_make_request_delegates_to_request_raw(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """``_make_request`` is a thin JSON wrapper — it must call ``.json()``."""
        mock_resp = _make_mock_response(200, {"key": "value"})
        mock_http_client.get.return_value = mock_resp

        result = await client._make_request("GET", "/things")

        assert result == {"key": "value"}
        mock_resp.json.assert_called_once()

    async def test_request_raw_raises_api_error_on_404(
        self, client: _StubAPIClient, mock_http_client: AsyncMock
    ) -> None:
        """Error translation happens at the raw layer — JSON wrapper inherits it."""
        resp = Mock()
        resp.status_code = 404
        resp.text = "not found"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client._request_raw("GET", "/missing")

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_request_raw_retries_transient_failures(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
        mock_http_client: AsyncMock,
    ) -> None:
        """Retry behavior is on _request_raw, so XML/text clients get it too."""
        mock_resp = _make_mock_response(200)
        mock_resp.text = "<feed/>"
        mock_http_client.get.side_effect = [
            httpx.TimeoutException("first"),
            mock_resp,
        ]

        response = await client._request_raw("GET", "/flaky")

        assert response.text == "<feed/>"
        assert mock_http_client.get.await_count == 2


class TestRetrySemantics:
    """Tests that tenacity retries the right errors and skips the wrong ones."""

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_transient_timeout_then_succeeds(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
        mock_http_client: AsyncMock,
    ) -> None:
        """First attempt times out, second attempt succeeds — caller gets the result."""
        mock_http_client.get.side_effect = [
            httpx.TimeoutException("first attempt"),
            _make_mock_response(200, {"recovered": True}),
        ]

        result = await client._make_request("GET", "/flaky")

        assert result == {"recovered": True}
        assert mock_http_client.get.await_count == 2

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_does_not_retry_on_4xx(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
        mock_http_client: AsyncMock,
    ) -> None:
        """HTTPStatusError is translated to APIError before tenacity sees it,
        so tenacity does not retry it."""
        resp = Mock()
        resp.status_code = 404
        resp.text = "nope"
        mock_http_client.get.side_effect = httpx.HTTPStatusError(
            "404", request=Mock(), response=resp
        )

        with pytest.raises(APIError):
            await client._make_request("GET", "/missing")

        # Only one HTTP call — tenacity does not retry APIError
        assert mock_http_client.get.await_count == 1

    @patch("sbir_etl.enrichers.base_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_does_not_retry_on_network_error(
        self,
        mock_sleep: AsyncMock,
        client: _StubAPIClient,
        mock_http_client: AsyncMock,
    ) -> None:
        """RequestError is also translated to APIError — not retried by tenacity."""
        mock_http_client.get.side_effect = httpx.RequestError("connection refused")

        with pytest.raises(APIError):
            await client._make_request("GET", "/things")

        assert mock_http_client.get.await_count == 1

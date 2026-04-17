"""Base async API client with shared rate limiting and retry logic.

Provides common infrastructure used by USAspending and SAM.gov API clients:
- Async rate limiting with configurable requests-per-minute
- HTTP request execution with tenacity retry
- Consistent error handling via central exception hierarchy
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError, ConfigurationError, RateLimitError
from .rate_limiting import RateLimiter


class BaseAsyncAPIClient:
    """Base async API client with rate limiting and retry logic.

    Subclasses must set:
        - self.base_url: str
        - self.rate_limit_per_minute: int
        - self._client: httpx.AsyncClient
        - self.api_name: str  (used in error messages, e.g. "usaspending")

    Subclasses may pass ``shared_limiter`` to :meth:`__init__` to route
    rate-limit waits through a shared synchronous :class:`RateLimiter`
    (useful when multiple client instances share a global quota across
    worker threads). The blocking ``wait_if_needed`` call is dispatched
    via :func:`asyncio.to_thread` so it does not block the event loop.
    """

    base_url: str
    rate_limit_per_minute: int
    api_name: str
    _client: httpx.AsyncClient

    def __init__(self, *, shared_limiter: RateLimiter | None = None) -> None:
        self.request_times: list[datetime] = []
        self._rate_limit_lock = asyncio.Lock()
        self._shared_limiter = shared_limiter

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded.

        When a shared synchronous limiter is configured, defer to it via
        :func:`asyncio.to_thread`. Otherwise use the per-instance async
        sliding-window limiter.
        """
        if self._shared_limiter is not None:
            await asyncio.to_thread(self._shared_limiter.wait_if_needed)
            return

        async with self._rate_limit_lock:
            now = datetime.now()
            self.request_times = [t for t in self.request_times if (now - t).total_seconds() < 60]

            if len(self.request_times) >= self.rate_limit_per_minute:
                oldest = min(self.request_times)
                wait_seconds = 60 - (now - oldest).total_seconds() + 1
                if wait_seconds > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_seconds:.1f} seconds")
                    await asyncio.sleep(wait_seconds)

            self.request_times.append(datetime.now())

    def _build_headers(self) -> dict[str, str]:
        """Build default request headers. Override to add auth headers."""
        return {
            "Accept": "application/json",
            "User-Agent": "SBIR-Analytics/0.1.0",
        }

    async def _request_raw(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request with rate limiting and retry logic.

        Returns the raw :class:`httpx.Response` so callers can decode
        non-JSON bodies (XML, text, binary) themselves. JSON-API
        callers should use :meth:`_make_request` instead, which is a
        thin wrapper around this method that calls ``response.json()``.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path (relative to base_url)
            params: Query parameters (GET) or JSON body (POST)
            headers: Additional headers to merge with defaults

        Returns:
            The raw :class:`httpx.Response`.

        Raises:
            APIError: If request fails after retries
            RateLimitError: If rate limit exceeded
            ConfigurationError: If method is unsupported
        """

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2.0, min=2, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _do_request() -> httpx.Response:
            await self._wait_for_rate_limit()

            # Allow absolute URLs as endpoints for cross-host clients (e.g.
            # press_wire, which polls multiple RSS hostnames). Otherwise
            # build the URL from base_url + endpoint.
            endpoint_str = str(endpoint)
            if endpoint_str.startswith(("http://", "https://")):
                url = endpoint_str
            else:
                url = (
                    f"{str(self.base_url).rstrip('/')}/"
                    f"{endpoint_str.lstrip('/')}"
                )
            request_headers = self._build_headers()
            if headers:
                request_headers.update(headers)

            try:
                if method.upper() == "GET":
                    response = await self._client.get(
                        url, params=params, headers=request_headers
                    )
                elif method.upper() == "POST":
                    response = await self._client.post(
                        url, json=params, headers=request_headers
                    )
                else:
                    raise ConfigurationError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()

                if response.status_code == 429:
                    raise RateLimitError(
                        "Rate limit exceeded",
                        api_name=self.api_name,
                        endpoint=endpoint,
                    )

                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise RateLimitError(
                        "Rate limit exceeded",
                        api_name=self.api_name,
                        endpoint=endpoint,
                        http_status=e.response.status_code,
                    ) from e
                raise APIError(
                    f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                    api_name=self.api_name,
                    endpoint=endpoint,
                    http_status=e.response.status_code,
                ) from e
            except httpx.TimeoutException:
                raise
            except httpx.RequestError as e:
                raise APIError(
                    f"Request error: {e}",
                    api_name=self.api_name,
                    endpoint=endpoint,
                    retryable=True,
                ) from e

        try:
            return await _do_request()
        except httpx.TimeoutException as e:
            raise APIError(
                "Request timeout after retries",
                api_name=self.api_name,
                endpoint=endpoint,
                http_status=408,
                retryable=False,
            ) from e

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request and return the parsed JSON body.

        Thin wrapper around :meth:`_request_raw` for JSON APIs. Same
        retry, rate-limiting, and error semantics — see that method
        for details.

        Returns:
            JSON response as dict.

        Raises:
            APIError: If request fails after retries
            RateLimitError: If rate limit exceeded
        """
        response = await self._request_raw(
            method, endpoint, params=params, headers=headers
        )
        return response.json()

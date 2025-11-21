"""SAM.gov API client for entity information.

This module provides an async client for querying the SAM.gov Entity Information API
to enrich SBIR awards with company data, UEI, CAGE codes, and entity information.
Supports rate limiting, retry logic, and state management.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ...config.loader import get_config
from ...exceptions import APIError, ConfigurationError, RateLimitError


# Backward compatibility: Alias to central exception classes
SAMGovAPIError = APIError
SAMGovRateLimitError = RateLimitError


class SAMGovAPIClient:
    """Async client for SAM.gov Entity Information API v3."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize SAM.gov API client.

        Args:
            config: Optional configuration override. If None, loads from get_config()
            http_client: Optional pre-configured HTTPX client (useful for tests)
        """
        if config is None:
            cfg = get_config()
            self.api_config = cfg.enrichment.sam_gov
        else:
            self.api_config = config

        self.base_url = self.api_config.get("base_url", "https://api.sam.gov/entity-information/v3")
        self.timeout = self.api_config.get("timeout_seconds", 30)
        self.retry_attempts = self.api_config.get("retry_attempts", 3)
        self.retry_backoff = self.api_config.get("retry_backoff_seconds", 1.0)
        self.rate_limit_per_minute = self.api_config.get("rate_limit_per_minute", 60)

        # Get API key from environment
        api_key_env_var = self.api_config.get("api_key_env_var", "SAM_GOV_API_KEY")
        self.api_key = os.getenv(api_key_env_var)
        if not self.api_key:
            logger.warning(
                f"SAM.gov API key not found in {api_key_env_var}. "
                "API calls will fail without authentication."
            )

        # Rate limiting state
        self.request_times: list[datetime] = []
        self._rate_limit_lock = asyncio.Lock()

        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)

        logger.info(
            f"Initialized SAMGovAPIClient: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min"
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded."""
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

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to SAM.gov API with retry logic.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path (relative to base_url)
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response as dict

        Raises:
            SAMGovAPIError: If request fails
            SAMGovRateLimitError: If rate limit exceeded
        """

        # Inner function that does the actual request (will be wrapped by retry decorator)
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2.0, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _do_request() -> dict[str, Any]:
            await self._wait_for_rate_limit()

            url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            default_headers = {
                "Accept": "application/json",
                "User-Agent": "SBIR-Analytics/0.1.0",
            }
            if self.api_key:
                default_headers["X-Api-Key"] = self.api_key

            if headers:
                default_headers.update(headers)

            try:
                if method.upper() == "GET":
                    response = await self._client.get(url, params=params, headers=default_headers)
                elif method.upper() == "POST":
                    response = await self._client.post(url, json=params, headers=default_headers)
                else:
                    raise ConfigurationError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()

                # Handle rate limit errors
                if response.status_code == 429:
                    raise RateLimitError(
                        f"SAM.gov API rate limit exceeded: {response.text}",
                        status_code=429,
                        response_text=response.text,
                    )

                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise RateLimitError(
                        f"SAM.gov API rate limit exceeded: {e.response.text}",
                        status_code=429,
                        response_text=e.response.text,
                    )
                raise APIError(
                    f"SAM.gov API request failed: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code,
                    response_text=e.response.text,
                )
            except httpx.TimeoutException as e:
                raise APIError(f"SAM.gov API request timed out: {e}")
            except httpx.RequestError as e:
                raise APIError(f"SAM.gov API request error: {e}")

        return await _do_request()

    async def get_entity_by_uei(self, uei: str) -> dict[str, Any] | None:
        """Get entity data by UEI (Unique Entity Identifier).

        Args:
            uei: Unique Entity Identifier (12 characters)

        Returns:
            Entity data dict or None if not found
        """
        try:
            # SAM.gov Entity Information API v3 endpoint
            # Format: /entities/{uei}
            response = await self._make_request("GET", f"/entities/{uei}")
            return response
        except APIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Entity not found for UEI: {uei}")
                return None
            raise

    async def get_entity_by_cage(self, cage: str) -> dict[str, Any] | None:
        """Get entity data by CAGE code.

        Args:
            cage: CAGE code (5 characters)

        Returns:
            Entity data dict or None if not found
        """
        try:
            # SAM.gov Entity Information API v3 endpoint
            # Format: /entities?cage={cage}
            response = await self._make_request("GET", "/entities", params={"cage": cage})
            # API may return a list, get first result
            if isinstance(response, list) and len(response) > 0:
                return response[0]
            return response if not isinstance(response, list) else None
        except APIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Entity not found for CAGE: {cage}")
                return None
            raise

    async def search_entities(
        self,
        *,
        legal_business_name: str | None = None,
        duns: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for entities by name or DUNS.

        Args:
            legal_business_name: Legal business name to search
            duns: DUNS number (legacy identifier)
            limit: Maximum number of results

        Returns:
            List of entity data dicts
        """
        params: dict[str, Any] = {"limit": limit}
        if legal_business_name:
            params["legalBusinessName"] = legal_business_name
        if duns:
            params["duns"] = duns

        try:
            response = await self._make_request("GET", "/entities", params=params)
            # API may return a list or dict with results
            if isinstance(response, list):
                return response
            elif isinstance(response, dict) and "entityData" in response:
                return response["entityData"]
            elif isinstance(response, dict) and "results" in response:
                return response["results"]
            return [response] if response else []
        except APIError as e:
            logger.warning(f"Entity search failed: {e}")
            return []

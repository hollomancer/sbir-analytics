"""USAspending API client for iterative enrichment.

This module provides an async client for querying the USAspending.gov API v2
to enrich SBIR awards with recipient data, NAICS codes, and transaction information.
Supports rate limiting, retry logic, delta detection, and state management.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ...config.loader import get_config
from ...exceptions import APIError, ConfigurationError, RateLimitError
from ...models.enrichment import EnrichmentFreshnessRecord


# Backward compatibility: Alias to central exception classes
# TODO: Update all usages to use APIError/RateLimitError directly, then remove these aliases
USAspendingAPIError = APIError
USAspendingRateLimitError = RateLimitError


class USAspendingAPIClient:
    """Async client for USAspending.gov API v2."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize USAspending API client.

        Args:
            config: Optional configuration override. If None, loads from get_config()
            http_client: Optional pre-configured HTTPX client (useful for tests)
        """
        if config is None:
            cfg = get_config()
            self.config = cfg.enrichment_refresh.usaspending.model_dump()
            self.api_config = cfg.enrichment.usaspending_api
        else:
            self.config = config
            self.api_config = config.get("usaspending_api", {})

        self.base_url = self.api_config.get("base_url", "https://api.usaspending.gov/api/v2")
        self.timeout = self.config.get("timeout_seconds", 30)
        self.retry_attempts = self.config.get("retry_attempts", 3)
        self.retry_backoff = self.config.get("retry_backoff_seconds", 2.0)
        self.retry_multiplier = self.config.get("retry_backoff_multiplier", 2.0)
        self.rate_limit_per_minute = self.config.get("rate_limit_per_minute", 120)

        # Rate limiting state
        self.request_times: list[datetime] = []
        self._rate_limit_lock = asyncio.Lock()

        # State file path
        self.state_file = Path(
            self.config.get("state_file", "data/state/enrichment_refresh_state.json")
        )
        from src.utils.common.path_utils import ensure_parent_dir

        ensure_parent_dir(self.state_file)

        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)

        logger.info(
            f"Initialized USAspendingAPIClient: base_url={self.base_url}, "
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
        """Make an HTTP request to USAspending API with retry logic.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint path (relative to base_url)
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response as dict

        Raises:
            USAspendingAPIError: If request fails
            USAspendingRateLimitError: If rate limit exceeded
        """

        # Inner function that does the actual request (will be wrapped by retry decorator)
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2.0, min=2, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )
        async def _do_request() -> dict[str, Any]:
            await self._wait_for_rate_limit()

            url_str: str = str(self.base_url) if self.base_url else "https://api.usaspending.gov/api/v2"
            url = f"{url_str.rstrip('/')}/{endpoint.lstrip('/')}"
            default_headers = {
                "Accept": "application/json",
                "User-Agent": "SBIR-Analytics/0.1.0",
            }
            if headers:
                default_headers.update(headers)

            try:
                if method.upper() == "GET":
                    response = await self._client.get(url, params=params, headers=default_headers)
                elif method.upper() == "POST":
                    response = await self._client.post(url, json=params, headers=default_headers)
                else:
                    raise ConfigurationError(
                        f"Unsupported HTTP method: {method}",
                        component="enricher.usaspending",
                        operation="_make_request",
                        details={
                            "method": method,
                            "supported_methods": ["GET", "POST"],
                            "endpoint": endpoint,
                        },
                    )

                response.raise_for_status()

                if response.status_code == 429:
                    raise RateLimitError(
                        "Rate limit exceeded",
                        api_name="usaspending",
                        endpoint=endpoint,
                        details={"response_text": response.text[:200]},
                    )

                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise RateLimitError(
                        "Rate limit exceeded",
                        api_name="usaspending",
                        endpoint=endpoint,
                        http_status=e.response.status_code,
                        details={"response_text": e.response.text[:200]},
                        cause=e,
                    ) from e
                raise APIError(
                    f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                    api_name="usaspending",
                    endpoint=endpoint,
                    http_status=e.response.status_code,
                    operation="_make_request",
                    cause=e,
                ) from e
            except httpx.TimeoutException:
                # Let TimeoutException propagate so retry decorator can catch it
                raise
            except httpx.RequestError as e:
                raise APIError(
                    f"Request error: {str(e)}",
                    api_name="usaspending",
                    endpoint=endpoint,
                    operation="_make_request",
                    retryable=True,
                    cause=e,
                ) from e

        # Call the retry-wrapped function and wrap TimeoutException after retries exhausted
        try:
            return await _do_request()
        except httpx.TimeoutException as e:
            # After all retries exhausted, wrap TimeoutException for consistent API
            raise APIError(
                "Request timeout after retries",
                api_name="usaspending",
                endpoint=endpoint,
                http_status=408,  # Timeout status code
                operation="_make_request",
                retryable=False,  # Already retried, don't retry again
                cause=e,
            ) from e

    def _compute_payload_hash(self, payload: dict[str, Any]) -> str:
        """Compute deterministic SHA256 hash of JSON payload.

        Args:
            payload: API response payload

        Returns:
            SHA256 hash as hex string
        """
        # Sort keys for deterministic hashing
        json_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _extract_delta_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract USAspending-specific delta identifiers from payload.

        Args:
            payload: API response payload

        Returns:
            Dictionary of delta metadata
        """
        metadata = {}

        # Extract modification_number if present (from transaction/award records)
        if "modification_number" in payload:
            metadata["modification_number"] = payload["modification_number"]

        # Extract action_date if present
        if "action_date" in payload:
            metadata["action_date"] = payload["action_date"]

        # Extract last_modified_date if present
        if "last_modified_date" in payload:
            metadata["last_modified_date"] = payload["last_modified_date"]

        # Extract award-level identifiers
        if "award_id" in payload:
            metadata["award_id"] = payload["award_id"]
        if "piid" in payload:
            metadata["piid"] = payload["piid"]

        return metadata

    async def get_recipient_by_uei(self, uei: str) -> dict[str, Any] | None:
        """Get recipient data by UEI.

        Args:
            uei: Unique Entity Identifier (12 characters)

        Returns:
            Recipient data dict or None if not found
        """
        try:
            # USAspending API v2 recipients endpoint
            # Note: Actual endpoint structure may need adjustment based on API docs
            response = await self._make_request(
                "GET",
                f"/recipients/{uei}/",
            )
            return response
        except USAspendingAPIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Recipient not found for UEI: {uei}")
                return None
            raise

    async def get_recipient_by_duns(self, duns: str) -> dict[str, Any] | None:
        """Get recipient data by DUNS number.

        Args:
            duns: DUNS number (9 digits)

        Returns:
            Recipient data dict or None if not found
        """
        try:
            # Search recipients by DUNS
            response = await self._make_request(
                "GET",
                "/recipients/",
                params={"duns": duns, "limit": 1},
            )
            results = response.get("results", [])
            return results[0] if results else None
        except USAspendingAPIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Recipient not found for DUNS: {duns}")
                return None
            raise

    async def get_recipient_by_cage(self, cage: str) -> dict[str, Any] | None:
        """Get recipient data by CAGE code.

        Args:
            cage: CAGE code (5 characters)

        Returns:
            Recipient data dict or None if not found
        """
        try:
            # Search recipients by CAGE
            response = await self._make_request(
                "GET",
                "/recipients/",
                params={"cage_code": cage, "limit": 1},
            )
            results = response.get("results", [])
            return results[0] if results else None
        except USAspendingAPIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Recipient not found for CAGE: {cage}")
                return None
            raise

    async def get_award_by_piid(self, piid: str) -> dict[str, Any] | None:
        """Get award data by PIID (Procurement Instrument Identifier).

        Args:
            piid: Contract/award PIID

        Returns:
            Award data dict or None if not found
        """
        try:
            response = await self._make_request(
                "GET",
                f"/awards/{piid}/",
            )
            return response
        except USAspendingAPIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Award not found for PIID: {piid}")
                return None
            raise

    async def get_transactions_by_recipient(
        self, uei: str, date_range: tuple[datetime, datetime] | None = None
    ) -> list[dict[str, Any]]:
        """Get transactions for a recipient by UEI.

        Args:
            uei: Unique Entity Identifier
            date_range: Optional tuple of (start_date, end_date)

        Returns:
            List of transaction records
        """
        params: dict[str, Any] = {"recipient_uei": uei, "limit": 1000}
        if date_range:
            params["action_date__gte"] = date_range[0].isoformat()
            params["action_date__lte"] = date_range[1].isoformat()

        try:
            response = await self._make_request("GET", "/search/spending_by_award/", params=params)
            return response.get("results", [])
        except USAspendingAPIError as e:
            logger.warning(f"Failed to fetch transactions for UEI {uei}: {e}")
            return []

    async def autocomplete_recipient(
        self,
        search_text: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Call the USAspending recipient autocomplete endpoint."""
        payload = {
            "search_text": search_text,
            "limit": limit,
        }
        return await self._make_request(
            "POST",
            "/autocomplete/recipient/",
            params=payload,
        )

    async def search_transactions(
        self,
        filters: dict[str, Any],
        fields: list[str],
        page: int = 1,
        limit: int = 100,
        sort: str | None = "Transaction Amount",
        order: str | None = "desc",
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search the spending_by_transaction endpoint with consistent defaults."""
        payload: dict[str, Any] = {
            "filters": filters,
            "fields": fields,
            "page": page,
            "limit": limit,
        }
        if sort:
            payload["sort"] = sort
        if order:
            payload["order"] = order
        if extra_payload:
            payload.update(extra_payload)

        return await self._make_request(
            "POST",
            "/search/spending_by_transaction/",
            params=payload,
        )

    async def fetch_award_details(self, award_id: str) -> dict[str, Any] | None:
        """Fetch detailed award information for PSC fallbacks."""
        try:
            return await self._make_request("GET", f"/awards/{award_id}/")
        except USAspendingAPIError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                logger.debug(f"Award not found for id: {award_id}")
                return None
            raise

    async def enrich_award(
        self,
        award_id: str,
        uei: str | None = None,
        duns: str | None = None,
        cage: str | None = None,
        piid: str | None = None,
        freshness_record: EnrichmentFreshnessRecord | None = None,
    ) -> dict[str, Any]:
        """Enrich an award using available identifiers with delta detection.

        Args:
            award_id: SBIR award identifier
            uei: Optional UEI for recipient lookup
            duns: Optional DUNS for recipient lookup
            cage: Optional CAGE code for recipient lookup
            piid: Optional PIID for award lookup
            freshness_record: Optional existing freshness record for delta detection

        Returns:
            Enrichment result with:
            - payload: API response data
            - payload_hash: SHA256 hash of payload
            - delta_detected: Whether payload differs from previous
            - metadata: Delta identifiers (modification_number, etc.)
            - success: Whether enrichment succeeded
            - error: Error message if failed
        """
        result: Any = {
            "payload": None,
            "payload_hash": None,
            "delta_detected": True,
            "metadata": {},
            "success": False,
            "error": None,
        }

        try:
            # Try recipient lookup by priority: UEI > DUNS > CAGE
            payload = None
            if uei:
                payload = await self.get_recipient_by_uei(uei)
            if not payload and duns:
                payload = await self.get_recipient_by_duns(duns)
            if not payload and cage:
                payload = await self.get_recipient_by_cage(cage)
            if not payload and piid:
                payload = await self.get_award_by_piid(piid)

            if not payload:
                result["error"] = "No recipient/award data found"
                return result

            # Compute payload hash
            payload_hash = self._compute_payload_hash(payload)

            # Extract delta metadata
            metadata = self._extract_delta_metadata(payload)

            # Check for delta if freshness record provided
            delta_detected = True
            if freshness_record:
                delta_detected = freshness_record.has_delta(payload_hash)

            result.update(
                {
                    "payload": payload,
                    "payload_hash": payload_hash,
                    "delta_detected": delta_detected,
                    "metadata": metadata,
                    "success": True,
                }
            )

        except USAspendingAPIError as e:
            result["error"] = str(e)
            logger.error(f"USAspending enrichment failed for award {award_id}: {e}")

        return result

    def load_state(self) -> dict[str, Any]:
        """Load refresh state from file.

        Returns:
            State dictionary with cursors, ETags, last fetch times, etc.
        """
        if not self.state_file.exists():
            return {}

        try:
            with open(self.state_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load state file {self.state_file}: {e}")
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        """Save refresh state to file.

        Args:
            state: State dictionary to save
        """
        try:
            from src.utils.common.path_utils import ensure_parent_dir

            ensure_parent_dir(self.state_file)
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save state file {self.state_file}: {e}")

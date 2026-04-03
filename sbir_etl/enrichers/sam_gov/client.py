"""SAM.gov API client for entity information.

This module provides an async client for querying the SAM.gov Entity Information API
to enrich SBIR awards with company data, UEI, CAGE codes, and entity information.
Supports rate limiting, retry logic, and state management.
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from loguru import logger

from ...config.loader import get_config
from ...exceptions import APIError, RateLimitError
from ..base_client import BaseAsyncAPIClient


# Backward compatibility: Alias to central exception classes
SAMGovAPIError = APIError
SAMGovRateLimitError = RateLimitError


class SAMGovAPIClient(BaseAsyncAPIClient):
    """Async client for SAM.gov Entity Information API v3."""

    api_name = "sam_gov"

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
        super().__init__()

        if config is None:
            cfg = get_config()
            self.api_config = cfg.enrichment.sam_gov
        else:
            self.api_config = config

        self.base_url = str(
            self.api_config.get("base_url", "https://api.sam.gov/entity-information/v3")
        )
        self.timeout = cast(int, self.api_config.get("timeout_seconds", 30))
        self.rate_limit_per_minute = cast(int, self.api_config.get("rate_limit_per_minute", 60))

        # Get API key from environment
        api_key_env_var = str(self.api_config.get("api_key_env_var", "SAM_GOV_API_KEY"))
        self.api_key = os.getenv(api_key_env_var)
        if not self.api_key:
            logger.warning(
                f"SAM.gov API key not found in {api_key_env_var}. "
                "API calls will fail without authentication."
            )

        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)

        logger.info(
            f"Initialized SAMGovAPIClient: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min"
        )

    def _build_headers(self) -> dict[str, str]:
        """Build default headers including API key if available."""
        headers = super()._build_headers()
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

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

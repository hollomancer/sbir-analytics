"""PatentsView API enricher module.

This module provides functionality to query the PatentsView API (PatentSearch API)
to retrieve patent data for companies and track patent reassignments.

The module supports:
- Querying patents by assignee organization name
- Finding assignee IDs using fuzzy name matching
- Tracking patent assignment history and reassignments
- Rate limiting and retry logic for API calls

Key Functions:
    - PatentsViewClient: Main client class for API interactions
    - retrieve_company_patents: Retrieve patents for a company
    - check_patent_reassignments: Check if patents were reassigned
"""

import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.loader import get_config
from src.exceptions import APIError, ConfigurationError
from src.utils.cache.api_cache import APICache


class RateLimiter:
    """Thread-safe rate limiter for PatentsView API calls.
    
    Tracks request timestamps and enforces rate limits by waiting when necessary.
    Thread-safe for use in parallel processing scenarios.
    """

    def __init__(self, rate_limit_per_minute: int = 60):
        """Initialize rate limiter.
        
        Args:
            rate_limit_per_minute: Maximum requests allowed per minute
        """
        self.rate_limit_per_minute = rate_limit_per_minute
        self.request_times: deque[datetime] = deque(maxlen=rate_limit_per_minute)
        self._lock = threading.Lock()  # Thread-safe lock

    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded.
        
        Removes requests older than 1 minute and waits if we're at the limit.
        Thread-safe for concurrent access.
        """
        with self._lock:
            now = datetime.now()
            # Remove requests older than 1 minute
            cutoff_time = now - timedelta(seconds=60)
            while self.request_times and self.request_times[0] < cutoff_time:
                self.request_times.popleft()

            # If we're at the limit, wait until the oldest request is 60 seconds old
            if len(self.request_times) >= self.rate_limit_per_minute:
                oldest = self.request_times[0]
                wait_seconds = 60 - (now - oldest).total_seconds() + 0.5  # Add 0.5s buffer
                if wait_seconds > 0:
                    logger.debug(
                        f"Rate limit reached ({self.rate_limit_per_minute}/min), "
                        f"waiting {wait_seconds:.1f} seconds"
                    )
                    # Release lock during sleep to allow other threads to check
                    self._lock.release()
                    try:
                        time.sleep(wait_seconds)
                    finally:
                        self._lock.acquire()
                    # Recalculate after sleep
                    now = datetime.now()
                    cutoff_time = now - timedelta(seconds=60)
                    while self.request_times and self.request_times[0] < cutoff_time:
                        self.request_times.popleft()

            # Record this request
            self.request_times.append(datetime.now())


class PatentsViewClient:
    """Client for interacting with PatentsView API (PatentSearch API).
    
    Provides methods to query patents by assignee, find assignee IDs,
    and track patent assignment history.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limit_per_minute: int | None = None,
        timeout_seconds: int | None = None,
    ):
        """Initialize PatentsView client.
        
        Args:
            api_key: PatentsView API key (if None, reads from config/env)
            base_url: Base URL for API (if None, reads from config)
            rate_limit_per_minute: Rate limit (if None, reads from config)
            timeout_seconds: Request timeout (if None, reads from config)
        """
        config = get_config()
        patentsview_config = config.enrichment.patentsview_api

        # Get API key from parameter, env var, or config
        if api_key is None:
            api_key_env_var = patentsview_config.get("api_key_env_var", "PATENTSVIEW_API_KEY")
            api_key = os.getenv(api_key_env_var)
            if not api_key:
                raise ConfigurationError(
                    f"PatentsView API key not found. Set {api_key_env_var} environment variable.",
                    config_key=f"enrichment.patentsview_api.api_key_env_var",
                )

        self.api_key = api_key
        self.base_url = base_url or patentsview_config.get(
            "base_url", "https://search.patentsview.org/api"
        )
        self.rate_limit_per_minute = rate_limit_per_minute or patentsview_config.get(
            "rate_limit_per_minute", 60
        )
        self.timeout_seconds = timeout_seconds or patentsview_config.get("timeout_seconds", 30)

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(rate_limit_per_minute=self.rate_limit_per_minute)

        # Initialize cache
        cache_config = patentsview_config.get("cache", {})
        cache_enabled = cache_config.get("enabled", True)
        cache_dir = cache_config.get("cache_dir", "data/cache/patentsview")
        cache_ttl = cache_config.get("ttl_hours", 24)
        self.cache = APICache(
            cache_dir=cache_dir,
            enabled=cache_enabled,
            ttl_hours=cache_ttl,
            default_cache_type="patents",
        )

        # HTTP client with default headers
        self.client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
        )

        logger.debug(
            f"PatentsView client initialized: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min, cache_enabled={cache_enabled}"
        )

    def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Make an API request with rate limiting and retry logic.
        
        Args:
            endpoint: API endpoint path (e.g., "/v1/patent")
            method: HTTP method (default: POST)
            json_data: JSON payload for POST requests
            max_retries: Maximum retry attempts
            
        Returns:
            JSON response as dictionary
            
        Raises:
            APIError: If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"

        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=2, min=2, max=10),
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            reraise=True,
        )
        def _do_request() -> httpx.Response:
            """Execute the HTTP request with rate limiting."""
            self.rate_limiter.wait_if_needed()

            try:
                if method == "POST":
                    response = self.client.post(url, json=json_data)
                else:
                    response = self.client.get(url)

                # Handle rate limiting
                if response.status_code == 429:
                    logger.warning("Rate limit exceeded, waiting before retry...")
                    time.sleep(60)  # Wait 1 minute
                    raise httpx.HTTPError("Rate limit exceeded")

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limit exceeded, waiting before retry...")
                    time.sleep(60)
                    raise httpx.HTTPError("Rate limit exceeded")
                raise APIError(
                    f"PatentsView API request failed: {e.response.status_code}",
                    api_name="patentsview",
                    endpoint=endpoint,
                    http_status=e.response.status_code,
                    retryable=e.response.status_code >= 500,
                ) from e

        try:
            response = _do_request()
            return response.json()
        except httpx.HTTPError as e:
            raise APIError(
                f"PatentsView API request failed: {str(e)}",
                api_name="patentsview",
                endpoint=endpoint,
                retryable=True,
            ) from e

    def query_patents_by_assignee(
        self,
        company_name: str,
        uei: str | None = None,
        duns: str | None = None,
        max_patents: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query patents assigned to a company.
        
        Args:
            company_name: Company name to search for
            uei: Optional UEI identifier (not used by PatentsView, but kept for consistency)
            duns: Optional DUNS identifier (not used by PatentsView, but kept for consistency)
            max_patents: Maximum number of patents to retrieve (default: 1000)
            
        Returns:
            List of patent records with patent_number, patent_title, patent_date, etc.
        """
        logger.debug(f"Querying patents for company: {company_name}")

        # Check cache first
        cached_df = self.cache.get(
            uei=uei, duns=duns, company_name=company_name, cache_type="patents"
        )
        if cached_df is not None:
            logger.debug(f"Using cached patents for {company_name}")
            return cached_df.to_dict(orient="records")

        all_patents: list[dict[str, Any]] = []
        page = 0
        per_page = 100  # PatentsView default page size

        while len(all_patents) < max_patents:
            query = {
                "q": {"assignee_organization": company_name},
                "f": [
                    "patent_number",
                    "patent_title",
                    "patent_date",
                    "assignee_organization",
                    "assignee_id",
                    "filing_date",
                    "grant_date",
                    "inventor",
                ],
                "o": {
                    "page": page,
                    "per_page": per_page,
                },
            }

            try:
                response = self._make_request("/v1/patent", json_data=query)
                patents = response.get("patents", [])

                if not patents:
                    break

                all_patents.extend(patents)
                logger.debug(f"Retrieved {len(patents)} patents (page {page}, total: {len(all_patents)})")

                # Check if there are more pages
                total_found = response.get("total_found", 0)
                if len(all_patents) >= total_found or len(patents) < per_page:
                    break

                page += 1

            except APIError as e:
                logger.error(f"Error querying patents for {company_name}: {e}")
                break

        patents_result = all_patents[:max_patents]
        logger.info(f"Found {len(patents_result)} patents for {company_name}")

        # Cache the results
        if patents_result:
            patents_df = pd.DataFrame(patents_result)
            self.cache.set(
                patents_df, uei=uei, duns=duns, company_name=company_name, cache_type="patents"
            )

        return patents_result

    def query_assignee_by_name(self, company_name: str) -> list[dict[str, Any]]:
        """Query assignee IDs by company name (fuzzy matching).
        
        Args:
            company_name: Company name to search for
            
        Returns:
            List of assignee records with assignee_id, assignee_organization, etc.
        """
        logger.debug(f"Querying assignees for company name: {company_name}")

        query = {
            "q": {"assignee_organization": company_name},
            "f": ["assignee_id", "assignee_organization", "assignee_type"],
        }

        try:
            response = self._make_request("/v1/assignee", json_data=query)
            assignees = response.get("assignees", [])
            logger.debug(f"Found {len(assignees)} assignee matches for {company_name}")
            return assignees
        except APIError as e:
            logger.error(f"Error querying assignees for {company_name}: {e}")
            return []

    def query_patent_assignments(self, patent_number: str) -> list[dict[str, Any]]:
        """Query assignment history for a specific patent.
        
        Note: PatentsView API may not have direct assignment history endpoint.
        This method queries the patent and extracts assignee information.
        For full assignment history, may need to use USPTO bulk data.
        
        Args:
            patent_number: Patent number to query
            
        Returns:
            List of assignment records (may be limited by API capabilities)
        """
        logger.debug(f"Querying assignment history for patent: {patent_number}")

        # Clean patent number (remove commas, spaces)
        clean_patent_number = re.sub(r"[,\s]", "", patent_number)

        query = {
            "q": {"patent_number": clean_patent_number},
            "f": [
                "patent_number",
                "assignee_organization",
                "assignee_id",
                "assignor",
            ],
        }

        try:
            response = self._make_request("/v1/patent", json_data=query)
            patents = response.get("patents", [])

            assignments = []
            for patent in patents:
                # Extract assignee information
                assignee_org = patent.get("assignee_organization")
                assignee_id = patent.get("assignee_id")
                assignor = patent.get("assignor")

                if assignee_org or assignee_id:
                    assignments.append(
                        {
                            "patent_number": clean_patent_number,
                            "assignee": assignee_org,
                            "assignee_id": assignee_id,
                            "assignor": assignor,
                        }
                    )

            logger.debug(f"Found {len(assignments)} assignment records for patent {patent_number}")
            return assignments

        except APIError as e:
            logger.error(f"Error querying assignments for patent {patent_number}: {e}")
            return []

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


def retrieve_company_patents(
    company_name: str,
    uei: str | None = None,
    duns: str | None = None,
    client: PatentsViewClient | None = None,
) -> pd.DataFrame:
    """Retrieve patents for a company from PatentsView API.
    
    Args:
        company_name: Company name to search for
        uei: Optional UEI identifier
        duns: Optional DUNS identifier
        client: Optional PatentsViewClient instance (creates new if None)
        
    Returns:
        DataFrame with patent details: patent_number, patent_title, patent_date, etc.
    """
    if client is None:
        client = PatentsViewClient()
        should_close = True
    else:
        should_close = False

    try:
        patents = client.query_patents_by_assignee(company_name, uei, duns)

        if not patents:
            return pd.DataFrame()

        # Normalize patent data
        normalized_patents = []
        for patent in patents:
            normalized_patents.append(
                {
                    "patent_number": patent.get("patent_number"),
                    "patent_title": patent.get("patent_title"),
                    "patent_date": patent.get("patent_date"),
                    "assignee_organization": patent.get("assignee_organization"),
                    "assignee_id": patent.get("assignee_id"),
                    "filing_date": patent.get("filing_date"),
                    "grant_date": patent.get("grant_date"),
                    "inventors": patent.get("inventor", []),
                }
            )

        df = pd.DataFrame(normalized_patents)
        return df

    finally:
        if should_close:
            client.close()


def check_patent_reassignments(
    patent_numbers: list[str],
    original_company_name: str,
    client: PatentsViewClient | None = None,
) -> pd.DataFrame:
    """Check if patents were reassigned to different companies.
    
    Args:
        patent_numbers: List of patent numbers to check
        original_company_name: Original company name (to compare against)
        client: Optional PatentsViewClient instance (creates new if None)
        
    Returns:
        DataFrame with reassignment details: patent_number, original_assignee,
        current_assignee, reassigned (boolean)
    """
    if client is None:
        client = PatentsViewClient()
        should_close = True
    else:
        should_close = False

    try:
        reassignments = []

        for patent_number in patent_numbers:
            assignments = client.query_patent_assignments(patent_number)

            for assignment in assignments:
                current_assignee = assignment.get("assignee")
                assignor = assignment.get("assignor")

                # Check if reassigned (current assignee differs from original)
                reassigned = False
                if current_assignee and current_assignee.lower() != original_company_name.lower():
                    reassigned = True

                reassignments.append(
                    {
                        "patent_number": patent_number,
                        "original_assignee": original_company_name,
                        "current_assignee": current_assignee,
                        "assignor": assignor,
                        "reassigned": reassigned,
                    }
                )

        df = pd.DataFrame(reassignments)
        return df

    finally:
        if should_close:
            client.close()


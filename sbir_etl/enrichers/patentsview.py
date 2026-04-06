"""USPTO Open Data Portal (ODP) patent enricher module.

This module provides functionality to query the USPTO ODP API
(formerly PatentsView at search.patentsview.org, migrated to data.uspto.gov
on March 20, 2026) to retrieve patent data for companies and track patent
reassignments.

The module supports:
- Querying patents by assignee organization name
- Finding assignee IDs using name matching
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
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sbir_etl.config.loader import get_config
from sbir_etl.exceptions import APIError, ConfigurationError
from sbir_etl.utils.cache.api_cache import APICache


class RateLimiter:
    """Thread-safe rate limiter for API calls.

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


def parse_patent_record(record: dict[str, Any]) -> dict[str, Any]:
    """Parse an ODP patent record into a normalized format.

    The ODP API returns patent file wrapper data with nested metadata.
    This function extracts and flattens the relevant fields into the format
    expected by downstream consumers.

    This is a module-level function so it can be reused by callers that
    don't instantiate a full :class:`PatentsViewClient` (e.g. the weekly
    awards report fallback path).

    Args:
        record: Raw patent record from ODP API response

    Returns:
        Normalized patent dict with standard field names
    """
    # ODP nests some fields under applicationMetaData
    metadata = record.get("applicationMetaData", {}) or {}

    patent_number = (
        metadata.get("patentNumber")
        or record.get("patentNumber")
        or record.get("applicationNumberText")
    )
    patent_title = (
        record.get("inventionTitle")
        or metadata.get("inventionTitle")
        or ""
    )
    filing_date = (
        record.get("filingDate")
        or metadata.get("filingDate")
    )
    grant_date = (
        metadata.get("grantDate")
        or record.get("grantDate")
    )

    # Extract assignee information
    assignees = record.get("assignees", []) or []
    assignee_org = None
    assignee_id = None
    if assignees:
        first_assignee = assignees[0] if isinstance(assignees, list) else assignees
        if isinstance(first_assignee, dict):
            assignee_org = first_assignee.get("assigneeName") or first_assignee.get("orgName")
            assignee_id = first_assignee.get("assigneeEntityId")

    # If assignee is at top level (varies by endpoint)
    if not assignee_org:
        assignee_org = record.get("assigneeName") or metadata.get("assigneeName")

    # Extract inventor information
    raw_inventors = record.get("inventors", []) or []
    inventors = []
    for inv in raw_inventors:
        if isinstance(inv, dict):
            name_parts = [
                inv.get("inventorFirstName", ""),
                inv.get("inventorLastName", ""),
            ]
            name = " ".join(p for p in name_parts if p).strip()
            if name:
                inventors.append(name)
        elif isinstance(inv, str):
            inventors.append(inv)

    return {
        "patent_number": patent_number,
        "patent_title": patent_title,
        "patent_date": grant_date,
        "assignee_organization": assignee_org,
        "assignee_id": assignee_id,
        "filing_date": filing_date,
        "grant_date": grant_date,
        "inventor": inventors,
    }


class PatentsViewClient:
    """Client for interacting with USPTO Open Data Portal (ODP) API.

    Provides methods to query patents by assignee, find assignee IDs,
    and track patent assignment history. This client was migrated from
    the PatentsView PatentSearch API (search.patentsview.org) to the
    USPTO ODP API (data.uspto.gov) following the March 2026 migration.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        rate_limit_per_minute: int | None = None,
        timeout_seconds: int | None = None,
        config=None,
    ):
        """Initialize USPTO ODP client.

        Args:
            api_key: USPTO ODP API key (if None, reads from config/env)
            base_url: Base URL for API (if None, reads from config)
            rate_limit_per_minute: Rate limit (if None, reads from config)
            timeout_seconds: Request timeout (if None, reads from config)
            config: Optional PipelineConfig. If None, loads from get_config().
        """
        config = config or get_config()
        patentsview_config: dict[str, object] = config.enrichment.patentsview_api  # type: ignore[assignment]

        # Get API key from parameter, env var, or config
        if api_key is None:
            api_key_env_var = patentsview_config.get("api_key_env_var", "USPTO_ODP_API_KEY")
            api_key = os.getenv(str(api_key_env_var))
            if not api_key:
                raise ConfigurationError(
                    f"USPTO ODP API key not found. Set {api_key_env_var} environment variable. "
                    f"Register at https://data.uspto.gov/apis/getting-started",
                    config_key="enrichment.patentsview_api.api_key_env_var",
                )

        self.api_key = api_key
        self.base_url = base_url or patentsview_config.get(
            "base_url", "https://data.uspto.gov/api/v1/patent/applications"
        )
        self.rate_limit_per_minute = rate_limit_per_minute or patentsview_config.get(
            "rate_limit_per_minute", 60
        )
        self.timeout_seconds = timeout_seconds or patentsview_config.get("timeout_seconds", 30)

        # Initialize rate limiter
        rate_limit: int = int(self.rate_limit_per_minute) if self.rate_limit_per_minute else 60  # type: ignore[call-overload]
        self.rate_limiter = RateLimiter(rate_limit_per_minute=rate_limit)  # type: ignore[arg-type]

        # Initialize cache
        cache_config = patentsview_config.get("cache", {})
        if isinstance(cache_config, dict):
            cache_enabled = cache_config.get("enabled", True)
            cache_dir = cache_config.get("cache_dir", "data/cache/patentsview")
            cache_ttl = cache_config.get("ttl_hours", 24)
        else:
            cache_enabled = True
            cache_dir = "data/cache/patentsview"
            cache_ttl = 24
        self.cache = APICache(
            cache_dir=cache_dir,
            enabled=cache_enabled,
            ttl_hours=cache_ttl,
            default_cache_type="patents",
        )

        # HTTP client with default headers
        # ODP uses X-API-KEY header (previously X-Api-Key for PatentsView)
        timeout_float: float = (
            float(self.timeout_seconds) if self.timeout_seconds is not None else 30.0  # type: ignore[arg-type]
        )
        self.client = httpx.Client(
            timeout=timeout_float,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
        )

        logger.debug(
            f"USPTO ODP client initialized: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min, cache_enabled={cache_enabled}"
        )

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Make an API request with rate limiting and retry logic.

        Args:
            endpoint: API endpoint path (e.g., "/search")
            method: HTTP method (default: GET)
            params: Query parameters for GET requests
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
                    response = self.client.get(url, params=params)

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
                    f"USPTO ODP API request failed: {e.response.status_code}",
                    api_name="uspto_odp",
                    endpoint=endpoint,
                    http_status=e.response.status_code,
                    retryable=e.response.status_code >= 500,
                ) from e

        try:
            response = _do_request()
            return response.json()
        except httpx.HTTPError as e:
            raise APIError(
                f"USPTO ODP API request failed: {str(e)}",
                api_name="uspto_odp",
                endpoint=endpoint,
                retryable=True,
            ) from e

    def _parse_patent_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Parse an ODP patent record into a normalized format.

        Delegates to the module-level :func:`parse_patent_record` function.

        Args:
            record: Raw patent record from ODP API response

        Returns:
            Normalized patent dict with standard field names
        """
        return parse_patent_record(record)

    def query_patents_by_assignee(
        self,
        company_name: str,
        uei: str | None = None,
        duns: str | None = None,
        max_patents: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query patents assigned to a company.

        Uses the ODP patent search endpoint with Lucene-style query syntax
        to find patents by assignee name.

        Args:
            company_name: Company name to search for
            uei: Optional UEI identifier (not used by ODP, but kept for consistency)
            duns: Optional DUNS identifier (not used by ODP, but kept for consistency)
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
            return cached_df.to_dict(orient="records")  # type: ignore[return-value]

        all_patents: list[dict[str, Any]] = []
        offset = 0
        limit = 100  # ODP page size

        # Escape special Lucene characters in company name for query
        escaped_name = self._escape_lucene_query(company_name)

        while len(all_patents) < max_patents:
            # ODP field-level Lucene queries go to the base endpoint (no
            # /search suffix).  The /search endpoint only accepts a
            # ``searchText`` free-text parameter and rejects ``q``.
            params = {
                "q": f'assigneeName:"{escaped_name}"',
                "offset": offset,
                "limit": limit,
            }

            try:
                response = self._make_request("", method="GET", params=params)

                # ODP response format: patentFileWrapperDataBag array
                records = response.get("patentFileWrapperDataBag", [])

                if not records:
                    break

                for record in records:
                    parsed = self._parse_patent_record(record)
                    if parsed.get("patent_number"):
                        all_patents.append(parsed)

                logger.debug(
                    f"Retrieved {len(records)} patents (offset {offset}, total: {len(all_patents)})"
                )

                # Check if there are more pages
                total_found = response.get("totalNumFound")
                if total_found is None:
                    total_found = response.get("totalResults")

                if total_found is not None:
                    try:
                        total_found = int(total_found)
                    except (TypeError, ValueError):
                        logger.warning(
                            f"Unexpected patent search total count {total_found!r}; "
                            "falling back to page-size-based pagination"
                        )
                        total_found = None

                if len(records) < limit:
                    break

                if total_found is not None and len(all_patents) >= total_found:
                    break

                offset += limit

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
        """Query assignee records by company name.

        The ODP API doesn't have a dedicated assignee endpoint like the old
        PatentsView API. Instead, we search patents by assignee name and
        extract unique assignee information from the results.

        Args:
            company_name: Company name to search for

        Returns:
            List of assignee records with assignee_id, assignee_organization, etc.
        """
        logger.debug(f"Querying assignees for company name: {company_name}")

        escaped_name = self._escape_lucene_query(company_name)
        params = {
            "q": f'assigneeName:"{escaped_name}"',
            "offset": 0,
            "limit": 25,
        }

        try:
            response = self._make_request("", method="GET", params=params)
            records = response.get("patentFileWrapperDataBag", [])

            # Deduplicate assignees from patent results
            seen_orgs: set[str] = set()
            assignees: list[dict[str, Any]] = []

            for record in records:
                record_assignees = record.get("assignees", []) or []
                for assignee in record_assignees:
                    if isinstance(assignee, dict):
                        org_name = assignee.get("assigneeName") or assignee.get("orgName")
                        if org_name and org_name.lower() not in seen_orgs:
                            seen_orgs.add(org_name.lower())
                            assignees.append({
                                "assignee_id": assignee.get("assigneeEntityId"),
                                "assignee_organization": org_name,
                                "assignee_type": assignee.get("assigneeTypeCategory"),
                            })

            logger.debug(f"Found {len(assignees)} assignee matches for {company_name}")
            return assignees
        except APIError as e:
            logger.error(f"Error querying assignees for {company_name}: {e}")
            return []

    def query_patent_assignments(self, patent_number: str) -> list[dict[str, Any]]:
        """Query assignment history for a specific patent.

        Uses the ODP assignment endpoint to retrieve assignment/reassignment
        records for a given patent.

        Args:
            patent_number: Patent number to query

        Returns:
            List of assignment records
        """
        logger.debug(f"Querying assignment history for patent: {patent_number}")

        # Clean patent number (remove commas, spaces)
        clean_patent_number = re.sub(r"[,\s]", "", patent_number)

        # First, find the application number for this patent
        # ODP uses application numbers for most detail endpoints
        params = {
            "q": f"applicationMetaData.patentNumber:{clean_patent_number}",
            "offset": 0,
            "limit": 1,
        }

        try:
            response = self._make_request("/search", method="GET", params=params)
            records = response.get("patentFileWrapperDataBag", [])

            if not records:
                logger.debug(f"No application found for patent {patent_number}")
                return []

            app_number = records[0].get("applicationNumberText")
            if not app_number:
                logger.debug(f"No application number in response for patent {patent_number}")
                # Fall back to extracting assignee from the search result
                parsed = self._parse_patent_record(records[0])
                if parsed.get("assignee_organization"):
                    return [{
                        "patent_number": clean_patent_number,
                        "assignee": parsed["assignee_organization"],
                        "assignee_id": parsed.get("assignee_id"),
                        "assignor": None,
                    }]
                return []

            # Fetch assignment data for this application
            assignment_response = self._make_request(
                f"/{app_number}/assignment", method="GET"
            )

            assignments = []
            assignment_records = assignment_response.get("patentAssignmentDataBag", [])
            if not assignment_records:
                # Try alternate response key
                assignment_records = assignment_response.get("assignments", [])

            for assignment in assignment_records:
                if isinstance(assignment, dict):
                    assignee_name = (
                        assignment.get("assigneeName")
                        or assignment.get("assigneeEntityName")
                    )
                    assignor_name = (
                        assignment.get("assignorName")
                        or assignment.get("assignorEntityName")
                    )
                    assignments.append({
                        "patent_number": clean_patent_number,
                        "assignee": assignee_name,
                        "assignee_id": assignment.get("assigneeEntityId"),
                        "assignor": assignor_name,
                    })

            # If no assignment endpoint data, fall back to patent record assignee
            if not assignments:
                parsed = self._parse_patent_record(records[0])
                if parsed.get("assignee_organization"):
                    assignments.append({
                        "patent_number": clean_patent_number,
                        "assignee": parsed["assignee_organization"],
                        "assignee_id": parsed.get("assignee_id"),
                        "assignor": None,
                    })

            logger.debug(f"Found {len(assignments)} assignment records for patent {patent_number}")
            return assignments

        except APIError as e:
            logger.error(f"Error querying assignments for patent {patent_number}: {e}")
            return []

    @staticmethod
    def _escape_lucene_query(text: str) -> str:
        """Escape special Lucene query characters.

        Args:
            text: Raw query text

        Returns:
            Escaped text safe for Lucene queries
        """
        # Lucene special characters: + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
        special_chars = r'([+\-&|!(){}\[\]^"~*?:\\/])'
        return re.sub(special_chars, r'\\\1', text)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()


def retrieve_company_patents(
    company_name: str,
    uei: str | None = None,
    duns: str | None = None,
    client: PatentsViewClient | None = None,
) -> pd.DataFrame:
    """Retrieve patents for a company from USPTO ODP API.

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

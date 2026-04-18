"""Solicitation topic extractor for SBIR.gov.

Pulls solicitation topic descriptions from the SBIR.gov API.  The API
exposes a ``/solicitations`` endpoint that returns topics with full
descriptions — the 500-3000 word technical prose that describes the
government's research needs.

This is the highest-value text for LightRAG entity extraction because
solicitation descriptions are far richer than award abstracts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import APIError

try:
    import httpx

    _RETRYABLE_HTTPX = (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError)
except ImportError:
    httpx = None  # type: ignore[assignment]
    _RETRYABLE_HTTPX = (Exception,)  # type: ignore[assignment]  # fallback when httpx absent

SBIR_GOV_API_BASE = "https://api.www.sbir.gov/public/api"


class SolicitationExtractor:
    """Extract solicitation topic descriptions from SBIR.gov.

    Pulls full topic text including:
    - Topic title and description (500-3000 words)
    - Agency, branch, and program
    - Open/close dates
    - Topic number and solicitation number

    Args:
        base_url: SBIR.gov API base URL.
        timeout: HTTP request timeout in seconds.
        http_client: Optional pre-configured httpx.Client.
    """

    def __init__(
        self,
        *,
        base_url: str = SBIR_GOV_API_BASE,
        timeout: float = 30.0,
        http_client: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client

    @property
    def client(self) -> Any:
        if self._client is None:
            if httpx is None:
                raise ImportError("httpx is required for SolicitationExtractor")
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_HTTPX),
        reraise=True,
    )
    def _query_solicitations(
        self,
        *,
        agency: str | None = None,
        year: int | None = None,
        keyword: str | None = None,
        start: int = 0,
        rows: int = 100,
    ) -> list[dict[str, Any]]:
        """Query SBIR.gov solicitations endpoint.

        Args:
            agency: Agency abbreviation filter.
            year: Solicitation year filter.
            keyword: Free-text keyword search (topic code or solicitation number).
            start: Pagination offset.
            rows: Results per page.

        Returns:
            List of solicitation topic dicts.
        """
        params: dict[str, str | int] = {"start": start, "rows": rows}
        if agency:
            params["agency"] = agency
        if year:
            params["year"] = year
        if keyword:
            params["keyword"] = keyword

        url = f"{self.base_url}/solicitations"
        logger.debug(f"SBIR.gov solicitations request: {url} params={params}")

        response = self.client.get(url, params=params)

        # Raise httpx.HTTPStatusError for transient failures so tenacity retries them.
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()

        if response.status_code != 200:
            raise APIError(
                f"SBIR.gov API returned {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("results") or data.get("data") or []
        return []

    def query_by_keyword(
        self,
        keyword: str,
        max_results: int = 25,
    ) -> list[dict[str, Any]]:
        """Search solicitations by keyword (topic code or solicitation number).

        Useful for finding topics when the solicitation year is unknown.

        Args:
            keyword: Topic code, solicitation number, or free-text query.
            max_results: Maximum results to return.

        Returns:
            List of normalized topic dicts.
        """
        try:
            return self._query_solicitations(keyword=keyword, rows=max_results)
        except Exception as e:
            logger.debug(f"SBIR.gov keyword query failed for '{keyword}': {e}")
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_HTTPX),
        reraise=True,
    )
    def _query_awards(
        self,
        keyword: str,
        rows: int = 5,
    ) -> list[dict[str, Any]]:
        """Query SBIR.gov awards endpoint by keyword.

        Used as fallback when a topic code isn't found via ``/solicitations``.
        Award records often contain topic titles and abstracts that can
        substitute for missing solicitation descriptions.

        Args:
            keyword: Topic code to search for.
            rows: Maximum results.

        Returns:
            List of award dicts.
        """
        url = f"{self.base_url}/awards"
        params: dict[str, str | int] = {"keyword": keyword, "rows": rows, "start": 0}
        logger.debug(f"SBIR.gov awards fallback request: {url} params={params}")

        response = self.client.get(url, params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            response.raise_for_status()
        if response.status_code != 200:
            return []

        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("results") or data.get("data") or []
        return []

    def query_awards_for_topic(
        self,
        topic_code: str,
    ) -> dict[str, Any] | None:
        """Find topic metadata via the awards endpoint as a last resort.

        Searches awards by topic code and extracts topic-level metadata
        (title, description, agency, program) from the first matching award.

        Args:
            topic_code: The topic code to search for.

        Returns:
            Normalized topic dict with ``topic_code``, ``title``,
            ``description``, ``agency``, ``program`` keys, or ``None``.
        """
        try:
            awards = self._query_awards(topic_code)
        except Exception as e:
            logger.debug(f"Awards fallback failed for '{topic_code}': {e}")
            return None

        for award in awards:
            award_tc = award.get("topicCode") or award.get("topic_code") or ""
            if award_tc != topic_code:
                continue
            title = (
                award.get("topicTitle")
                or award.get("topic_title")
                or award.get("awardTitle")
                or award.get("award_title")
                or ""
            )
            desc = (
                award.get("topicDescription")
                or award.get("topic_description")
                or award.get("abstract")
                or award.get("Abstract")
                or None
            )
            if title or desc:
                return {
                    "topic_code": topic_code,
                    "title": title,
                    "description": desc,
                    "agency": award.get("agency"),
                    "program": award.get("program"),
                }
        return None

    def extract_topics(
        self,
        *,
        agency: str | None = None,
        year: int | None = None,
        max_results: int = 100_000,
        page_size: int = 100,
    ) -> pd.DataFrame:
        """Extract solicitation topics with full descriptions.

        Paginates through the SBIR.gov solicitations API and normalizes
        the response into a DataFrame.

        Args:
            agency: Filter by agency abbreviation.
            year: Filter by solicitation year.
            max_results: Safety cap on total results.
            page_size: Results per API call.

        Returns:
            DataFrame with columns: topic_code, solicitation_number, title,
            description, agency, branch, program, open_date, close_date, year.
        """
        all_topics: list[dict[str, Any]] = []
        offset = 0

        while len(all_topics) < max_results:
            batch = self._query_solicitations(
                agency=agency, year=year, start=offset, rows=page_size
            )
            if not batch:
                break

            all_topics.extend(batch)
            offset += len(batch)

            if len(batch) < page_size:
                break  # Last page

            logger.info(f"Fetched {len(all_topics)} solicitation topics so far")

        logger.info(f"Extracted {len(all_topics)} total solicitation topics")

        if not all_topics:
            return pd.DataFrame(
                columns=[
                    "topic_code",
                    "solicitation_number",
                    "title",
                    "description",
                    "agency",
                    "branch",
                    "program",
                    "open_date",
                    "close_date",
                    "year",
                ]
            )

        # Normalize API response fields
        rows = []
        for topic in all_topics:
            rows.append(
                {
                    "topic_code": topic.get("topicCode") or topic.get("topic_code") or "",
                    "solicitation_number": (
                        topic.get("solicitationNumber") or topic.get("solicitation_number") or ""
                    ),
                    "title": topic.get("topicTitle") or topic.get("title") or "",
                    "description": topic.get("topicDescription") or topic.get("description"),
                    "agency": topic.get("agency"),
                    "branch": topic.get("branch"),
                    "program": topic.get("program"),
                    "open_date": topic.get("openDate") or topic.get("open_date"),
                    "close_date": topic.get("closeDate") or topic.get("close_date"),
                    "year": topic.get("solicitationYear") or topic.get("year"),
                }
            )

        return pd.DataFrame(rows)

    def deduplicate_topics(self, topics_df: pd.DataFrame) -> pd.DataFrame:
        """Deduplicate topics by (topic_code, solicitation_number).

        Keeps the first occurrence (which typically has the most complete data).

        Args:
            topics_df: Raw extracted topics DataFrame.

        Returns:
            Deduplicated DataFrame.
        """
        if topics_df.empty:
            return topics_df

        before = len(topics_df)
        deduped = topics_df.drop_duplicates(
            subset=["topic_code", "solicitation_number"], keep="first"
        )
        removed = before - len(deduped)
        if removed > 0:
            logger.info(f"Removed {removed} duplicate solicitation topics")
        return deduped.reset_index(drop=True)

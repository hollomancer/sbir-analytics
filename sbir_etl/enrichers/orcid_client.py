"""ORCID public API client for researcher profile lookups.

Queries the `ORCID public API <https://pub.orcid.org/>`_ to find
researcher profiles and extract affiliations, works, funding, and
keywords.

No API key is required for basic access.  Set ``ORCID_ACCESS_TOKEN``
for higher rate limits (generate via client credentials grant with a
free ORCID Public API application).

Usage::

    from sbir_etl.enrichers.orcid_client import ORCIDClient

    client = ORCIDClient()
    record = client.lookup("Jane Smith")
    if record:
        print(record.orcid_id, record.works_count)
    client.close()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

ORCID_API_URL = "https://pub.orcid.org/v3.0"


@dataclass
class ORCIDRecord:
    """Key data from an ORCID researcher profile."""

    orcid_id: str
    given_name: str | None = None
    family_name: str | None = None
    affiliations: list[str] = field(default_factory=list)
    works_count: int = 0
    sample_work_titles: list[str] = field(default_factory=list)
    funding_count: int = 0
    keywords: list[str] = field(default_factory=list)


def _parse_profile(orcid_id: str, search_result: dict, profile: dict) -> ORCIDRecord:
    """Parse an ORCID profile response into an :class:`ORCIDRecord`."""
    # Affiliations
    affiliations: list[str] = []
    affiliation_groups = (
        profile.get("activities-summary", {})
        .get("employments", {})
        .get("affiliation-group", [])
    )
    for group in affiliation_groups[:10]:
        for s in group.get("summaries", []):
            org_name = (
                s.get("employment-summary", {})
                .get("organization", {})
                .get("name", "")
            )
            if org_name and org_name not in affiliations:
                affiliations.append(org_name)

    # Works
    works_group = (
        profile.get("activities-summary", {})
        .get("works", {})
        .get("group", [])
    )
    sample_titles: list[str] = []
    for wg in works_group[:5]:
        summaries = wg.get("work-summary", [])
        if summaries:
            title_val = (
                summaries[0].get("title", {}).get("title", {}).get("value", "")
            )
            if title_val:
                sample_titles.append(title_val)

    # Funding
    funding_group = (
        profile.get("activities-summary", {})
        .get("fundings", {})
        .get("group", [])
    )

    # Keywords
    keyword_list = (
        profile.get("person", {}).get("keywords", {}).get("keyword", [])
    )
    keywords = [kw.get("content", "") for kw in keyword_list[:10] if kw.get("content")]

    return ORCIDRecord(
        orcid_id=orcid_id,
        given_name=search_result.get("given-names"),
        family_name=search_result.get("family-names"),
        affiliations=affiliations,
        works_count=len(works_group),
        sample_work_titles=sample_titles,
        funding_count=len(funding_group),
        keywords=keywords,
    )


class ORCIDClient:
    """Client for querying the ORCID public API.

    Args:
        rate_limiter: Optional rate limiter instance with ``wait_if_needed()`` method.
        access_token: Optional OAuth token. Defaults to ``ORCID_ACCESS_TOKEN`` env var.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: Any | None = None,
        access_token: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._limiter = rate_limiter
        headers: dict[str, str] = {"Accept": "application/json"}
        token = access_token or os.environ.get("ORCID_ACCESS_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ORCIDClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self) -> None:
        if self._limiter is not None:
            self._limiter.wait_if_needed()

    def search(self, family_name: str, given_names: str | None = None, limit: int = 5) -> list[dict]:
        """Search for researchers by name.

        Returns list of expanded search result dicts.
        """
        query = f"family-name:{family_name}"
        if given_names:
            query += f"+AND+given-names:{given_names}"

        self._wait()
        try:
            resp = self._client.get(
                f"{ORCID_API_URL}/expanded-search/",
                params={"q": query, "rows": limit},
            )
            if resp.status_code != 200:
                logger.debug(f"ORCID search returned {resp.status_code}")
                return []
            return resp.json().get("expanded-result", []) or []
        except httpx.HTTPError as e:
            logger.debug(f"ORCID search error: {e}")
            return []

    def get_profile(self, orcid_id: str) -> dict | None:
        """Fetch a full ORCID profile by ID."""
        self._wait()
        try:
            resp = self._client.get(f"{ORCID_API_URL}/{orcid_id}/record")
            if resp.status_code != 200:
                logger.debug(f"ORCID profile {orcid_id} returned {resp.status_code}")
                return None
            return resp.json()
        except httpx.HTTPError as e:
            logger.debug(f"ORCID profile error for {orcid_id}: {e}")
            return None

    def lookup(self, name: str) -> ORCIDRecord | None:
        """Look up a researcher's ORCID profile by full name.

        Splits *name* into given/family components, searches, then
        fetches the full profile for the best match.
        """
        parts = name.strip().split()
        if not parts:
            return None
        family = parts[-1]
        given = " ".join(parts[:-1]) if len(parts) > 1 else None

        results = self.search(family, given)
        if not results:
            return None

        best = results[0]
        orcid_id = best.get("orcid-id", "")
        if not orcid_id:
            return None

        profile = self.get_profile(orcid_id)
        if profile is None:
            return None

        return _parse_profile(orcid_id, best, profile)

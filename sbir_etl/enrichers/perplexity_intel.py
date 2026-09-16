"""Perplexity AI Premium Sources enricher — PitchBook Essentials + CB Insights.

Uses Perplexity's ``sonar-pro`` model with ``@PitchBook`` and
``@CB Insights`` source connectors to surface firmographic and
market-context signals that are not available from SAM.gov, SEC
EDGAR, or OpenCorporates.

**Unique value over existing enrichers:**

- Post-award VC/PE funding rounds (PitchBook Essentials) — company
  survival proxy and commercialization outcome signal
- Investor profiles: which firms co-invest downstream of SBIR
- Acquirer/acquisition status (exit type: IPO, M&A, defunct)
- CB Insights sector/market-map classification — technology readiness
  context and competitive-density signal
- CB Insights industry reports for agency-sector investment alignment
  benchmarking

**PitchBook Essentials limitations (track carefully):**

- No round-level financials or valuations (full PitchBook paywall)
- No cap-table data
- Company existence confirmed; funding *count* (not amount) available
- CB Insights report access is curated subset, not full library

**Access model:**

This client calls the Perplexity Chat Completions API (``sonar-pro``)
with structured prompts that invoke the ``@PitchBook`` and
``@CB Insights`` connectors. It does NOT call PitchBook or CB Insights
APIs directly — results depend on Perplexity's connector indexing
freshness. Set ``PERPLEXITY_API_KEY`` in your environment.

**Evaluation status:**

This module is scaffolded for evaluation. Before promoting to a
standard enrichment step, the following must be assessed:

1. Match-rate: % of SBIR awardees surfaced in PitchBook Essentials
2. Latency / cost per record at scale (sonar-pro pricing)
3. Connector freshness vs. canonical PitchBook data
4. Whether CB Insights classifications align with existing NAICS/CET taxonomy

See ``specs/perplexity-intel-enricher/REQUIREMENTS.md`` for full spec.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncPerplexityIntelClient

    with SyncPerplexityIntelClient() as client:
        record = client.company_intel("Anduril Industries")
        if record:
            print(record.funding_rounds_confirmed, record.investor_names)

        ctx = client.market_context("directed-energy weapons", agency="DoD")
        if ctx:
            print(ctx.sector_classification, ctx.competitive_density)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError, ConfigurationError

PERPLEXITY_API_URL = "https://api.perplexity.ai"
DEFAULT_MODEL = "sonar-pro"
DEFAULT_RATE_LIMIT_PER_MINUTE = 20  # Conservative; sonar-pro rate limits not yet benchmarked


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PerplexityIntelRecord:
    """Firmographic intel for a single SBIR awardee from PitchBook Essentials.

    Fields mirror the PitchBook Essentials dataset scope. Fields that are
    *not* available in Essentials (round financials, valuations, cap table)
    are intentionally absent — see module docstring for scope notes.
    """

    company_name: str
    # PitchBook signals
    pitchbook_confirmed: bool = False  # True if PitchBook returned a match
    funding_rounds_confirmed: int | None = None  # Count of rounds, not amount
    latest_funding_stage: str | None = None  # e.g. "Series A", "Seed"
    investor_names: list[str] = field(default_factory=list)
    acquisition_status: str | None = None  # "Acquired", "IPO", "Active", "Defunct"
    acquirer_name: str | None = None
    year_founded: int | None = None
    employee_range: str | None = None
    # CB Insights signals
    cbinsights_confirmed: bool = False
    sector_classification: str | None = None  # CB Insights sector label
    market_map_segments: list[str] = field(default_factory=list)
    # Provenance
    perplexity_citations: list[str] = field(default_factory=list)
    raw_response: str | None = None  # Full model text for audit
    model_used: str = DEFAULT_MODEL


@dataclass
class MarketContextRecord:
    """Sector/market-map context for a technology area from CB Insights."""

    query: str
    agency: str | None = None
    sector_classification: str | None = None
    competitive_density: str | None = None  # e.g. "crowded", "sparse", "emerging"
    key_players: list[str] = field(default_factory=list)
    investment_trend_summary: str | None = None
    relevant_report_titles: list[str] = field(default_factory=list)
    perplexity_citations: list[str] = field(default_factory=list)
    raw_response: str | None = None
    model_used: str = DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class PerplexityIntelClient(BaseAsyncAPIClient):
    """Async Perplexity AI client for PitchBook + CB Insights enrichment.

    Subclasses :class:`BaseAsyncAPIClient` for shared rate limiting,
    retry, and error translation. For sync callers, use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncPerplexityIntelClient`
    (sync wrapper not yet implemented — add to sync_wrappers.py before
    production use).

    Args:
        api_key: Perplexity API key. Defaults to ``PERPLEXITY_API_KEY``
            environment variable.
        model: Perplexity model name. Defaults to ``sonar-pro``.
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute ceiling.
        shared_limiter: Optional shared :class:`RateLimiter` for
            multi-threaded workers.
        http_client: Optional pre-built :class:`httpx.AsyncClient`
            for testing.
    """

    api_name = "perplexity_intel"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = 60,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        self.base_url = PERPLEXITY_API_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self.model = model
        self._api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        if not self._api_key:
            raise ConfigurationError(
                "PERPLEXITY_API_KEY is not set",
                config_key="PERPLEXITY_API_KEY",
            )
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _build_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        """Call Perplexity chat completions endpoint.

        Args:
            system_prompt: System role instructions.
            user_prompt: User query, optionally prefixed with @Source connectors.
            sources: List of Perplexity Premium Source names to restrict
                results to, e.g. ``["PitchBook", "CB Insights"]``.

        Returns:
            Raw API response dict.

        Raises:
            APIError: On HTTP or parse failure.
            ConfigurationError: If API key is missing.
        """
        # Prepend source connectors to the user prompt
        if sources:
            connector_prefix = " ".join(f"@{s}" for s in sources)
            user_prompt = f"{connector_prefix} {user_prompt}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        return await self._make_request("POST", "chat/completions", params=payload)

    # ------------------------------------------------------------------
    # Company intel (PitchBook Essentials + CB Insights)
    # ------------------------------------------------------------------

    async def company_intel(
        self,
        company_name: str,
        *,
        include_cbinsights: bool = True,
    ) -> PerplexityIntelRecord | None:
        """Retrieve firmographic and funding intel for an SBIR awardee.

        Queries PitchBook Essentials (and optionally CB Insights) via
        Perplexity Premium Sources. Returns a :class:`PerplexityIntelRecord`
        or ``None`` if the company is not found in either source.

        Args:
            company_name: Legal name of the SBIR awardee.
            include_cbinsights: Whether to also query CB Insights for
                sector classification. Adds latency; disable for bulk runs
                where only funding status is needed.
        """
        sources = ["PitchBook"]
        if include_cbinsights:
            sources.append("CB Insights")

        system_prompt = (
            "You are a structured data extractor. Answer ONLY with the requested fields "
            "in JSON. Do not explain or add commentary. If a field is unknown, use null. "
            "Do not infer or hallucinate values not present in the source material."
        )
        user_prompt = (
            f"Company: {company_name}\n\n"
            "Return a JSON object with these fields:\n"
            "- pitchbook_confirmed: bool (true if PitchBook has a record)\n"
            "- funding_rounds_confirmed: int or null (number of funding rounds, no amounts)\n"
            "- latest_funding_stage: string or null (e.g. Seed, Series A)\n"
            "- investor_names: list of strings (lead investors only, max 5)\n"
            "- acquisition_status: string or null (Acquired, IPO, Active, Defunct)\n"
            "- acquirer_name: string or null\n"
            "- year_founded: int or null\n"
            "- employee_range: string or null (e.g. '11-50')\n"
            "- cbinsights_confirmed: bool (true if CB Insights has a record)\n"
            "- sector_classification: string or null (CB Insights sector label)\n"
            "- market_map_segments: list of strings\n"
        )

        try:
            response = await self._chat(system_prompt, user_prompt, sources=sources)
        except APIError as e:
            logger.warning(f"PerplexityIntel: API error for '{company_name}': {e}")
            return None

        content = ""
        citations: list[str] = []
        try:
            choices = response.get("choices", [])
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content", "")
            citations = [c.get("url", "") for c in response.get("citations", []) if c.get("url")]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning(f"PerplexityIntel: unexpected response shape for '{company_name}': {exc}")
            return None

        # Parse JSON from model response
        import json
        import re

        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content.strip()
        try:
            data: dict[str, Any] = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning(
                f"PerplexityIntel: JSON parse failed for '{company_name}'; raw='{content[:200]}'"
            )
            return PerplexityIntelRecord(
                company_name=company_name,
                raw_response=content,
                perplexity_citations=citations,
                model_used=self.model,
            )

        if not data.get("pitchbook_confirmed") and not data.get("cbinsights_confirmed"):
            logger.debug(f"PerplexityIntel: no match in either source for '{company_name}'")
            return None

        return PerplexityIntelRecord(
            company_name=company_name,
            pitchbook_confirmed=bool(data.get("pitchbook_confirmed")),
            funding_rounds_confirmed=data.get("funding_rounds_confirmed"),
            latest_funding_stage=data.get("latest_funding_stage"),
            investor_names=data.get("investor_names") or [],
            acquisition_status=data.get("acquisition_status"),
            acquirer_name=data.get("acquirer_name"),
            year_founded=data.get("year_founded"),
            employee_range=data.get("employee_range"),
            cbinsights_confirmed=bool(data.get("cbinsights_confirmed")),
            sector_classification=data.get("sector_classification"),
            market_map_segments=data.get("market_map_segments") or [],
            perplexity_citations=citations,
            raw_response=content,
            model_used=self.model,
        )

    # ------------------------------------------------------------------
    # Market context (CB Insights)
    # ------------------------------------------------------------------

    async def market_context(
        self,
        technology_area: str,
        *,
        agency: str | None = None,
    ) -> MarketContextRecord | None:
        """Retrieve CB Insights market-map and sector context for a technology area.

        Intended for agency-sector alignment analysis: place an SBIR-funded
        technology within CB Insights' market-map to assess whether the
        funded tech is entering a crowded or sparse segment.

        Args:
            technology_area: Technology area or topic, e.g.
                "directed-energy weapons", "mRNA vaccine delivery".
            agency: Optional funding agency for context (e.g. "DoD", "NIH").
        """
        system_prompt = (
            "You are a structured data extractor. Answer ONLY with the requested fields "
            "in JSON. Do not explain or add commentary. If a field is unknown, use null."
        )
        agency_clause = f" in the context of {agency} funding" if agency else ""
        user_prompt = (
            f"Technology area: {technology_area}{agency_clause}\n\n"
            "Return a JSON object with:\n"
            "- sector_classification: string (CB Insights sector label)\n"
            "- competitive_density: string (crowded | emerging | sparse | null)\n"
            "- key_players: list of company names (max 6)\n"
            "- investment_trend_summary: string (1–2 sentences, null if unknown)\n"
            "- relevant_report_titles: list of CB Insights report titles (max 3)\n"
        )

        try:
            response = await self._chat(system_prompt, user_prompt, sources=["CB Insights"])
        except APIError as e:
            logger.warning(f"PerplexityIntel: market_context API error for '{technology_area}': {e}")
            return None

        content = ""
        citations: list[str] = []
        try:
            choices = response.get("choices", [])
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content", "")
            citations = [c.get("url", "") for c in response.get("citations", []) if c.get("url")]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning(f"PerplexityIntel: unexpected response shape for '{technology_area}': {exc}")
            return None

        import json
        import re

        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        raw_json = json_match.group(1) if json_match else content.strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning(
                f"PerplexityIntel: JSON parse failed for '{technology_area}'; raw='{content[:200]}'"
            )
            return MarketContextRecord(
                query=technology_area,
                agency=agency,
                raw_response=content,
                perplexity_citations=citations,
                model_used=self.model,
            )

        return MarketContextRecord(
            query=technology_area,
            agency=agency,
            sector_classification=data.get("sector_classification"),
            competitive_density=data.get("competitive_density"),
            key_players=data.get("key_players") or [],
            investment_trend_summary=data.get("investment_trend_summary"),
            relevant_report_titles=data.get("relevant_report_titles") or [],
            perplexity_citations=citations,
            raw_response=content,
            model_used=self.model,
        )

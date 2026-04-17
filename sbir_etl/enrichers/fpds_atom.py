"""FPDS Atom Feed client for real-time federal procurement data.

The FPDS (Federal Procurement Data System) Atom Feed at
``https://www.fpds.gov/ezsearch/LATEST`` provides public, real-time access
to federal contract records. Unlike USAspending (which lags weeks/months),
FPDS updates within 3 days of contract action.

Key data available via FPDS Atom:
- Contract descriptions (``descriptionOfContractRequirement``)
- SBIR/STTR research codes (Element 10Q: SR1–SR3, ST1–ST3)
- Vendor information (name, UEI, CAGE, DUNS)
- PSC and NAICS codes
- Contract values and dates
- Competition type and solicitation info

No API key is required — the Atom feed is fully public.

This client inherits shared rate limiting, retry, and error
translation from :class:`BaseAsyncAPIClient` via the body-agnostic
:meth:`BaseAsyncAPIClient._request_raw` (FPDS returns Atom XML, not
JSON). Synchronous callers should use
:class:`sbir_etl.enrichers.sync_wrappers.SyncFPDSAtomClient`.

Usage (sync)::

    from sbir_etl.enrichers.sync_wrappers import SyncFPDSAtomClient

    with SyncFPDSAtomClient() as client:
        record = client.search_by_piid("FA2541-26-C-B005")
        if record:
            print(record.description)
            print(record.research_code)  # e.g. "SR1" for SBIR Phase I
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from sbir_etl.enrichers.base_client import BaseAsyncAPIClient
from sbir_etl.enrichers.rate_limiting import RateLimiter
from sbir_etl.exceptions import APIError

FPDS_BASE_URL = "https://www.fpds.gov/ezsearch"
FPDS_ENDPOINT = "LATEST"
# Full URL retained for callers/tests that reference it
FPDS_ATOM_URL = f"{FPDS_BASE_URL}/{FPDS_ENDPOINT}"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
DEFAULT_RATE_LIMIT_PER_MINUTE = 60


@dataclass
class FPDSRecord:
    """Parsed FPDS contract record from the Atom feed."""

    piid: str
    description: str | None = None
    research_code: str | None = None
    vendor_name: str | None = None
    vendor_uei: str | None = None
    vendor_duns: str | None = None
    vendor_cage: str | None = None
    psc_code: str | None = None
    naics_code: str | None = None
    agency_name: str | None = None
    awarding_office: str | None = None
    obligated_amount: float | None = None
    signed_date: str | None = None
    completion_date: str | None = None
    solicitation_id: str | None = None
    competition_type: str | None = None
    raw_xml: str | None = field(default=None, repr=False)


def _find_local(element: ET.Element, local_name: str) -> ET.Element | None:
    """Find a descendant element by local name, ignoring XML namespaces.

    Python's ElementTree doesn't support XPath ``local-name()``, so we
    iterate and strip namespace prefixes manually.
    """
    for el in element.iter():
        # Tag may be ``{namespace}localName`` or just ``localName``
        tag = el.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if tag == local_name:
            return el
    return None


def _text(element: ET.Element, local_name: str) -> str | None:
    """Extract text from a descendant element by local name."""
    el = _find_local(element, local_name)
    if el is not None and el.text:
        return el.text.strip()
    return None


def _attr(element: ET.Element, local_name: str, attr: str = "description") -> str | None:
    """Extract an attribute value from a descendant element by local name."""
    el = _find_local(element, local_name)
    if el is not None:
        return el.get(attr)
    return None


def _parse_entry(entry: ET.Element, piid: str) -> FPDSRecord:
    """Parse an Atom ``<entry>`` element into an :class:`FPDSRecord`.

    Extracts fields from the inner FPDS XML nested inside
    ``<atom:content>``, falling back to Atom-level elements where needed.
    """
    content_el = entry.find("atom:content", ATOM_NS)
    if content_el is None:
        # Minimal record from Atom-level data only
        title = entry.findtext("atom:title", default=None, namespaces=ATOM_NS)
        return FPDSRecord(piid=piid, description=title)

    # Description: try FPDS-specific field first, then generic
    desc = _text(content_el, "descriptionOfContractRequirement")
    if not desc:
        desc = _text(content_el, "description")
    if not desc:
        title_el = entry.find("atom:title", ATOM_NS)
        if title_el is not None and title_el.text:
            desc = title_el.text.strip()

    # SBIR/STTR research code (Element 10Q)
    research_code = _text(content_el, "research")

    # Vendor information
    vendor_name = _text(content_el, "vendorName")
    vendor_uei = _text(content_el, "UEINumber") or _text(content_el, "entityIdentifier")
    vendor_duns = _text(content_el, "DUNSNumber")
    vendor_cage = _text(content_el, "cageCode")

    # Classification
    psc_code = _text(content_el, "productOrServiceCode")
    naics_code = _text(content_el, "principalNAICSCode")

    # Agency
    agency_name = _text(content_el, "agencyID")
    if not agency_name:
        agency_name = _attr(content_el, "agencyID", "name")
    awarding_office = _text(content_el, "contractingOfficeAgencyID")
    if not awarding_office:
        awarding_office = _attr(content_el, "contractingOfficeAgencyID", "name")

    # Financial
    amount_str = _text(content_el, "obligatedAmount")
    obligated_amount = None
    if amount_str:
        try:
            obligated_amount = float(amount_str)
        except ValueError:
            pass

    # Dates
    signed_date = _text(content_el, "signedDate")
    completion_date = _text(content_el, "ultimateCompletionDate")

    # Solicitation and competition
    solicitation_id = _text(content_el, "solicitationID")
    competition_type = _text(content_el, "extentCompeted")
    if not competition_type:
        competition_type = _attr(content_el, "extentCompeted", "description")

    return FPDSRecord(
        piid=piid,
        description=desc,
        research_code=research_code,
        vendor_name=vendor_name,
        vendor_uei=vendor_uei,
        vendor_duns=vendor_duns,
        vendor_cage=vendor_cage,
        psc_code=psc_code,
        naics_code=naics_code,
        agency_name=agency_name,
        awarding_office=awarding_office,
        obligated_amount=obligated_amount,
        signed_date=signed_date,
        completion_date=completion_date,
        solicitation_id=solicitation_id,
        competition_type=competition_type,
    )


class FPDSAtomClient(BaseAsyncAPIClient):
    """Async client for the FPDS Atom Feed.

    Inherits retry, rate limiting, and typed error translation from
    :class:`BaseAsyncAPIClient`. Uses the body-agnostic
    :meth:`_request_raw` because FPDS responses are Atom XML, not JSON.

    For sync callers (scripts, Dagster ops, notebooks), use
    :class:`sbir_etl.enrichers.sync_wrappers.SyncFPDSAtomClient`
    instead — it wraps this client with :func:`run_sync`.

    Args:
        timeout: HTTP request timeout in seconds.
        rate_limit_per_minute: Requests per minute when no
            ``shared_limiter`` is provided. Defaults to 60 — FPDS
            doesn't publish a rate limit, so we err on the polite side.
        shared_limiter: Optional shared synchronous :class:`RateLimiter`
            for sharing a global rate budget across worker threads
            (see the semantic_scholar client for the same pattern).
            Dispatched via :func:`asyncio.to_thread` so it does not
            block the persistent background event loop.
        http_client: Optional pre-constructed :class:`httpx.AsyncClient`
            (useful for testing).
    """

    api_name = "fpds_atom"

    def __init__(
        self,
        *,
        timeout: int = 30,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        shared_limiter: RateLimiter | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(shared_limiter=shared_limiter)
        self.base_url = FPDS_BASE_URL
        self.rate_limit_per_minute = rate_limit_per_minute
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def _fetch_xml(self, params: dict[str, Any]) -> str | None:
        """Fetch the FPDS Atom XML body for a query.

        Returns ``None`` on transport errors or non-2xx responses, so
        the high-level methods can preserve their legacy "errors as
        ``None``" contract. Callers that need error visibility should
        catch :class:`APIError` from :meth:`_request_raw` directly.
        """
        try:
            response = await self._request_raw(
                "GET", FPDS_ENDPOINT, params=params
            )
        except APIError as e:
            logger.debug("FPDS API error: {}", e)
            return None
        return response.text

    @staticmethod
    def _parse_xml(xml_text: str, context: str) -> ET.Element | None:
        """Parse an XML body, logging and returning ``None`` on parse failure."""
        try:
            return ET.fromstring(xml_text)
        except (ET.ParseError, UnicodeDecodeError) as e:
            logger.debug("FPDS XML parse error for {}: {}", context, e)
            return None

    async def search_by_piid(self, piid: str) -> FPDSRecord | None:
        """Search for a contract by PIID (Procurement Instrument Identifier).

        Queries both ``PIID`` and ``REF_IDV_PIID`` to catch task orders
        under indefinite-delivery contracts.

        Returns:
            Parsed :class:`FPDSRecord` or ``None`` if not found / on error.
        """
        query = f'PIID:"{piid}" OR REF_IDV_PIID:"{piid}"'
        xml_text = await self._fetch_xml({"q": query, "s": 0, "num": 1})
        if xml_text is None:
            return None

        root = self._parse_xml(xml_text, piid)
        if root is None:
            return None

        entry = root.find("atom:entry", ATOM_NS)
        if entry is None:
            return None

        return _parse_entry(entry, piid)

    async def search_by_vendor(
        self,
        name: str | None = None,
        uei: str | None = None,
        limit: int = 10,
    ) -> list[FPDSRecord]:
        """Search for contracts by vendor name or UEI."""
        parts = []
        if uei:
            parts.append(f'VENDOR_UEI_NUMBER:"{uei}"')
        if name:
            parts.append(f'VENDOR_FULL_NAME:"{name}"')
        if not parts:
            return []

        query = " OR ".join(parts)
        xml_text = await self._fetch_xml({"q": query, "s": 0, "num": limit})
        if xml_text is None:
            return []

        root = self._parse_xml(xml_text, "vendor search")
        if root is None:
            return []

        records = []
        for entry in root.findall("atom:entry", ATOM_NS):
            content = entry.find("atom:content", ATOM_NS)
            piid = _text(content, "PIID") if content is not None else None
            piid = piid or "unknown"
            records.append(_parse_entry(entry, piid))

        return records

    async def get_description(self, piid: str) -> str | None:
        """Get just the contract description for a PIID."""
        record = await self.search_by_piid(piid)
        return record.description if record else None

    async def get_research_code(self, piid: str) -> str | None:
        """Get the FPDS SBIR/STTR research code for a PIID.

        Returns codes like ``"SR1"`` (SBIR Phase I), ``"ST2"`` (STTR Phase II),
        or ``None`` if not an SBIR/STTR contract.
        """
        record = await self.search_by_piid(piid)
        return record.research_code if record else None

    async def get_descriptions(self, piids: list[str]) -> dict[str, str]:
        """Batch-fetch descriptions for multiple PIIDs."""
        results: dict[str, str] = {}
        for piid in piids:
            if piid in results:
                continue
            record = await self.search_by_piid(piid)
            if record and record.description:
                desc = record.description
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                results[piid] = desc
        return results

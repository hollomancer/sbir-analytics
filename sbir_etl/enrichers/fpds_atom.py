"""FPDS Atom Feed client for real-time federal procurement data.

The FPDS (Federal Procurement Data System) Atom Feed at
``https://www.fpds.gov/ezsearch/LATEST`` provides public, real-time access
to federal contract records.  Unlike USAspending (which lags weeks/months),
FPDS updates within 3 days of contract action.

Key data available via FPDS Atom:
- Contract descriptions (``descriptionOfContractRequirement``)
- SBIR/STTR research codes (Element 10Q: SR1–SR3, ST1–ST3)
- Vendor information (name, UEI, CAGE, DUNS)
- PSC and NAICS codes
- Contract values and dates
- Competition type and solicitation info

No API key is required — the Atom feed is fully public.

Usage::

    from sbir_etl.enrichers.fpds_atom import FPDSAtomClient

    client = FPDSAtomClient()
    record = client.search_by_piid("FA2541-26-C-B005")
    if record:
        print(record.description)
        print(record.research_code)  # e.g. "SR1" for SBIR Phase I

    descs = client.get_descriptions(["FA2541-26-C-B005", "FA9550-26-C-B001"])
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

FPDS_ATOM_URL = "https://www.fpds.gov/ezsearch/LATEST"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Maximum retries for transient errors (429, 5xx)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


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


class FPDSAtomClient:
    """Client for querying the FPDS Atom Feed.

    Uses synchronous httpx with retry logic and rate limiting.
    Thread-safe when used with a shared :class:`RateLimiter`.

    Args:
        rate_limiter: Optional rate limiter (e.g.
            :class:`sbir_etl.enrichers.rate_limiting.RateLimiter`). If
            ``None``, no rate limiting is applied.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        rate_limiter: Any | None = None,
        timeout: int = 30,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._limiter = rate_limiter
        self._timeout = timeout
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def close(self) -> None:
        """Close the underlying HTTP client (if owned by this instance)."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FPDSAtomClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self) -> None:
        if self._limiter is not None:
            self._limiter.wait_if_needed()

    def _get(self, params: dict[str, Any]) -> httpx.Response | None:
        """Make a GET request with retry logic for transient errors."""
        for attempt in range(MAX_RETRIES):
            self._wait()
            try:
                resp = self._client.get(FPDS_ATOM_URL, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.debug(
                        f"FPDS returned {resp.status_code}, retrying in {wait}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.debug(f"FPDS returned {resp.status_code}")
                    return None
                return resp
            except httpx.HTTPError as e:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                logger.debug(f"FPDS request error: {e}, retrying in {wait}s")
                time.sleep(wait)
        return None

    def _parse_response(self, resp: httpx.Response, piid: str) -> FPDSRecord | None:
        """Parse an FPDS Atom response into a record."""
        try:
            root = ET.fromstring(resp.text)
        except (ET.ParseError, UnicodeDecodeError) as e:
            logger.debug(f"FPDS XML parse error for {piid}: {e}")
            return None

        entry = root.find("atom:entry", ATOM_NS)
        if entry is None:
            return None

        return _parse_entry(entry, piid)

    def search_by_piid(self, piid: str) -> FPDSRecord | None:
        """Search for a contract by PIID (Procurement Instrument Identifier).

        Queries both ``PIID`` and ``REF_IDV_PIID`` to catch task orders
        under indefinite-delivery contracts.

        Returns:
            Parsed :class:`FPDSRecord` or ``None`` if not found.
        """
        query = f'PIID:"{piid}" OR REF_IDV_PIID:"{piid}"'
        resp = self._get({"q": query, "s": 0, "num": 1})
        if resp is None:
            return None
        return self._parse_response(resp, piid)

    def search_by_vendor(
        self, name: str | None = None, uei: str | None = None, limit: int = 10
    ) -> list[FPDSRecord]:
        """Search for contracts by vendor name or UEI.

        Args:
            name: Vendor name to search.
            uei: Unique Entity Identifier.
            limit: Maximum results to return.

        Returns:
            List of :class:`FPDSRecord` objects.
        """
        parts = []
        if uei:
            parts.append(f'VENDOR_UEI_NUMBER:"{uei}"')
        if name:
            parts.append(f'VENDOR_FULL_NAME:"{name}"')
        if not parts:
            return []

        query = " OR ".join(parts)
        resp = self._get({"q": query, "s": 0, "num": limit})
        if resp is None:
            return []

        try:
            root = ET.fromstring(resp.text)
        except (ET.ParseError, UnicodeDecodeError) as e:
            logger.debug(f"FPDS XML parse error for vendor search: {e}")
            return []

        records = []
        for entry in root.findall("atom:entry", ATOM_NS):
            # Extract PIID from entry for the record
            content = entry.find("atom:content", ATOM_NS)
            piid = _text(content, "PIID") if content is not None else None
            piid = piid or "unknown"
            records.append(_parse_entry(entry, piid))

        return records

    def get_description(self, piid: str) -> str | None:
        """Get just the contract description for a PIID.

        Convenience method — delegates to :meth:`search_by_piid`.
        """
        record = self.search_by_piid(piid)
        return record.description if record else None

    def get_research_code(self, piid: str) -> str | None:
        """Get the FPDS SBIR/STTR research code for a PIID.

        Returns codes like ``"SR1"`` (SBIR Phase I), ``"ST2"`` (STTR Phase II),
        or ``None`` if not an SBIR/STTR contract.
        """
        record = self.search_by_piid(piid)
        return record.research_code if record else None

    def get_descriptions(self, piids: list[str]) -> dict[str, str]:
        """Batch-fetch descriptions for multiple PIIDs.

        Args:
            piids: List of contract PIIDs.

        Returns:
            Dict mapping PIID to description text.
        """
        results: dict[str, str] = {}
        for piid in piids:
            if piid in results:
                continue
            record = self.search_by_piid(piid)
            if record and record.description:
                desc = record.description
                if len(desc) > 500:
                    desc = desc[:500] + "..."
                results[piid] = desc
        return results

"""USAspending API client for iterative enrichment.

This module provides an async client for querying the USAspending.gov API v2
to enrich SBIR awards with recipient data, NAICS codes, and transaction information.
Supports rate limiting, retry logic, delta detection, and state management.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from ...config.loader import get_config
from ...exceptions import APIError
from ...models.enrichment import EnrichmentFreshnessRecord
from ..base_client import BaseAsyncAPIClient

# ------------------------------------------------------------------
# Award type code groups — USAspending requires separate requests for
# contracts (procurement) vs. assistance (grants/cooperative agreements).
# ------------------------------------------------------------------
CONTRACT_TYPE_CODES: list[str] = ["A", "B", "C", "D"]
ASSISTANCE_TYPE_CODES: list[str] = ["02", "03", "04", "05"]


def classify_award_id(award_id: str) -> str:
    """Classify an SBIR award/contract identifier as PIID, FAIN, or unknown.

    Uses format heuristics derived from DoD PIIDs and DOE FAINs:
    - DoD PIIDs: 2-letter agency prefix + digits + dash patterns (e.g. FA2541-26-C-B005)
    - DOE/agency FAINs: DE-AR, DE-SC prefixes (grants)
    - Pure numeric: agency internal IDs (e.g. NSF "2516905") — ambiguous

    Args:
        award_id: The contract/award identifier string.

    Returns:
        One of ``"piid"``, ``"fain"``, or ``"unknown"``.
    """
    s = award_id.strip()
    if not s:
        return "unknown"
    if re.match(r"^DE-", s, re.IGNORECASE):
        return "fain"
    if re.match(r"^[A-Z]{2}\d", s):
        return "piid"
    return "unknown"


def build_award_type_groups(
    award_ids: list[str],
) -> list[tuple[list[str], str, list[str]]]:
    """Split award IDs into typed request groups for USAspending queries.

    Contracts (PIIDs) are queried with ``CONTRACT_TYPE_CODES``, financial
    assistance (FAINs) with ``ASSISTANCE_TYPE_CODES``, and unknown IDs are
    tried against both.

    Args:
        award_ids: Raw award/contract identifier strings.

    Returns:
        List of ``(ids, group_name, award_type_codes)`` tuples ready for
        USAspending API calls.
    """
    piids: list[str] = []
    fains: list[str] = []
    unknown: list[str] = []

    seen: set[str] = set()
    for raw in award_ids:
        aid = raw.strip()
        if not aid or aid in seen:
            continue
        seen.add(aid)
        kind = classify_award_id(aid)
        if kind == "piid":
            piids.append(aid)
        elif kind == "fain":
            fains.append(aid)
        else:
            unknown.append(aid)

    groups: list[tuple[list[str], str, list[str]]] = []
    if piids:
        groups.append((piids, "contracts", CONTRACT_TYPE_CODES))
    if fains:
        groups.append((fains, "assistance", ASSISTANCE_TYPE_CODES))
    for uid in unknown:
        groups.append(([uid], "contracts", CONTRACT_TYPE_CODES))
        groups.append(([uid], "assistance", ASSISTANCE_TYPE_CODES))
    return groups



class USAspendingAPIClient(BaseAsyncAPIClient):
    """Async client for USAspending.gov API v2."""

    api_name = "usaspending"

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
        super().__init__()

        if config is None:
            cfg = get_config()
            self.config = cfg.enrichment_refresh.usaspending.model_dump()
            self.api_config = cfg.enrichment.usaspending_api
        else:
            self.config = config
            self.api_config = config.get("usaspending_api", {})

        self.base_url = self.api_config.get("base_url", "https://api.usaspending.gov/api/v2")
        self.timeout = self.config.get("timeout_seconds", 30)
        self.rate_limit_per_minute = self.config.get("rate_limit_per_minute", 120)

        # State file path
        self.state_file = Path(
            self.config.get("state_file", "data/state/enrichment_refresh_state.json")
        )
        from sbir_etl.utils.path_utils import ensure_parent_dir

        ensure_parent_dir(self.state_file)

        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)

        logger.info(
            f"Initialized USAspendingAPIClient: base_url={self.base_url}, "
            f"rate_limit={self.rate_limit_per_minute}/min"
        )

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
        except APIError as e:
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
        except APIError as e:
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
        except APIError as e:
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
        except APIError as e:
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
        except APIError as e:
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
        except APIError as e:
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

        except APIError as e:
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
            from sbir_etl.utils.path_utils import ensure_parent_dir

            ensure_parent_dir(self.state_file)
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save state file {self.state_file}: {e}")

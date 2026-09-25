"""USAspending ``SourceAdapter`` wrapping ``USAspendingAPIClient``.

Epistemic tier: pipelines. Domain lookup order (UEI / DUNS / CAGE / PIID)
stays on the client; this module only exposes the shared lifecycle surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sbir_etl.enrichers.source_adapter import (
    USASPENDING_CITATION,
    QualityResult,
    RawPage,
    SourceProvenance,
)
from sbir_etl.enrichers.usaspending.client import USAspendingAPIClient
from sbir_etl.utils.async_tools import run_sync
from sbir_etl.utils.enrichment.freshness import FreshnessStore


EPISTEMIC_TIER = "pipelines"


class USAspendingSourceAdapter:
    """Award-level USAspending refresh adapter."""

    source_id = "usaspending"

    def __init__(
        self,
        client: USAspendingAPIClient | None = None,
        *,
        freshness: FreshnessStore | None = None,
    ) -> None:
        self._client = client or USAspendingAPIClient()
        self._freshness = freshness

    def fetch_page(self, request: Mapping[str, Any], cursor: str | None) -> RawPage:
        del cursor
        award_id = str(request["award_id"])
        freshness_record = None
        if self._freshness is not None:
            freshness_record = self._freshness.get_record(award_id, self.source_id)
        result = run_sync(
            self._client.enrich_award(
                award_id=award_id,
                uei=_optional_str(request.get("uei")),
                duns=_optional_str(request.get("duns")),
                cage=_optional_str(request.get("cage")),
                piid=_optional_str(request.get("piid")),
                freshness_record=freshness_record,
            )
        )
        return RawPage(payload=result, record_id=award_id)

    def normalize(self, raw: RawPage) -> list[Mapping[str, Any]]:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        return [
            {
                "award_id": raw.record_id,
                "success": bool(payload.get("success")),
                "payload": payload.get("payload"),
                "payload_hash": payload.get("payload_hash"),
                "delta_detected": payload.get("delta_detected", True),
                "metadata": payload.get("metadata") or {},
                "error": payload.get("error"),
            }
        ]

    def validate(self, records: Sequence[Mapping[str, Any]]) -> QualityResult:
        if not records:
            return QualityResult(ok=False, errors=("empty page",))
        first = records[0]
        if first.get("success"):
            return QualityResult(ok=True)
        return QualityResult(ok=False, errors=(str(first.get("error") or "enrichment failed"),))

    def provenance(self, raw: RawPage) -> SourceProvenance:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        return SourceProvenance(
            source_id=self.source_id,
            retrieved_at=datetime.now(UTC),
            content_hash=payload.get("payload_hash") if isinstance(payload, Mapping) else None,
            citation_url=USASPENDING_CITATION,
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

"""NIH RePORTER ``SourceAdapter`` wrapping ``NIHReporterAPIClient``.

Epistemic tier: pipelines. Exact ``project_num`` + FY lookup stays on the
client; this module exposes the shared refresh lifecycle and persists the
project table.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sbir_etl.enrichers.nih_reporter.client import NIH_REPORTER_CITATION, NIHReporterAPIClient
from sbir_etl.enrichers.nih_reporter.keys import NIHWindowKind, parse_refresh_window
from sbir_etl.enrichers.nih_reporter.persist import upsert_nih_reporter_awards
from sbir_etl.enrichers.nih_reporter.schema import NIHReporterRecord
from sbir_etl.enrichers.source_adapter import QualityResult, RawPage, SourceProvenance
from sbir_etl.utils.async_tools import run_sync
from sbir_etl.utils.enrichment.freshness import FreshnessStore


EPISTEMIC_TIER = "pipelines"


class NIHReporterSourceAdapter:
    """Award-level NIH RePORTER refresh adapter."""

    source_id = "nih_reporter"

    def __init__(
        self,
        client: NIHReporterAPIClient | None = None,
        *,
        freshness: FreshnessStore | None = None,
        persist_path: Path | None = None,
    ) -> None:
        self._client = client or NIHReporterAPIClient()
        self._freshness = freshness
        self._persist_path = persist_path

    def fetch_page(self, request: Mapping[str, Any], cursor: str | None) -> RawPage:
        del cursor
        award_id = str(request.get("award_id") or "")
        project_nums = _project_nums(request)
        award_year = _award_year(request)
        if not award_id or not project_nums or award_year is None:
            return RawPage(
                payload={
                    "success": False,
                    "records": [],
                    "payload_hash": None,
                    "delta_detected": True,
                    "metadata": {},
                    "error": "NIH RePORTER request needs award_id, project_num, and award_year",
                },
                record_id=award_id or "unknown",
            )

        records = run_sync(
            self._client.lookup_projects(
                project_nums,
                award_year,
                window=_lookup_window(request.get("window")),
            )
        )
        payload_hash = _payload_hash(self._client, records)
        previous = None
        if self._freshness is not None:
            previous = self._freshness.get_record(award_id, self.source_id)
        previous_hash = previous.payload_hash if previous is not None else None
        delta_detected = previous_hash is None or previous_hash != payload_hash
        if records:
            upsert_nih_reporter_awards(
                records,
                award_id=award_id,
                path=self._persist_path,
            )
        return RawPage(
            payload={
                "success": True,
                "records": [record.to_mapping() for record in records],
                "payload_hash": payload_hash,
                "delta_detected": delta_detected,
                "metadata": {
                    "match_count": len(records),
                    "appl_ids": [record.appl_id for record in records],
                    "award_year": award_year,
                },
                "error": None,
            },
            record_id=award_id,
        )

    def normalize(self, raw: RawPage) -> list[Mapping[str, Any]]:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        return [
            {
                "award_id": raw.record_id,
                "success": bool(payload.get("success")),
                "payload": payload.get("records") or [],
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
            citation_url=NIH_REPORTER_CITATION,
        )


def _project_nums(request: Mapping[str, Any]) -> list[str]:
    raw = request.get("project_nums")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = [str(item).strip() for item in raw if str(item).strip()]
        if values:
            return values
    single = request.get("project_num") or request.get("core_project_num")
    if single is None:
        return []
    text = str(single).strip()
    return [text] if text else []


def _award_year(request: Mapping[str, Any]) -> int | None:
    raw = request.get("award_year")
    if raw is None or raw == "":
        return None
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return None
    if 1900 <= year <= 2100:
        return year
    return None


def _lookup_window(window: Any) -> str | None:
    """Pass date windows through; fy windows are already applied to award_year."""

    if window is None:
        return None
    parsed = parse_refresh_window(str(window) if not isinstance(window, str) else window)
    if parsed.kind is NIHWindowKind.PROJECT_START_DATE:
        return f"{parsed.from_date}:{parsed.to_date}"
    return None


def _payload_hash(client: NIHReporterAPIClient, records: Sequence[NIHReporterRecord]) -> str:
    page_hashes = tuple(sorted({record.payload_hash for record in records if record.payload_hash}))
    if len(page_hashes) == 1:
        return page_hashes[0]
    if page_hashes:
        return client.compute_payload_hash({"pages": list(page_hashes)})
    body = {
        "appl_ids": [record.appl_id for record in records],
        "records": [
            {key: value for key, value in record.to_mapping().items() if key != "last_refreshed_at"}
            for record in records
        ],
    }
    return client.compute_payload_hash(body)

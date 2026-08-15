"""Shared source-adapter lifecycle for iterative enrichment refresh.

Epistemic tier: pipelines. Transport stays on ``BaseAsyncAPIClient``; domain
semantics (NIH activity codes, UCC sessions, screening, M&A scoring) stay in
per-source adapters. This module owns fetch → normalize → validate plus
freshness and checkpoint bookkeeping.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sbir_etl.utils.enrichment.checkpoints import CheckpointStore, EnrichmentCheckpoint
from sbir_etl.utils.enrichment.freshness import FreshnessStore, update_freshness_ledger
from sbir_etl.utils.enrichment.metrics import EnrichmentMetricsCollector


EPISTEMIC_TIER = "pipelines"

USASPENDING_CITATION = "https://api.usaspending.gov/"


@dataclass(frozen=True)
class RawPage:
    """One opaque fetch result plus an optional pagination cursor."""

    payload: Any
    record_id: str
    cursor: str | None = None


@dataclass(frozen=True)
class QualityResult:
    """Validation outcome for a normalized page."""

    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceProvenance:
    """Retrieval stamp shared by every adapter."""

    source_id: str
    retrieved_at: datetime
    content_hash: str | None
    citation_url: str


class SourceAdapter(Protocol):
    """Lifecycle surface a new enrichment source must implement."""

    source_id: str

    def fetch_page(self, request: Mapping[str, Any], cursor: str | None) -> RawPage:
        """Fetch one raw page for ``request``. Cursor is source-defined."""

    def normalize(self, raw: RawPage) -> list[Mapping[str, Any]]:
        """Turn a raw page into typed-ish records (mappings)."""

    def validate(self, records: Sequence[Mapping[str, Any]]) -> QualityResult:
        """Return a quality result; do not raise for expected empty pages."""

    def provenance(self, raw: RawPage) -> SourceProvenance:
        """Return source id, retrieval time, content hash, and citation URL."""


@dataclass
class RefreshStats:
    """Aggregate outcome of one runner pass."""

    total: int = 0
    success: int = 0
    failed: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


class SourceRefreshRunner:
    """One request loop over freshness, checkpoints, and metrics."""

    def __init__(
        self,
        *,
        freshness: FreshnessStore,
        checkpoints: CheckpointStore,
        metrics: EnrichmentMetricsCollector | None = None,
        partition_id: str = "default",
    ) -> None:
        self.freshness = freshness
        self.checkpoints = checkpoints
        self.metrics = metrics or EnrichmentMetricsCollector()
        self.partition_id = partition_id

    def refresh_records(
        self,
        adapter: SourceAdapter,
        records: Sequence[Mapping[str, Any]],
    ) -> RefreshStats:
        """Refresh each record through the adapter. Resume from checkpoint."""

        stats = RefreshStats(total=len(records))
        existing = self.checkpoints.load_checkpoint(self.partition_id, adapter.source_id)
        processed_ids = set()
        if existing and isinstance(existing.metadata, dict):
            raw_ids = existing.metadata.get("processed_ids") or []
            processed_ids = {str(item) for item in raw_ids}

        for request in records:
            award_id = str(request.get("award_id") or "")
            if not award_id:
                stats.failed += 1
                stats.errors.append("missing award_id")
                continue
            if award_id in processed_ids:
                stats.skipped += 1
                continue

            try:
                raw = adapter.fetch_page(request, cursor=None)
                normalized = adapter.normalize(raw)
                quality = adapter.validate(normalized)
                proven = adapter.provenance(raw)
                first = normalized[0] if normalized else {}
                success = bool(quality.ok and first.get("success", quality.ok))
                unchanged = bool(first.get("delta_detected") is False)
                if success:
                    error = None
                elif first.get("error"):
                    error = first.get("error")
                elif quality.errors:
                    error = quality.errors[0]
                else:
                    error = "validation failed"
                self.metrics.record_api_call(adapter.source_id, error=not success)
                update_freshness_ledger(
                    store=self.freshness,
                    award_id=award_id,
                    source=adapter.source_id,
                    success=success,
                    payload_hash=proven.content_hash,
                    metadata=dict(first.get("metadata") or {}),
                    error_message=None if success else str(error),
                )
                if success and unchanged:
                    stats.unchanged += 1
                elif success:
                    stats.success += 1
                else:
                    stats.failed += 1
                    stats.errors.append(f"{award_id}: {error}")
            except Exception as exc:
                stats.failed += 1
                stats.errors.append(f"{award_id}: {exc}")
                self.metrics.record_api_call(adapter.source_id, error=True)
                update_freshness_ledger(
                    store=self.freshness,
                    award_id=award_id,
                    source=adapter.source_id,
                    success=False,
                    error_message=str(exc),
                )

            processed_ids.add(award_id)
            self.checkpoints.save_checkpoint(
                EnrichmentCheckpoint(
                    partition_id=self.partition_id,
                    source=adapter.source_id,
                    last_processed_award_id=award_id,
                    last_success_timestamp=datetime.now(UTC),
                    records_processed=stats.success + stats.unchanged,
                    records_failed=stats.failed,
                    records_total=stats.total,
                    checkpoint_timestamp=datetime.now(UTC),
                    metadata={"processed_ids": sorted(processed_ids)},
                )
            )

        return stats

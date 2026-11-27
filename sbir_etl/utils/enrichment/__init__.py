"""Consolidated enrichment utilities.

This module provides a unified interface to enrichment-related utilities:
- Checkpoints: Resume functionality for interrupted enrichment runs
- Freshness: Staleness tracking and refresh scheduling
- Metrics: Enrichment performance and coverage reporting

Usage:
    from sbir_etl.utils.enrichment import CheckpointStore, FreshnessStore, EnrichmentFreshnessMetrics

Epistemic tier: pipelines. This is the package default that ``sbir_etl.utils`` states
for deterministic shared helpers.
"""

from .checkpoints import CheckpointStore, EnrichmentCheckpoint
from .freshness import FreshnessStore
from .metrics import EnrichmentFreshnessMetrics

EPISTEMIC_TIER = "pipelines"

__all__ = [
    "CheckpointStore",
    "EnrichmentCheckpoint",
    "FreshnessStore",
    "EnrichmentFreshnessMetrics",
]

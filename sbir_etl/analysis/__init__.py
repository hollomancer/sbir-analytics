"""Pipelines-tier analysis contracts, registry, runner, and snapshots.

Epistemic tier: pipelines. Exploratory census and cohort engines are injected
at the CLI / Dagster composition boundary; this package must not import them.
"""

from sbir_etl.analysis.contracts import (
    AnalysisKind,
    AnalysisRun,
    AnalysisSpec,
    AwardCorpus,
    EvidenceChannelStage,
    ProfileEntry,
    ReportingWindow,
    SourceManifest,
    unavailable_channel_label,
)
from sbir_etl.analysis.registry import load_registry
from sbir_etl.analysis.runner import materialize_analysis
from sbir_etl.analysis.snapshots import compare_snapshots, write_snapshot


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "AnalysisKind",
    "AnalysisRun",
    "AnalysisSpec",
    "AwardCorpus",
    "EvidenceChannelStage",
    "ProfileEntry",
    "ReportingWindow",
    "SourceManifest",
    "compare_snapshots",
    "load_registry",
    "materialize_analysis",
    "unavailable_channel_label",
    "write_snapshot",
]

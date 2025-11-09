"""Transition Detection assets package.

This package contains modularized Dagster assets for the Transition Detection MVP,
which identifies SBIR award recipients who transition to federal contracts.

Module Structure:
- utils: Shared utilities, Dagster shims, and helper functions
- contracts: Federal contracts loading and sampling
- vendor_resolution: Vendor→SBIR recipient resolution via UEI/DUNS/fuzzy matching
- scoring: Transition candidate scoring
- evidence: Structured evidence extraction for transitions
- detections: High-confidence transition flagging
- analytics: Transition analytics and insights
- checks: Quality checks for all transition assets
- loading: Neo4j graph database loading

Pipeline Stages:
1. Contracts: Load and sample federal contracts
2. Vendor Resolution: Resolve vendors to SBIR recipients
3. Scoring: Score transition candidates
4. Evidence: Extract structured evidence
5. Detections: Flag high-confidence transitions
6. Analytics: Compute insights and metrics
7. Loading: Load into Neo4j graph database

Exported Assets:
- raw_contracts, validated_contracts_sample
- enriched_vendor_resolution
- transformed_transition_scores
- transformed_transition_evidence
- transformed_transition_detections
- transformed_transition_analytics
- loaded_transitions, loaded_transition_relationships, loaded_transition_profiles
"""

from __future__ import annotations

# Analytics module
from .analytics import transformed_transition_analytics

# Checks module
from .checks import (
    contracts_sample_quality_check,
    transition_analytics_quality_check,
    transition_detections_quality_check,
    transition_evidence_quality_check,
    transition_scores_quality_check,
    vendor_resolution_quality_check,
)

# Contracts module
from .contracts import raw_contracts, validated_contracts_sample

# Detections module
from .detections import transformed_transition_detections

# Evidence module
from .evidence import transformed_transition_evidence

# Loading module
from .loading import (
    loaded_transition_profiles,
    loaded_transition_relationships,
    loaded_transitions,
    transition_node_count_check,
    transition_relationships_check,
)

# Scoring module
from .scoring import transformed_transition_scores

# Utility functions
from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)

# Vendor resolution module
from .vendor_resolution import enriched_vendor_resolution


__all__ = [
    # Contracts
    "raw_contracts",
    "validated_contracts_sample",
    # Vendor resolution
    "enriched_vendor_resolution",
    # Scoring
    "transformed_transition_scores",
    # Evidence
    "transformed_transition_evidence",
    # Detections
    "transformed_transition_detections",
    # Analytics
    "transformed_transition_analytics",
    # Checks
    "contracts_sample_quality_check",
    "vendor_resolution_quality_check",
    "transition_scores_quality_check",
    "transition_evidence_quality_check",
    "transition_detections_quality_check",
    "transition_analytics_quality_check",
    # Loading
    "loaded_transitions",
    "loaded_transition_relationships",
    "loaded_transition_profiles",
    "transition_node_count_check",
    "transition_relationships_check",
    # Utility functions
    "asset",
    "asset_check",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "AssetExecutionContext",
    "MetadataValue",
    "Output",
]

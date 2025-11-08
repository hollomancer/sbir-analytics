"""
Dagster assets for Transition Detection MVP.

This module re-exports all Transition assets from the modularized src.assets.transition package.
For implementation details, see the individual modules in src/assets/transition/:
- contracts.py: Federal contracts loading and sampling
- vendor_resolution.py: Vendor→SBIR recipient resolution
- scoring.py: Transition candidate scoring
- evidence.py: Structured evidence extraction
- detections.py: High-confidence transition flagging
- analytics.py: Transition analytics and insights
- checks.py: Quality checks for all assets
- loading.py: Neo4j graph database loading
- utils.py: Shared utilities and helpers

Pipeline Stages:
1. Contracts: Load and sample federal contracts
2. Vendor Resolution: Resolve vendors to SBIR recipients
3. Scoring: Score transition candidates
4. Evidence: Extract structured evidence
5. Detections: Flag high-confidence transitions
6. Analytics: Compute insights and metrics
7. Loading: Load into Neo4j graph database

Design Goals:
- Import-safe: gracefully operates when Dagster is not available
- File outputs: parquet artifacts under data/processed/
- Config via env vars: thresholds, caps, and paths

For backward compatibility, all assets are re-exported at the top level.
"""

from __future__ import annotations

# Import all assets from the modularized transition package
from .transition import (
    # Contracts
    raw_contracts,
    validated_contracts_sample,
    # Vendor resolution
    enriched_vendor_resolution,
    # Scoring
    transformed_transition_scores,
    # Evidence
    transformed_transition_evidence,
    # Detections
    transformed_transition_detections,
    # Analytics
    transformed_transition_analytics,
    # Checks
    contracts_sample_quality_check,
    transition_analytics_quality_check,
    transition_detections_quality_check,
    transition_evidence_quality_check,
    transition_scores_quality_check,
    vendor_resolution_quality_check,
    # Loading
    loaded_transition_profiles,
    loaded_transition_relationships,
    loaded_transitions,
    transition_node_count_check,
    transition_relationships_check,
)


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
]

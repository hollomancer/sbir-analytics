"""Smoke tests for transition Dagster asset definitions."""

from __future__ import annotations

import pytest

import src.assets.transition as transition_assets


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_transition_assets_registered():
    """Ensure core transition Dagster assets resolve and are importable."""
    asset_functions = [
        transition_assets.raw_contracts,
        transition_assets.validated_contracts_sample,
        transition_assets.enriched_vendor_resolution,
        transition_assets.transformed_transition_scores,
        transition_assets.transformed_transition_evidence,
        transition_assets.transformed_transition_detections,
        transition_assets.transformed_transition_analytics,
    ]

    for asset in asset_functions:
        assert callable(asset)


def test_transition_asset_checks_registered():
    """Ensure supporting asset checks exist for transition pipeline."""
    checks = [
        transition_assets.contracts_sample_quality_check,
        transition_assets.vendor_resolution_quality_check,
        transition_assets.transition_scores_quality_check,
        transition_assets.transition_evidence_quality_check,
        transition_assets.transition_detections_quality_check,
        transition_assets.transition_analytics_quality_check,
    ]

    for check in checks:
        assert callable(check)


def test_transition_neo4j_assets_registered():
    """Ensure Neo4j loader assets are registered."""
    neo4j_assets = [
        transition_assets.loaded_transitions,
        transition_assets.transition_node_count_check,
        transition_assets.loaded_transition_relationships,
        transition_assets.transition_relationships_check,
        transition_assets.loaded_transition_profiles,
    ]

    for asset in neo4j_assets:
        assert callable(asset)


def test_asset_import_dependencies_ordered():
    """Minimal dependency smoke test to catch refactoring regressions."""
    assert transition_assets.raw_contracts is not None
    assert transition_assets.enriched_vendor_resolution is not None
    assert transition_assets.transformed_transition_scores is not None
    assert transition_assets.transformed_transition_detections is not None


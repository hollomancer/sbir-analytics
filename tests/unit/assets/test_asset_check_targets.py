"""Every asset check in the code location must target an asset that can be materialized.

A check whose ``asset=`` names a key that no ``@asset`` or ``@multi_asset`` produces
makes Dagster create a placeholder asset. The check attaches to that placeholder and
never runs with the job that materializes the real asset (issue #872).
"""

import pytest
from dagster import Definitions

import sbir_analytics.definitions as definitions
from sbir_analytics.definitions_factory import build_definitions


pytestmark = pytest.mark.fast


def _placeholder_check_targets(defs: Definitions) -> list[str]:
    graph = defs.resolve_asset_graph()
    return sorted(
        f"{check_key.asset_key.to_user_string()}:{check_key.name}"
        for check_key in graph.asset_check_keys
        if not graph.get(check_key.asset_key).is_materializable
    )


def test_primary_definitions_checks_target_materializable_assets():
    assert _placeholder_check_targets(definitions.defs) == []


def test_heavy_definitions_checks_target_materializable_assets():
    """The heavy profile always loads the CET family, whatever the environment says."""
    defs = build_definitions("heavy").defs
    check_keys = defs.resolve_asset_graph().asset_check_keys
    assert any(key.name == "cet_taxonomy_completeness_check" for key in check_keys)
    assert _placeholder_check_targets(defs) == []

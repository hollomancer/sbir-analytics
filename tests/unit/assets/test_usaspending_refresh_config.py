"""Unit tests for the USAspending iterative refresh assets (issue #875)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from dagster import build_asset_context

from sbir_analytics.assets import usaspending_iterative_enrichment as usa_iterative
from sbir_etl.config.loader import get_config


pytestmark = pytest.mark.fast


def _md(output: Any, key: str) -> Any:
    value = output.metadata[key]
    return getattr(value, "value", value)


class _RunnerMustNotRun:
    def __init__(self, **_kwargs: Any) -> None:
        raise AssertionError("SourceRefreshRunner must not be built when the source is disabled")


@pytest.fixture
def config(monkeypatch):
    """Return a private copy of the repository config that the assets will read."""
    cfg = get_config().model_copy(deep=True)
    monkeypatch.setattr(usa_iterative, "get_config", lambda: cfg)
    return cfg


def test_refresh_skips_when_usaspending_disabled(config, monkeypatch) -> None:
    monkeypatch.setattr(config.enrichment_refresh.usaspending, "enabled", False)
    monkeypatch.setattr(usa_iterative, "FreshnessStore", lambda: object())
    monkeypatch.setattr(usa_iterative, "SourceRefreshRunner", _RunnerMustNotRun)
    monkeypatch.setattr(
        usa_iterative,
        "build_usaspending_adapter",
        lambda **_kw: pytest.fail("adapter must not be built when the source is disabled"),
    )
    monkeypatch.setattr(usa_iterative, "stale_awards_to_requests", lambda _df: [{"award_id": "A1"}])
    monkeypatch.setattr(usa_iterative, "has_identifier", lambda _request: True)

    output = usa_iterative.usaspending_refresh_batch(
        build_asset_context(),
        pd.DataFrame({"award_id": ["A1"]}),
        config=usa_iterative.EnrichmentRefreshConfig(),
    )

    assert output.value["total"] == 0
    assert output.value["success"] == 0
    assert _md(output, "reason") == "disabled"


def test_refresh_config_has_no_force_field() -> None:
    assert "force" not in usa_iterative.EnrichmentRefreshConfig.model_fields


def test_threshold_default_is_1000() -> None:
    assert get_config().enrichment_refresh.usaspending.stale_awards_threshold == 1000


def test_threshold_check_reads_threshold_from_config(config, monkeypatch) -> None:
    monkeypatch.setattr(config.enrichment_refresh.usaspending, "stale_awards_threshold", 2)

    at_limit = usa_iterative.stale_awards_threshold_check(pd.DataFrame({"award_id": ["A", "B"]}))
    over_limit = usa_iterative.stale_awards_threshold_check(
        pd.DataFrame({"award_id": ["A", "B", "C"]})
    )

    assert at_limit.passed
    assert not over_limit.passed
    assert over_limit.metadata["threshold"].value == 2
    assert over_limit.metadata["stale_count"].value == 3


def test_threshold_check_passes_below_default(config) -> None:
    result = usa_iterative.stale_awards_threshold_check(pd.DataFrame({"award_id": ["A"] * 1000}))

    assert result.passed
    assert result.metadata["threshold"].value == 1000

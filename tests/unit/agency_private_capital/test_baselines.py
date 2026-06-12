"""Unit tests for the published-baseline registry loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from sbir_analytics.assets.agency_private_capital.baselines import (
    BaselineKind,
    PublishedBaseline,
    PublishedBaselineRegistry,
)


pytestmark = pytest.mark.fast


REPO_REGISTRY = Path("config/agency_private_capital/published_baselines.yaml")


def test_default_registry_loads_and_contains_required_baselines() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    ids = {b.id for b in reg}
    required = {
        "nvca_seed_to_series_a",
        "bls_bed_5yr_survival",
        "lerner_growth_effect",
        "howell_followon_vc",
        "itif_seed_fund_framing",
    }
    assert required.issubset(ids)


def test_baseline_records_are_typed() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    for b in reg:
        assert isinstance(b, PublishedBaseline)
        assert isinstance(b.kind, BaselineKind)
        assert b.id and b.label and b.citation
        assert b.as_of
        if b.kind is BaselineKind.RATE:
            assert b.point_estimate is not None
            assert 0.0 <= b.point_estimate <= 1.0


def test_for_metric_filters() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    matches = reg.for_metric("phase_i_to_ii_graduation")
    ids = {b.id for b in matches}
    assert "nvca_seed_to_series_a" in ids
    assert "itif_seed_fund_framing" in ids


def test_load_rejects_entry_missing_required_keys(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """baselines:
  - id: orphan
    cohort_metric: foo
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        PublishedBaselineRegistry.load(bad)


def test_load_handles_empty_baselines_block(tmp_path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("baselines: []\n", encoding="utf-8")
    reg = PublishedBaselineRegistry.load(empty)
    assert len(reg) == 0

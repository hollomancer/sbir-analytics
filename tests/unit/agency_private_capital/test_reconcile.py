"""Unit tests for the reconciliation narrative writer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.baselines import PublishedBaselineRegistry
from sbir_analytics.assets.agency_private_capital.reconcile import (
    ReconciliationNarrative,
    ReconciliationRecord,
)


pytestmark = pytest.mark.fast


REPO_REGISTRY = Path("config/agency_private_capital/published_baselines.yaml")


def _outcomes_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "vintage_bucket": "2015-2019",
                "phase_label": "I",
                "metric": "phase_i_to_ii_graduation",
                "numerator": 25,
                "denominator": 100,
                "rate": 0.25,
                "ci_low": 0.176,
                "ci_high": 0.343,
                "available": True,
            },
            {
                "vintage_bucket": "2015-2019",
                "phase_label": "II",
                "metric": "phase_ii_to_federal_contract_transition",
                "numerator": 10,
                "denominator": 50,
                "rate": 0.20,
                "ci_low": 0.114,
                "ci_high": 0.331,
                "available": True,
            },
            {
                "vintage_bucket": "2015-2019",
                "phase_label": "II",
                "metric": "five_year_survival_proxy",
                "numerator": 30,
                "denominator": 50,
                "rate": 0.60,
                "ci_low": 0.46,
                "ci_high": 0.72,
                "available": True,
            },
        ]
    )


def test_record_shape_for_rate_baseline() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    records = ReconciliationNarrative(reg).reconcile(_outcomes_fixture())
    by_id = {r.baseline_id: r for r in records}
    nvca = by_id["nvca_seed_to_series_a"]
    assert isinstance(nvca, ReconciliationRecord)
    assert nvca.cohort_metric == "phase_i_to_ii_graduation"
    assert nvca.baseline_kind == "rate"
    assert nvca.baseline_point_estimate == pytest.approx(0.33)
    assert nvca.cohort_rate == pytest.approx(0.25)
    assert nvca.delta == pytest.approx(0.25 - 0.33)
    assert nvca.attribution
    assert nvca.caveat
    assert nvca.cohort_available is True


def test_record_shape_for_effect_size_baseline() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    records = ReconciliationNarrative(reg).reconcile(_outcomes_fixture())
    by_id = {r.baseline_id: r for r in records}
    lerner = by_id["lerner_growth_effect"]
    assert lerner.baseline_kind == "effect_size"
    assert lerner.baseline_point_estimate is None
    assert lerner.delta is None
    assert lerner.baseline_effect_description


def test_record_shape_when_metric_missing_from_outcomes() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    sparse = _outcomes_fixture().head(1)  # only graduation metric present
    records = ReconciliationNarrative(reg).reconcile(sparse)
    by_id = {r.baseline_id: r for r in records}
    bls = by_id["bls_bed_5yr_survival"]
    assert bls.cohort_available is False
    assert bls.cohort_rate is None
    assert bls.cohort_denominator is None


def test_to_json_replaces_nan_with_none() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    rec = ReconciliationNarrative(reg).reconcile(_outcomes_fixture())[0]
    payload = rec.to_json()
    for key in (
        "cohort_rate",
        "cohort_ci_low",
        "cohort_ci_high",
        "delta",
        "baseline_point_estimate",
    ):
        assert key in payload


def test_markdown_agency_code_parameterizes_header_and_rows() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    narrative = ReconciliationNarrative(reg)
    records = narrative.reconcile(_outcomes_fixture(), headline_vintage="2015-2019")
    md = narrative.to_markdown(records, headline_vintage="2015-2019", agency_code="NIH")
    assert "# NIH SBIR vs. Published Private-Capital" in md
    assert "NIH is 25.0% on vintage 2015-2019 Phase I" in md
    assert "NSF" not in md  # nothing hardcoded leaks through


def test_markdown_contains_gate_statement_pattern() -> None:
    reg = PublishedBaselineRegistry.load(REPO_REGISTRY)
    narrative = ReconciliationNarrative(reg)
    records = narrative.reconcile(_outcomes_fixture(), headline_vintage="2015-2019")
    md = narrative.to_markdown(records, headline_vintage="2015-2019")
    assert "# NSF SBIR vs. Published Private-Capital" in md
    assert "Gate statements" in md
    # Required gate-statement template per spec: NVCA reports X%, NSF is Y%.
    assert "NVCA seed -> Series A graduation rate reports 33%" in md
    assert "NSF is 25.0% on vintage 2015-2019 Phase I" in md
    assert "Difference is attributable to" in md
    assert "Caveat:" in md

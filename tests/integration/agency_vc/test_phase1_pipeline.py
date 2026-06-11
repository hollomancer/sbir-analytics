"""Integration test: Phase 1 SBIR vs published-baseline pipeline (agency-parameterized).

Builds a small NSF Phase II fixture (vintage 2015, n~=100), runs the
cohort -> outcomes -> reconciliation pipeline end-to-end, and verifies
that the three artifacts (parquet, markdown, JSON) are produced and
contain the gate-statement template required by Phase 1 Requirement 4.

NSF is used as the initial implementation target; the test also verifies
that the agency_code parameter routes correctly so future agencies can
reuse the same pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.agency_vc.baselines import PublishedBaselineRegistry
from sbir_analytics.assets.agency_vc.cohort import AgencyCohortBuilder
from sbir_analytics.assets.agency_vc.outcomes import OutcomeMetricsCalculator
from sbir_analytics.assets.agency_vc.reconcile import ReconciliationNarrative


pytestmark = pytest.mark.integration


REPO_REGISTRY = Path("config/agency_vc/published_baselines.yaml")


def _make_nsf_fixture(n_phase_i: int = 200, graduation_rate: float = 0.30) -> pd.DataFrame:
    """Vintage-2015 NSF cohort with controlled graduation behaviour."""

    rows: list[dict] = []
    n_phase_ii = int(n_phase_i * graduation_rate)
    # Phase I awardees
    for i in range(n_phase_i):
        rows.append(
            {
                "award_id": f"NSF-I-{i:04d}",
                "agency": "National Science Foundation",
                "phase": "Phase I",
                "award_year": 2015,
                "uei": f"COMPANY{i:05d}",
                "company_name": f"Firm {i}",
            }
        )
    # First N graduate to Phase II in 2017
    for i in range(n_phase_ii):
        rows.append(
            {
                "award_id": f"NSF-II-{i:04d}",
                "agency": "National Science Foundation",
                "phase": "Phase II",
                "award_year": 2017,
                "uei": f"COMPANY{i:05d}",
                "company_name": f"Firm {i}",
            }
        )
    # A few non-NSF rows to confirm filtering
    for j in range(5):
        rows.append(
            {
                "award_id": f"DOD-I-{j:04d}",
                "agency": "Department of Defense",
                "phase": "Phase I",
                "award_year": 2015,
                "uei": f"DODFIRM{j:05d}",
                "company_name": f"Defense Firm {j}",
            }
        )
    return pd.DataFrame(rows)


def test_phase1_pipeline_produces_three_artifacts(tmp_path) -> None:
    awards = _make_nsf_fixture(n_phase_i=200, graduation_rate=0.30)

    cohort = AgencyCohortBuilder(agency_code="NSF").build(awards)
    # Filter discarded the 5 DOD rows
    assert (cohort["agency"].str.lower() != "department of defense").all()
    assert len(cohort) == 200 + 60

    outcomes = OutcomeMetricsCalculator().compute(cohort)
    parquet_path = tmp_path / "agency_cohort_outcomes.parquet"
    outcomes.to_parquet(parquet_path, index=False)
    assert parquet_path.exists()

    registry = PublishedBaselineRegistry.load(REPO_REGISTRY)
    narrative = ReconciliationNarrative(registry=registry)
    records = narrative.reconcile(outcomes, headline_vintage="2015-2019")
    md_text = narrative.to_markdown(records, headline_vintage="2015-2019")
    md_path = tmp_path / "agency_vs_published_baselines.md"
    md_path.write_text(md_text, encoding="utf-8")

    json_path = tmp_path / "agency_baseline_comparison.json"
    json_path.write_text(json.dumps([r.to_json() for r in records], indent=2))

    # Verify graduation rate matches the seeded ratio
    grad = outcomes[outcomes["metric"] == "phase_i_to_ii_graduation"].iloc[0]
    assert grad["numerator"] == 60
    assert grad["denominator"] == 200
    assert grad["rate"] == pytest.approx(0.30, abs=1e-6)
    assert grad["ci_low"] < 0.30 < grad["ci_high"]

    # Verify gate-statement language for the NVCA pair
    md_loaded = md_path.read_text(encoding="utf-8")
    assert "NVCA seed -> Series A graduation rate reports 33%" in md_loaded
    assert "NSF is 30.0% on vintage 2015-2019 Phase I" in md_loaded
    assert "n=200" in md_loaded
    assert "Difference is attributable to" in md_loaded

    # JSON record shape spot-check
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    by_id = {r["baseline_id"]: r for r in payload}
    nvca = by_id["nvca_seed_to_series_a"]
    assert nvca["nsf_rate"] == pytest.approx(0.30, abs=1e-6)
    assert nvca["baseline_point_estimate"] == pytest.approx(0.33)
    assert nvca["delta"] == pytest.approx(0.30 - 0.33, abs=1e-6)
    assert nvca["nsf_available"] is True


def test_phase1_pipeline_reproducible(tmp_path) -> None:
    awards = _make_nsf_fixture(n_phase_i=120, graduation_rate=0.25)
    cohort = AgencyCohortBuilder(agency_code="NSF").build(awards)
    o1 = OutcomeMetricsCalculator().compute(cohort)
    o2 = OutcomeMetricsCalculator().compute(cohort)
    pd.testing.assert_frame_equal(
        o1.sort_values(list(o1.columns)).reset_index(drop=True),
        o2.sort_values(list(o2.columns)).reset_index(drop=True),
    )

    registry = PublishedBaselineRegistry.load(REPO_REGISTRY)
    n1 = ReconciliationNarrative(registry).reconcile(o1, headline_vintage="2015-2019")
    n2 = ReconciliationNarrative(registry).reconcile(o2, headline_vintage="2015-2019")
    assert [r.to_json() for r in n1] == [r.to_json() for r in n2]

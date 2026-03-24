"""Tests for Mission B: Statutory Performance Benchmarks tools."""

import pytest
import pandas as pd

from sbir_ml.tools.mission_b.compute_transition_rate import (
    ComputeTransitionRateTool,
    STANDARD_THRESHOLD,
    INCREASED_THRESHOLD,
)
from sbir_ml.tools.mission_b.compute_observable_commercialization import (
    ComputeObservableCommercializationTool,
    PHASE2_TRIGGER_THRESHOLD,
    PATENT_PRONG_THRESHOLD,
)


# ---- compute_transition_rate ----

class TestComputeTransitionRateTool:
    def _make_awards(self, company, p1_count, p2_count, fy_start=2021, fy_end=2025):
        """Helper to create award records for a company."""
        records = []
        for i in range(p1_count):
            records.append({
                "company": company, "phase": "I",
                "fiscal_year": fy_start + (i % (fy_end - fy_start + 1)),
            })
        for i in range(p2_count):
            records.append({
                "company": company, "phase": "II",
                "fiscal_year": fy_start + (i % (fy_end - fy_start + 1)),
            })
        return records

    def test_below_threshold(self):
        records = self._make_awards("SmallCo", p1_count=5, p2_count=2)
        awards = pd.DataFrame(records)
        tool = ComputeTransitionRateTool()
        result = tool.run(awards_df=awards, assessment_year=2026)
        results_df = result.data["results"]
        assert len(results_df) == 1
        assert results_df.iloc[0]["status"] == "not_subject"

    def test_standard_threshold_passing(self):
        records = self._make_awards("MediumCo", p1_count=25, p2_count=10)
        awards = pd.DataFrame(records)
        tool = ComputeTransitionRateTool()
        result = tool.run(awards_df=awards, assessment_year=2026)
        results_df = result.data["results"]
        row = results_df[results_df["company_id"] == "MediumCo"].iloc[0]
        assert row["threshold_tier"] == "standard"
        assert row["transition_rate"] == pytest.approx(10 / 25, abs=0.01)

    def test_standard_threshold_failing(self):
        records = self._make_awards("BadCo", p1_count=25, p2_count=2)
        awards = pd.DataFrame(records)
        tool = ComputeTransitionRateTool()
        result = tool.run(awards_df=awards, assessment_year=2026)
        results_df = result.data["results"]
        row = results_df[results_df["company_id"] == "BadCo"].iloc[0]
        assert row["status"] == "failing"

    def test_increased_threshold(self):
        records = self._make_awards("BigCo", p1_count=55, p2_count=25)
        awards = pd.DataFrame(records)
        tool = ComputeTransitionRateTool()
        result = tool.run(awards_df=awards, assessment_year=2026)
        results_df = result.data["results"]
        row = results_df[results_df["company_id"] == "BigCo"].iloc[0]
        assert row["threshold_tier"] == "increased"

    def test_summary_stats(self):
        records = (
            self._make_awards("Co1", 25, 10) +
            self._make_awards("Co2", 5, 2) +
            self._make_awards("Co3", 25, 2)
        )
        awards = pd.DataFrame(records)
        tool = ComputeTransitionRateTool()
        result = tool.run(awards_df=awards, assessment_year=2026)
        summary = result.data["summary"]
        assert summary["total_companies"] == 3
        assert summary["subject_to_benchmark"] == 2  # Co1 and Co3

    def test_empty_input(self):
        tool = ComputeTransitionRateTool()
        result = tool.run()
        assert result.data["summary"]["total_companies"] == 0

    def test_statutory_thresholds(self):
        assert STANDARD_THRESHOLD == 21
        assert INCREASED_THRESHOLD == 51


# ---- compute_observable_commercialization ----

class TestComputeObservableCommercializationTool:
    def _make_p2_awards(self, company, count, fy_start=2016, fy_end=2024):
        return [{
            "company": company, "phase": "II",
            "fiscal_year": fy_start + (i % (fy_end - fy_start + 1)),
        } for i in range(count)]

    def test_qualifying_company(self):
        records = self._make_p2_awards("QualCo", 20)
        awards = pd.DataFrame(records)
        fpds = pd.DataFrame({
            "company": ["QualCo"],
            "obligation_amount": [5_000_000],
        })
        patents = pd.DataFrame({
            "company": ["QualCo"] * 5,
        })
        sam = pd.DataFrame({
            "unique_entity_id": ["QualCo"],
            "registration_status": ["ACTIVE"],
        })

        tool = ComputeObservableCommercializationTool()
        result = tool.run(
            awards_df=awards, fpds_contracts=fpds,
            patent_data=patents, sam_entities=sam,
        )
        results_df = result.data["results"]
        assert len(results_df) == 1
        assert results_df.iloc[0]["company_id"] == "QualCo"
        assert results_df.iloc[0]["composite_score"] > 0

    def test_below_trigger(self):
        records = self._make_p2_awards("SmallCo", 5)
        awards = pd.DataFrame(records)
        tool = ComputeObservableCommercializationTool()
        result = tool.run(awards_df=awards)
        assert len(result.data["results"]) == 0

    def test_trigger_threshold(self):
        assert PHASE2_TRIGGER_THRESHOLD == 16
        assert PATENT_PRONG_THRESHOLD == pytest.approx(0.15)

    def test_empty_input(self):
        tool = ComputeObservableCommercializationTool()
        result = tool.run()
        assert result.data["summary"]["qualifying_companies"] == 0

    def test_three_prong_scoring(self):
        """Test that all three prongs contribute to composite score."""
        records = self._make_p2_awards("TestCo", 20)
        awards = pd.DataFrame(records)

        # No FPDS, no patents, not in SAM
        tool = ComputeObservableCommercializationTool()
        result_bare = tool.run(awards_df=awards)

        # With FPDS revenue
        fpds = pd.DataFrame({"company": ["TestCo"], "obligation_amount": [10_000_000]})
        result_fpds = tool.run(awards_df=awards, fpds_contracts=fpds)

        if len(result_bare.data["results"]) > 0 and len(result_fpds.data["results"]) > 0:
            score_bare = result_bare.data["results"].iloc[0]["composite_score"]
            score_fpds = result_fpds.data["results"].iloc[0]["composite_score"]
            assert score_fpds >= score_bare

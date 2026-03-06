"""Tests for SBIR/STTR benchmark eligibility evaluator.

Tests cover:
- FY window construction
- Transition rate benchmark evaluation (standard and increased tiers)
- Commercialization rate benchmark evaluation (standard and increased tiers)
- Sensitivity analysis for companies near thresholds
- Edge cases (zero awards, exactly at threshold, etc.)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.models.benchmark_models import (
    BenchmarkStatus,
    BenchmarkTier,
    ConsequenceType,
)
from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator


def _make_awards_df(
    records: list[dict],
) -> pd.DataFrame:
    """Helper to build a minimal awards DataFrame from dicts."""
    return pd.DataFrame(records)


def _phase1_awards(company: str, uei: str, count: int, fy_start: int) -> list[dict]:
    """Generate `count` Phase I award records starting at `fy_start`."""
    return [
        {
            "award_id": f"{uei}-P1-{i}",
            "company_name": company,
            "company_uei": uei,
            "phase": "I",
            "award_year": fy_start + (i % 5),
            "award_amount": 150_000,
        }
        for i in range(count)
    ]


def _phase2_awards(company: str, uei: str, count: int, fy_start: int) -> list[dict]:
    """Generate `count` Phase II award records starting at `fy_start`."""
    return [
        {
            "award_id": f"{uei}-P2-{i}",
            "company_name": company,
            "company_uei": uei,
            "phase": "II",
            "award_year": fy_start + (i % 5),
            "award_amount": 1_000_000,
        }
        for i in range(count)
    ]


# ─── FY Window Tests ─────────────────────────────────────────────────


class TestFYWindows:
    def test_transition_phase1_window_excludes_most_recent(self):
        """Phase I window should exclude the most recently completed FY."""
        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        p1_window = evaluator.transition_window["phase1"]
        # evaluation_fy=2025, most_recent_completed=2024
        # Phase I excludes 1 recent year -> end_fy = 2023
        # 5 year lookback -> start_fy = 2019
        assert p1_window.start_fy == 2019
        assert p1_window.end_fy == 2023

    def test_transition_phase2_window_includes_most_recent(self):
        """Phase II window should include the most recently completed FY."""
        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        p2_window = evaluator.transition_window["phase2"]
        # Phase II excludes 0 recent years -> end_fy = 2024
        # 5 year lookback -> start_fy = 2020
        assert p2_window.start_fy == 2020
        assert p2_window.end_fy == 2024

    def test_commercialization_window_excludes_two_recent(self):
        """Commercialization window should exclude 2 most recently completed FYs."""
        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        comm_window = evaluator.commercialization_window
        # most_recent_completed=2024, exclude 2 -> end_fy = 2022
        # 10 year lookback -> start_fy = 2013
        assert comm_window.start_fy == 2013
        assert comm_window.end_fy == 2022


# ─── Transition Rate Benchmark Tests ─────────────────────────────────


class TestTransitionRateBenchmark:
    def test_not_subject_below_threshold(self):
        """Company with <21 Phase I awards is not subject."""
        records = _phase1_awards("SmallCo", "UEI000000001", 10, 2019)
        records += _phase2_awards("SmallCo", "UEI000000001", 3, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        assert len(summary.transition_results) == 1
        result = summary.transition_results[0]
        assert result.tier == BenchmarkTier.NOT_SUBJECT
        assert result.status == BenchmarkStatus.NOT_APPLICABLE
        assert result.consequence == ConsequenceType.NONE

    def test_standard_tier_pass(self):
        """Company with >=21 Phase I and ratio >=0.25 passes standard tier."""
        # 25 Phase I in window, 7 Phase II -> ratio = 7/25 = 0.28 >= 0.25
        records = _phase1_awards("MidCo", "UEI000000002", 25, 2019)
        records += _phase2_awards("MidCo", "UEI000000002", 7, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        tr = summary.transition_results[0]
        assert tr.tier == BenchmarkTier.STANDARD
        assert tr.status == BenchmarkStatus.PASS
        assert tr.consequence == ConsequenceType.NONE
        assert tr.transition_ratio is not None
        assert tr.transition_ratio >= 0.25

    def test_standard_tier_fail(self):
        """Company with >=21 Phase I but ratio <0.25 fails -> ineligible 1yr."""
        # 30 Phase I, 3 Phase II -> ratio = 0.10 < 0.25
        records = _phase1_awards("FailCo", "UEI000000003", 30, 2019)
        records += _phase2_awards("FailCo", "UEI000000003", 3, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        tr = summary.transition_results[0]
        assert tr.tier == BenchmarkTier.STANDARD
        assert tr.status == BenchmarkStatus.FAIL
        assert tr.consequence == ConsequenceType.PHASE1_INELIGIBLE_1YR

    def test_increased_tier_pass(self):
        """Company with >=51 Phase I and ratio >=0.50 passes increased tier."""
        # 55 Phase I, 28 Phase II -> ratio = 28/55 ~ 0.509 >= 0.50
        records = _phase1_awards("BigCo", "UEI000000004", 55, 2019)
        records += _phase2_awards("BigCo", "UEI000000004", 28, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        tr = summary.transition_results[0]
        assert tr.tier == BenchmarkTier.INCREASED_TIER1
        assert tr.status == BenchmarkStatus.PASS

    def test_increased_tier_fail(self):
        """Company with >=51 Phase I but ratio <0.50 -> capped 20 per agency."""
        # 60 Phase I, 10 Phase II -> ratio = 0.167 < 0.50
        records = _phase1_awards("BigFailCo", "UEI000000005", 60, 2019)
        records += _phase2_awards("BigFailCo", "UEI000000005", 10, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        tr = summary.transition_results[0]
        assert tr.tier == BenchmarkTier.INCREASED_TIER1
        assert tr.status == BenchmarkStatus.FAIL
        assert tr.consequence == ConsequenceType.CAPPED_20_AWARDS_PER_AGENCY

    def test_exactly_at_threshold(self):
        """Company with exactly 21 Phase I is subject to standard tier."""
        records = _phase1_awards("EdgeCo", "UEI000000006", 21, 2019)
        records += _phase2_awards("EdgeCo", "UEI000000006", 6, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        tr = summary.transition_results[0]
        assert tr.tier == BenchmarkTier.STANDARD


# ─── Commercialization Rate Benchmark Tests ──────────────────────────


class TestCommercializationRateBenchmark:
    def test_not_subject_below_16_phase2(self):
        """Company with <16 Phase II (in comm window) is not subject."""
        # Phase II awards in comm window (FY 2013-2022 for eval FY 2025)
        records = _phase2_awards("SmallP2", "UEI000000010", 10, 2013)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        cr = summary.commercialization_results[0]
        assert cr.tier == BenchmarkTier.NOT_SUBJECT
        assert cr.status == BenchmarkStatus.NOT_APPLICABLE

    def test_standard_tier_pass_via_sales(self):
        """Company with >=16 Phase II and >=100K avg sales passes."""
        records = _phase2_awards("SalesCo", "UEI000000011", 20, 2013)
        df = _make_awards_df(records)

        # Commercialization data: $2.5M total for 20 Phase II = $125K avg
        comm_df = pd.DataFrame([{
            "company_id": "uei:UEI000000011",
            "total_sales_and_investment": 2_500_000,
            "patent_count": 0,
        }])

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df, comm_df)

        cr = summary.commercialization_results[0]
        assert cr.tier == BenchmarkTier.STANDARD
        assert cr.status == BenchmarkStatus.PASS

    def test_standard_tier_pass_via_patents(self):
        """Company with >=16 Phase II and >=15% patent rate passes (standard only)."""
        records = _phase2_awards("PatentCo", "UEI000000012", 20, 2013)
        df = _make_awards_df(records)

        # 4 patents / 20 Phase II = 20% >= 15%
        comm_df = pd.DataFrame([{
            "company_id": "uei:UEI000000012",
            "total_sales_and_investment": 0,
            "patent_count": 4,
        }])

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df, comm_df)

        cr = summary.commercialization_results[0]
        assert cr.tier == BenchmarkTier.STANDARD
        assert cr.status == BenchmarkStatus.PASS
        assert cr.patents_path_available is True

    def test_increased_tier1_no_patent_path(self):
        """Company at increased tier 1 (>=51 Phase II) cannot use patent path."""
        records = _phase2_awards("BigP2Co", "UEI000000013", 55, 2013)
        df = _make_awards_df(records)

        # Has patents but not enough sales
        comm_df = pd.DataFrame([{
            "company_id": "uei:UEI000000013",
            "total_sales_and_investment": 1_000_000,  # ~18K avg < 250K
            "patent_count": 20,  # 36% rate, but patents path not available
        }])

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df, comm_df)

        cr = summary.commercialization_results[0]
        assert cr.tier == BenchmarkTier.INCREASED_TIER1
        assert cr.patents_path_available is False
        assert cr.status == BenchmarkStatus.FAIL


# ─── Sensitivity Analysis Tests ──────────────────────────────────────


class TestSensitivityAnalysis:
    def test_approaching_transition_threshold(self):
        """Company with 18 Phase I (3 away from 21) should be flagged at-risk."""
        records = _phase1_awards("AlmostCo", "UEI000000020", 18, 2019)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(
            evaluation_fy=2025, sensitivity_margin_awards=5
        )
        summary = evaluator.evaluate(df)

        at_risk = [s for s in summary.sensitivity_results if s.at_risk_transition]
        assert len(at_risk) == 1
        assert at_risk[0].phase1_to_standard_transition == 3

    def test_near_failing_transition(self):
        """Company subject to benchmark but close to failing should be at-risk."""
        # 25 Phase I, 7 Phase II -> ratio = 0.28, margin = 0.03 from 0.25
        records = _phase1_awards("NarrowCo", "UEI000000021", 25, 2019)
        records += _phase2_awards("NarrowCo", "UEI000000021", 7, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(
            evaluation_fy=2025, sensitivity_margin_ratio=0.05
        )
        summary = evaluator.evaluate(df)

        at_risk = [s for s in summary.sensitivity_results if s.at_risk_transition]
        assert len(at_risk) == 1
        assert at_risk[0].transition_rate_margin is not None
        assert at_risk[0].transition_rate_margin > 0  # Still passing, but narrow

    def test_not_at_risk_wide_margin(self):
        """Company well above threshold should not be flagged at-risk."""
        # 30 Phase I, 20 Phase II -> ratio = 0.667, margin = 0.417 from 0.25
        records = _phase1_awards("SafeCo", "UEI000000022", 30, 2019)
        records += _phase2_awards("SafeCo", "UEI000000022", 20, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(
            evaluation_fy=2025, sensitivity_margin_ratio=0.05
        )
        summary = evaluator.evaluate(df)

        # Should still be in sensitivity results (subject to benchmark) but not flagged at-risk
        at_risk = [s for s in summary.sensitivity_results if s.at_risk_transition]
        assert len(at_risk) == 0


# ─── Multiple Company Tests ──────────────────────────────────────────


class TestMultipleCompanies:
    def test_evaluates_all_companies(self):
        """Evaluator should process all companies in the dataset."""
        records = (
            _phase1_awards("CompanyA", "UEI000000030", 5, 2019)
            + _phase1_awards("CompanyB", "UEI000000031", 25, 2019)
            + _phase2_awards("CompanyB", "UEI000000031", 8, 2020)
            + _phase1_awards("CompanyC", "UEI000000032", 55, 2019)
            + _phase2_awards("CompanyC", "UEI000000032", 30, 2020)
        )
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        assert summary.total_companies_evaluated == 3
        # CompanyA: not subject, CompanyB: standard, CompanyC: increased
        tiers = {r.company_name: r.tier for r in summary.transition_results if r.company_name}
        assert tiers.get("CompanyA") == BenchmarkTier.NOT_SUBJECT
        assert tiers.get("CompanyB") == BenchmarkTier.STANDARD
        assert tiers.get("CompanyC") == BenchmarkTier.INCREASED_TIER1

    def test_summary_counts(self):
        """Summary counts should reflect the evaluation results."""
        records = (
            _phase1_awards("SubjectCo", "UEI000000040", 25, 2019)
            + _phase2_awards("SubjectCo", "UEI000000040", 2, 2020)  # ratio 0.08 -> FAIL
            + _phase1_awards("FreeCo", "UEI000000041", 5, 2019)
        )
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        assert summary.companies_subject_to_transition == 1
        assert summary.companies_failing_transition == 1


# ─── Edge Cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_dataframe(self):
        """Empty DataFrame should return empty results."""
        df = pd.DataFrame(columns=["award_id", "company_name", "phase", "award_year"])
        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)
        assert summary.total_companies_evaluated == 0

    def test_awards_outside_window(self):
        """Awards outside the evaluation window should not be counted."""
        # Phase I awards in 2010 — well before the 2019-2023 window for FY 2025
        records = _phase1_awards("OldCo", "UEI000000050", 30, 2010)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)

        # Company should have 0 Phase I in the transition window
        tr = summary.transition_results[0]
        assert tr.phase1_count == 0
        assert tr.tier == BenchmarkTier.NOT_SUBJECT

    def test_report_generation(self):
        """Report generation should produce valid markdown."""
        records = (
            _phase1_awards("ReportCo", "UEI000000060", 25, 2019)
            + _phase2_awards("ReportCo", "UEI000000060", 8, 2020)
        )
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)
        report = evaluator.generate_report(summary)

        assert "# SBIR/STTR Benchmark Eligibility Report" in report
        assert "FY 2025" in report or "2025" in report
        assert "ReportCo" in report

    def test_to_dict_serialization(self):
        """Summary should serialize to dict without errors."""
        records = _phase1_awards("DictCo", "UEI000000070", 25, 2019)
        records += _phase2_awards("DictCo", "UEI000000070", 7, 2020)
        df = _make_awards_df(records)

        evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=2025)
        summary = evaluator.evaluate(df)
        result = summary.to_dict()

        assert isinstance(result, dict)
        assert "transition_results" in result
        assert "commercialization_results" in result
        assert "sensitivity_results" in result
        assert result["evaluation_fy"] == 2025

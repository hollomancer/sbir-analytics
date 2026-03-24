"""Tests for Mission A: Cross-Agency Portfolio Analysis tools."""

import pytest
import numpy as np
import pandas as pd

from sbir_etl.tools.mission_a.extract_topics import ExtractTopicsTool
from sbir_etl.tools.mission_a.cluster_topics import ClusterTopicsTool
from sbir_etl.tools.mission_a.detect_gaps import DetectGapsTool, NSTC_CET_AREAS
from sbir_etl.tools.mission_a.compute_portfolio_metrics import ComputePortfolioMetricsTool, _compute_hhi


# ---- extract_topics ----

class TestExtractTopicsTool:
    def test_basic_extraction(self):
        awards = pd.DataFrame({
            "solicitation_topic": ["T001", "T001", "T002"],
            "agency": ["DoD", "DoD", "DOE"],
            "abstract": ["Battery research", "Battery development", "Solar panel tech"],
            "award_amount": [100000, 150000, 200000],
            "fiscal_year": [2023, 2024, 2024],
            "company": ["Acme", "Widget", "Solar Co"],
        })
        tool = ExtractTopicsTool()
        result = tool.run(awards_df=awards)
        assert result.metadata.tool_name == "extract_topics"
        assert isinstance(result.data, pd.DataFrame)
        assert len(result.data) == 2  # 2 topics

    def test_fiscal_year_filter(self):
        awards = pd.DataFrame({
            "solicitation_topic": ["T001", "T002"],
            "agency": ["DoD", "DOE"],
            "abstract": ["Test 1", "Test 2"],
            "fiscal_year": [2022, 2024],
        })
        tool = ExtractTopicsTool()
        result = tool.run(awards_df=awards, fiscal_years=[2024])
        assert len(result.data) == 1

    def test_empty_input(self):
        tool = ExtractTopicsTool()
        result = tool.run()
        assert len(result.data) == 0
        assert "No topics provided" not in result.metadata.warnings  # different message


# ---- cluster_topics ----

class TestClusterTopicsTool:
    def test_basic_clustering(self):
        topics = pd.DataFrame({
            "topic_id": ["T1", "T2", "T3"],
            "agency": ["DoD", "DOE", "NIH"],
            "title": ["Battery tech", "Battery storage", "Cancer treatment"],
            "description": [
                "Advanced lithium batteries for military use",
                "Grid-scale battery storage solutions",
                "Novel cancer immunotherapy approach",
            ],
        })
        # Create embeddings where T1 and T2 are similar
        embeddings = np.array([
            [1.0, 0.1, 0.0],  # T1: battery-ish
            [0.9, 0.2, 0.0],  # T2: also battery-ish
            [0.0, 0.0, 1.0],  # T3: completely different
        ])
        tool = ClusterTopicsTool()
        result = tool.run(
            topics_df=topics,
            embeddings=embeddings,
            similarity_threshold=0.85,
        )
        assert isinstance(result.data, dict)
        assert "clusters" in result.data
        assert "stats" in result.data

    def test_empty_topics(self):
        tool = ClusterTopicsTool()
        result = tool.run()
        assert any("No topics provided" in w for w in result.metadata.warnings)

    def test_cross_agency_filter(self):
        topics = pd.DataFrame({
            "topic_id": ["T1", "T2"],
            "agency": ["DoD", "DoD"],  # Same agency
            "title": ["Battery 1", "Battery 2"],
        })
        embeddings = np.array([[1.0, 0.0], [0.99, 0.01]])
        tool = ClusterTopicsTool()
        result = tool.run(
            topics_df=topics,
            embeddings=embeddings,
            cross_agency_only=True,
        )
        # Should not cluster since same agency
        assert result.data["stats"]["num_clusters"] == 0


# ---- detect_gaps ----

class TestDetectGapsTool:
    def test_detects_unfunded_areas(self):
        awards = pd.DataFrame({
            "cet_primary": ["Artificial Intelligence"] * 5,
            "fiscal_year": [2021, 2022, 2023, 2024, 2025],
            "agency": ["DoD"] * 5,
            "award_amount": [100000] * 5,
        })
        tool = DetectGapsTool()
        result = tool.run(classified_awards=awards)
        unfunded = result.data["unfunded_cet_areas"]
        # All CET areas except AI should be unfunded
        assert len(unfunded) == len(NSTC_CET_AREAS) - 1

    def test_detects_single_agency_dependency(self):
        awards = pd.DataFrame({
            "cet_primary": ["Quantum Information Technologies"] * 10,
            "fiscal_year": [2023] * 10,
            "agency": ["DoD"] * 10,
            "award_amount": [50000] * 10,
        })
        tool = DetectGapsTool()
        result = tool.run(classified_awards=awards)
        single_deps = result.data["single_agency_dependencies"]
        assert len(single_deps) >= 1
        assert single_deps[0]["sole_agency"] == "DoD"

    def test_nstc_taxonomy_default(self):
        assert len(NSTC_CET_AREAS) == 20
        assert "Artificial Intelligence" in NSTC_CET_AREAS
        assert "Quantum Information Technologies" in NSTC_CET_AREAS

    def test_empty_input(self):
        tool = DetectGapsTool()
        result = tool.run()
        assert len(result.data["unfunded_cet_areas"]) == 20  # All unfunded


# ---- compute_portfolio_metrics ----

class TestComputeHHI:
    def test_monopoly(self):
        assert _compute_hhi([100.0]) == pytest.approx(1.0)

    def test_equal_shares(self):
        # 4 equal shares → HHI = 4 * (0.25)^2 = 0.25
        assert _compute_hhi([25.0, 25.0, 25.0, 25.0]) == pytest.approx(0.25)

    def test_empty(self):
        assert _compute_hhi([]) == 0.0


class TestComputePortfolioMetricsTool:
    def test_agency_hhi(self):
        awards = pd.DataFrame({
            "cet_primary": ["AI"] * 6,
            "agency": ["DoD", "DoD", "DoD", "DOE", "NIH", "NIH"],
            "company": ["A", "B", "C", "D", "E", "F"],
            "state": ["CA", "MA", "TX", "NY", "CA", "MA"],
            "fiscal_year": [2024] * 6,
            "award_amount": [100000] * 6,
        })
        tool = ComputePortfolioMetricsTool()
        result = tool.run(classified_awards=awards)
        assert isinstance(result.data, dict)
        assert "AI" in result.data["agency_hhi_by_cet"]
        hhi = result.data["agency_hhi_by_cet"]["AI"]["hhi"]
        assert 0 < hhi < 1  # Not monopoly, not perfect competition

    def test_cross_agency_companies(self):
        awards = pd.DataFrame({
            "cet_primary": ["AI", "AI"],
            "agency": ["DoD", "DOE"],
            "company": ["Acme", "Acme"],  # Same company, different agencies
            "state": ["CA", "CA"],
            "fiscal_year": [2024, 2024],
        })
        tool = ComputePortfolioMetricsTool()
        result = tool.run(classified_awards=awards)
        assert result.data["cross_agency_company_count"] == 1

    def test_empty_input(self):
        tool = ComputePortfolioMetricsTool()
        result = tool.run()
        assert result.data["summary"]["total_awards"] == 0

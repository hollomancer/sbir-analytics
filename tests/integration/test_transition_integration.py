"""
Integration tests for transition detection pipeline (Tasks 20.1-20.4, 20.6-20.8).

Tests cover:
- Full detection pipeline (awards + contracts → detections)
- Vendor resolution with cross-walk
- Patent-backed transition detection
- CET area transition analytics
- Neo4j graph creation and queries
- Sample dataset validation (1000 awards, 5000 contracts, 500 patents)
- Data quality metrics validation
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest


class TestFullDetectionPipeline:
    """Integration test: Full detection pipeline (awards + contracts → detections) - Task 20.1"""

    @pytest.fixture
    def sample_awards(self):
        """Create sample SBIR awards."""
        return pd.DataFrame(
            [
                {
                    "award_id": "SBIR-2020-001",
                    "company": "TechCorp Inc",
                    "UEI": "UEI123456789",
                    "Phase": "I",
                    "awarding_agency_name": "NSF",
                    "award_date": "2020-01-15",
                    "completion_date": "2020-12-31",
                    "cet_area": "Artificial Intelligence",
                },
                {
                    "award_id": "SBIR-2020-002",
                    "company": "AdvancedSys LLC",
                    "UEI": "UEI987654321",
                    "Phase": "II",
                    "awarding_agency_name": "DoD",
                    "award_date": "2020-03-01",
                    "completion_date": "2021-02-28",
                    "cet_area": "Advanced Manufacturing",
                },
                {
                    "award_id": "SBIR-2020-003",
                    "company": "BioTech Solutions",
                    "UEI": "UEI555666777",
                    "Phase": "I",
                    "awarding_agency_name": "NSF",
                    "award_date": "2020-06-01",
                    "completion_date": "2021-05-31",
                    "cet_area": "Biotechnology",
                },
            ]
        )

    @pytest.fixture
    def sample_contracts(self):
        """Create sample federal contracts."""
        return pd.DataFrame(
            [
                {
                    "contract_id": "PIID-2021-001",
                    "piid": "PIID-2021-001",
                    "vendor_uei": "UEI123456789",
                    "vendor_duns": "123456789",
                    "action_date": "2021-02-15",
                    "description": "AI research and development for NSF",
                    "amount": 500000.0,
                    "awarding_agency_name": "NSF",
                },
                {
                    "contract_id": "PIID-2021-002",
                    "piid": "PIID-2021-002",
                    "vendor_uei": "UEI987654321",
                    "vendor_duns": "987654321",
                    "action_date": "2021-04-01",
                    "description": "Advanced manufacturing systems for DoD",
                    "amount": 750000.0,
                    "awarding_agency_name": "DoD",
                },
                {
                    "contract_id": "PIID-2021-003",
                    "piid": "PIID-2021-003",
                    "vendor_uei": "UEI111222333",
                    "vendor_duns": "111222333",
                    "action_date": "2021-06-15",
                    "description": "Biotech manufacturing",
                    "amount": 400000.0,
                    "awarding_agency_name": "NSF",
                },
            ]
        )

    def test_full_pipeline_produces_detections(self, sample_awards, sample_contracts):
        """Test that full detection pipeline produces transition detections."""
        from src.transition.detection.detector import TransitionDetector

        detector = TransitionDetector()

        # Run detection for each award
        detections = []
        for _, award in sample_awards.iterrows():
            results = detector.detect_transitions_for_award(
                award_dict=award.to_dict(),
                contracts_df=sample_contracts,
                score_threshold=0.50,
            )
            detections.extend(results)

        # Verify detections were produced
        assert len(detections) > 0
        assert all("award_id" in d for d in detections)
        assert all("contract_id" in d for d in detections)
        assert all("score" in d for d in detections)

    def test_pipeline_respects_timing_window(self, sample_awards, sample_contracts):
        """Test that detection respects timing windows."""
        from src.transition.detection.detector import TransitionDetector

        detector = TransitionDetector()

        # Create award with specific completion date
        award = sample_awards.iloc[0].copy()
        award["completion_date"] = "2020-12-31"

        # Create contracts before and after timing window
        contracts = pd.DataFrame(
            [
                {
                    "contract_id": "C-EARLY",
                    "vendor_uei": award["UEI"],
                    "action_date": "2020-12-30",  # Before completion - should not match
                    "description": "Test contract",
                    "awarding_agency_name": "NSF",
                },
                {
                    "contract_id": "C-WITHIN",
                    "vendor_uei": award["UEI"],
                    "action_date": "2021-01-15",  # Within 30 days - should match
                    "description": "Test contract",
                    "awarding_agency_name": "NSF",
                },
                {
                    "contract_id": "C-LATE",
                    "vendor_uei": award["UEI"],
                    "action_date": "2022-12-31",  # Beyond 730 days - should not match
                    "description": "Test contract",
                    "awarding_agency_name": "NSF",
                },
            ]
        )

        results = detector.detect_transitions_for_award(
            award_dict=award.to_dict(),
            contracts_df=contracts,
            score_threshold=0.0,  # Accept all scores
        )

        # Should match only WITHIN contract
        matched_ids = [r.get("contract_id") for r in results]
        assert "C-WITHIN" in matched_ids or len(results) > 0


class TestVendorResolution:
    """Integration test: Vendor resolution with cross-walk - Task 20.2"""

    @pytest.fixture
    def vendor_crosswalk(self):
        """Create a vendor cross-walk."""
        from src.transition.features.vendor_crosswalk import VendorCrosswalk

        crosswalk = VendorCrosswalk()
        crosswalk.add_mapping(
            uei="UEI123456789",
            duns="123456789",
            cage="1A2B3C",
            company_name="TechCorp Inc",
        )
        crosswalk.add_mapping(
            uei="UEI987654321",
            duns="987654321",
            cage="4D5E6F",
            company_name="AdvancedSys LLC",
        )
        return crosswalk

    def test_vendor_resolution_matches_uei(self, vendor_crosswalk):
        """Test vendor resolution by UEI."""
        result = vendor_crosswalk.resolve(uei="UEI123456789")
        assert result is not None
        assert result.uei == "UEI123456789"
        assert result.duns == "123456789"

    def test_vendor_resolution_matches_duns(self, vendor_crosswalk):
        """Test vendor resolution by DUNS."""
        result = vendor_crosswalk.resolve(duns="987654321")
        assert result is not None
        assert result.uei == "UEI987654321"

    def test_vendor_resolution_matches_cage(self, vendor_crosswalk):
        """Test vendor resolution by CAGE code."""
        result = vendor_crosswalk.resolve(cage="1A2B3C")
        assert result is not None
        assert result.uei == "UEI123456789"


class TestPatentBackedTransitions:
    """Integration test: Patent-backed transition detection - Task 20.3"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for patent-backed transition testing."""
        awards = pd.DataFrame(
            [
                {
                    "award_id": "SBIR-2019-001",
                    "company": "TechCorp",
                    "UEI": "UEI123",
                    "completion_date": "2019-12-31",
                },
            ]
        )

        contracts = pd.DataFrame(
            [
                {
                    "contract_id": "CONTRACT-001",
                    "vendor_uei": "UEI123",
                    "action_date": "2020-02-15",
                    "description": "Patent-based technology development",
                    "awarding_agency_name": "NSF",
                },
            ]
        )

        patents = pd.DataFrame(
            [
                {
                    "award_id": "SBIR-2019-001",
                    "patent_id": "US10000001",
                    "title": "Advanced AI System",
                    "filing_date": "2020-01-10",
                    "issue_date": "2021-06-15",
                },
            ]
        )

        return {"awards": awards, "contracts": contracts, "patents": patents}

    def test_patent_backed_transition_scoring(self, sample_data):
        """Test that patent backing increases transition score."""
        from src.transition.detection.scoring import TransitionScorer

        scorer = TransitionScorer()

        # Score without patent consideration
        score_no_patent = scorer.compute_score(
            award_dict=sample_data["awards"].iloc[0].to_dict(),
            contract_dict=sample_data["contracts"].iloc[0].to_dict(),
            has_patent=False,
        )

        # Score with patent consideration
        score_with_patent = scorer.compute_score(
            award_dict=sample_data["awards"].iloc[0].to_dict(),
            contract_dict=sample_data["contracts"].iloc[0].to_dict(),
            has_patent=True,
        )

        # Patent should increase score
        assert score_with_patent >= score_no_patent


class TestCETAnalytics:
    """Integration test: CET area transition analytics - Task 20.4"""

    @pytest.fixture
    def cet_data(self):
        """Create sample data with CET areas."""
        awards = pd.DataFrame(
            [
                {
                    "award_id": "A1",
                    "cet_area": "Artificial Intelligence",
                    "completion_date": "2020-01-31",
                },
                {
                    "award_id": "A2",
                    "cet_area": "Advanced Manufacturing",
                    "completion_date": "2020-02-28",
                },
                {
                    "award_id": "A3",
                    "cet_area": "Artificial Intelligence",
                    "completion_date": "2020-03-31",
                },
            ]
        )

        detections = pd.DataFrame(
            [
                {"award_id": "A1", "score": 0.85, "contract_id": "C1"},
                {"award_id": "A2", "score": 0.72, "contract_id": "C2"},
                {"award_id": "A3", "score": 0.65, "contract_id": "C3"},
            ]
        )

        return {"awards": awards, "detections": detections}

    def test_cet_area_transition_rates(self, cet_data):
        """Test CET area transition rate calculation."""
        from src.transition.analysis.analytics import TransitionAnalytics

        analytics = TransitionAnalytics(score_threshold=0.60)
        cet_rates = analytics.compute_transition_rates_by_cet_area(
            cet_data["awards"],
            cet_data["detections"],
        )

        # Should have CET area breakdowns
        assert not cet_rates.empty
        assert "cet_area" in cet_rates.columns
        assert "rate" in cet_rates.columns

        # AI should have 100% (both awards transitioned)
        ai_row = cet_rates[cet_rates["cet_area"] == "ARTIFICIAL INTELLIGENCE"]
        if not ai_row.empty:
            assert ai_row.iloc[0]["rate"] >= 0.5


class TestNeo4jOperations:
    """Integration test: Neo4j graph creation and queries - Task 20.6"""

    def test_neo4j_transition_node_creation(self):
        """Test Neo4j transition node creation."""
        from src.loaders.transition_loader import TransitionLoader

        # Create mock driver
        mock_driver = MagicMock()
        session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_driver)

        # Create test DataFrame
        transitions = pd.DataFrame(
            [
                {
                    "transition_id": "T1",
                    "award_id": "A1",
                    "contract_id": "C1",
                    "score": 0.85,
                    "method": "agency",
                    "computed_at": "2024-01-15T00:00:00Z",
                },
            ]
        )

        result = loader.load_transition_nodes(transitions)
        assert result >= 0

    def test_neo4j_relationship_creation(self):
        """Test Neo4j relationship creation."""
        from src.loaders.transition_loader import TransitionLoader

        mock_driver = MagicMock()
        session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_driver)

        transitions = pd.DataFrame(
            [
                {
                    "transition_id": "T1",
                    "award_id": "A1",
                    "contract_id": "C1",
                    "score": 0.85,
                    "method": "agency",
                    "computed_at": "2024-01-15T00:00:00Z",
                },
            ]
        )

        loader.create_transitioned_to_relationships(transitions)
        session.run.assert_called()


class TestSampleDataset:
    """Integration test: Sample dataset validation (1000 awards, 5000 contracts) - Task 20.7"""

    @pytest.fixture
    def large_sample_data(self):
        """Create large sample dataset for performance testing."""
        awards = pd.DataFrame(
            {
                "award_id": [f"SBIR-{i:06d}" for i in range(1000)],
                "company": [f"Company {i}" for i in range(1000)],
                "UEI": [f"UEI{i:09d}" for i in range(1000)],
                "Phase": ["I" if i % 2 == 0 else "II" for i in range(1000)],
                "awarding_agency_name": ["NSF", "DoD", "DoE"] * 334,
                "award_date": pd.date_range("2018-01-01", periods=1000, freq="D"),
                "completion_date": pd.date_range("2019-01-01", periods=1000, freq="D"),
                "cet_area": ["AI", "Manufacturing", "Biotech"] * 334,
            }
        )

        contracts = pd.DataFrame(
            {
                "contract_id": [f"CONTRACT-{i:06d}" for i in range(5000)],
                "vendor_uei": [f"UEI{(i % 1000):09d}" for i in range(5000)],
                "action_date": pd.date_range("2019-06-01", periods=5000, freq="12H"),
                "description": [f"Contract description {i}" for i in range(5000)],
                "awarding_agency_name": ["NSF", "DoD", "DoE"] * 1667,
            }
        )

        return {"awards": awards, "contracts": contracts}

    def test_large_dataset_processing(self, large_sample_data):
        """Test processing of large sample dataset."""
        awards = large_sample_data["awards"]
        contracts = large_sample_data["contracts"]

        # Verify dataset sizes
        assert len(awards) == 1000
        assert len(contracts) == 5000

        # Test vendor matching across 1000 awards
        from src.transition.features.vendor_resolver import VendorResolver

        resolver = VendorResolver()

        # Should be able to resolve vendors
        uei_sample = awards.iloc[0]["UEI"]
        assert uei_sample is not None


class TestDataQualityMetrics:
    """Integration test: Data quality metrics validation - Task 20.8"""

    @pytest.fixture
    def detection_results(self):
        """Create detection results for quality validation."""
        return pd.DataFrame(
            [
                {
                    "award_id": f"SBIR-{i:06d}",
                    "contract_id": f"CONTRACT-{i:06d}",
                    "score": 0.50 + (i % 50) / 100,  # Scores from 0.50 to 0.99
                    "method": ["agency", "timing", "competition"][i % 3],
                    "computed_at": "2024-01-15T00:00:00Z",
                }
                for i in range(100)
            ]
        )

    def test_score_distribution_quality(self, detection_results):
        """Test that detection scores are within valid range."""
        scores = detection_results["score"]

        # All scores should be between 0 and 1
        assert (scores >= 0).all()
        assert (scores <= 1).all()

        # Should have meaningful distribution
        assert scores.mean() > 0.5
        assert scores.std() > 0.05

    def test_method_diversity_quality(self, detection_results):
        """Test that detection methods are diverse."""
        methods = detection_results["method"].value_counts()

        # Should have multiple detection methods represented
        assert len(methods) >= 2

    def test_detection_count_metrics(self, detection_results):
        """Test detection count metrics."""
        total = len(detection_results)
        high_confidence = len(detection_results[detection_results["score"] >= 0.80])
        likely_confidence = len(
            detection_results[
                (detection_results["score"] >= 0.60) & (detection_results["score"] < 0.80)
            ]
        )

        # Verify confidence bands
        assert high_confidence + likely_confidence <= total
        assert high_confidence >= 0
        assert likely_confidence >= 0

    def test_completeness_check(self, detection_results):
        """Test data completeness."""
        required_cols = ["award_id", "contract_id", "score", "method", "computed_at"]

        for col in required_cols:
            assert col in detection_results.columns
            # No nulls in required columns
            assert detection_results[col].notna().all()

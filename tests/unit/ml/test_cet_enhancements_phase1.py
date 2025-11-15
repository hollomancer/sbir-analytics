"""
Unit tests for Phase 1 CET classifier enhancements.

Tests:
- Stop words filtering
- Negative keyword penalties
- Agency/branch priors
"""

import pytest
from src.ml.models.cet_classifier import ApplicabilityModel
from src.models.cet_models import CETArea


class TestNegativeKeywordFiltering:
    """Test negative keyword penalty application."""

    def test_negative_keyword_penalty_reduces_score(self):
        """Test that negative keywords reduce classification scores."""
        config = {"priors": {"enabled": False}}
        cet_areas = [
            CETArea(
                cet_id="quantum_information_science",
                name="Quantum Information Science",
                definition="Test",
                keywords=["quantum computing"],
                negative_keywords=["quantum mechanics", "quantum chemistry"],
                taxonomy_version="NSTC-2025Q1",
            )
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        # Test penalty application
        text_positive = "quantum computing algorithms"
        text_negative = "quantum mechanics research"

        score_positive = 80.0
        score_negative = model._apply_negative_keyword_penalty(
            score_positive, text_negative, ["quantum mechanics", "quantum chemistry"]
        )

        # Score should be reduced (80 * 0.7 = 56)
        assert score_negative < score_positive
        assert score_negative == pytest.approx(56.0, abs=0.1)

    def test_no_penalty_without_negative_keywords(self):
        """Test that scores are unchanged when negative keywords not present."""
        config = {"priors": {"enabled": False}}
        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=["machine learning"],
                negative_keywords=["ai-powered diagnostic"],
                taxonomy_version="NSTC-2025Q1",
            )
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        text = "machine learning framework for data analysis"
        score = 75.0

        penalized_score = model._apply_negative_keyword_penalty(
            score, text, ["ai-powered diagnostic"]
        )

        # No negative keywords present, score unchanged
        assert penalized_score == score


class TestAgencyBranchPriors:
    """Test agency and branch prior application."""

    def test_agency_priors_boost_scores(self):
        """Test that agency priors boost relevant CET scores."""
        config = {
            "priors": {
                "enabled": True,
                "agencies": {
                    "Department of Defense": {
                        "hypersonics": 15,
                        "autonomous_systems": 10,
                    }
                },
                "branches": {},
            }
        }

        cet_areas = [
            CETArea(
                cet_id="hypersonics",
                name="Hypersonics",
                definition="Test",
                keywords=["hypersonic"],
                taxonomy_version="NSTC-2025Q1",
            ),
            CETArea(
                cet_id="autonomous_systems",
                name="Autonomous Systems",
                definition="Test",
                keywords=["autonomous"],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        base_scores = {"hypersonics": 50.0, "autonomous_systems": 40.0}

        adjusted_scores = model._apply_agency_branch_priors(
            base_scores, agency="Department of Defense"
        )

        # Scores should be boosted
        assert adjusted_scores["hypersonics"] == 65.0  # 50 + 15
        assert adjusted_scores["autonomous_systems"] == 50.0  # 40 + 10

    def test_branch_priors_override_agency(self):
        """Test that branch priors augment agency priors."""
        config = {
            "priors": {
                "enabled": True,
                "agencies": {
                    "Department of Defense": {
                        "hypersonics": 10,
                    }
                },
                "branches": {
                    "Air Force": {
                        "hypersonics": 20,  # Additional boost
                    }
                },
            }
        }

        cet_areas = [
            CETArea(
                cet_id="hypersonics",
                name="Hypersonics",
                definition="Test",
                keywords=["hypersonic"],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        base_scores = {"hypersonics": 50.0}

        adjusted_scores = model._apply_agency_branch_priors(
            base_scores, agency="Department of Defense", branch="Air Force"
        )

        # Agency +10, Branch +20 = +30 total
        assert adjusted_scores["hypersonics"] == 80.0  # 50 + 10 + 20

    def test_priors_disabled(self):
        """Test that priors can be disabled via config."""
        config = {
            "priors": {
                "enabled": False,  # Disabled
                "agencies": {
                    "Department of Defense": {
                        "hypersonics": 15,
                    }
                },
            }
        }

        cet_areas = [
            CETArea(
                cet_id="hypersonics",
                name="Hypersonics",
                definition="Test",
                keywords=["hypersonic"],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        base_scores = {"hypersonics": 50.0}

        adjusted_scores = model._apply_agency_branch_priors(
            base_scores, agency="Department of Defense"
        )

        # Priors disabled, scores unchanged
        assert adjusted_scores["hypersonics"] == 50.0

    def test_all_cets_baseline_boost(self):
        """Test _all_cets applies baseline boost to all CET areas."""
        config = {
            "priors": {
                "enabled": True,
                "agencies": {
                    "National Science Foundation": {
                        "_all_cets": 5,  # Baseline boost
                    }
                },
            }
        }

        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=["ai"],
                taxonomy_version="NSTC-2025Q1",
            ),
            CETArea(
                cet_id="biotechnologies",
                name="Biotechnologies",
                definition="Test",
                keywords=["biotech"],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        base_scores = {"artificial_intelligence": 60.0, "biotechnologies": 45.0}

        adjusted_scores = model._apply_agency_branch_priors(
            base_scores, agency="National Science Foundation"
        )

        # All scores boosted by +5
        assert adjusted_scores["artificial_intelligence"] == 65.0
        assert adjusted_scores["biotechnologies"] == 50.0


class TestStopWordsIntegration:
    """Test stop words are properly passed to vectorizer."""

    def test_stop_words_in_config(self):
        """Test that stop words from config are used in vectorizer."""
        config = {
            "tfidf": {
                "stop_words": ["sbir", "sttr", "phase", "award"],
                "keyword_boost_factor": 2.0,
                "max_features": 5000,
            },
            "priors": {"enabled": False},
            "logistic_regression": {},
            "feature_selection": {"enabled": False},
            "calibration": {},
        }

        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=["machine learning"],
                taxonomy_version="NSTC-2025Q1",
            )
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")
        pipeline = model._build_pipeline("artificial_intelligence")

        vectorizer = pipeline.named_steps["vectorizer"]

        # Verify stop words are passed to vectorizer
        assert vectorizer.stop_words == ["sbir", "sttr", "phase", "award"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

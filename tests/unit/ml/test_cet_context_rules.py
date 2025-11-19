"""
Unit tests for Phase 3 CET classifier context rules.

Tests:
- Context rule matching and scoring
- Keyword combination detection
- Integration with classification pipeline
- Enable/disable functionality
"""

import pytest
from src.ml.models.cet_classifier import ApplicabilityModel
from src.models.cet_models import CETArea


class TestContextRulesApplication:
    """Test context rule evaluation and scoring."""

    def test_context_rule_boosts_score_when_keywords_present(self):
        """Test that context rules boost scores when all keywords are present."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": ["ai", "diagnostic"], "boost": 20},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        # Base scores
        scores = {"medical_devices": 50.0}

        # Text with matching keywords
        text = "AI-powered diagnostic system for medical imaging"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Score should be boosted by 20
        assert adjusted_scores["medical_devices"] == 70.0  # 50 + 20

    def test_context_rule_no_boost_when_keywords_missing(self):
        """Test that context rules don't boost when keywords are missing."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": ["ai", "diagnostic"], "boost": 20},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"medical_devices": 50.0}

        # Text missing "diagnostic" keyword
        text = "AI system for image processing"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Score should be unchanged
        assert adjusted_scores["medical_devices"] == 50.0

    def test_context_rule_requires_all_keywords(self):
        """Test that all keywords must be present for rule to apply."""
        config = {
            "context_rules": {
                "enabled": True,
                "autonomous_systems": [
                    {"keywords": ["ai", "autonomous", "vehicle"], "boost": 15},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="autonomous_systems",
                name="Autonomous Systems",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"autonomous_systems": 40.0}

        # Text missing "vehicle" keyword
        text = "AI for autonomous navigation"
        adjusted1 = model._apply_context_rules(scores, text)
        assert adjusted1["autonomous_systems"] == 40.0  # No boost

        # Text with all keywords
        text_all = "AI system for autonomous vehicle navigation"
        adjusted2 = model._apply_context_rules(scores, text_all)
        assert adjusted2["autonomous_systems"] == 55.0  # 40 + 15

    def test_multiple_context_rules_for_same_cet(self):
        """Test that multiple rules can apply to the same CET."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": ["ai", "diagnostic"], "boost": 20},
                    {"keywords": ["machine learning", "clinical"], "boost": 15},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"medical_devices": 40.0}

        # Text matching BOTH rules
        text = "AI-powered diagnostic system with machine learning for clinical use"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Both boosts should apply: 40 + 20 + 15 = 75
        assert adjusted_scores["medical_devices"] == 75.0

    def test_context_rule_case_insensitive(self):
        """Test that keyword matching is case-insensitive."""
        config = {
            "context_rules": {
                "enabled": True,
                "advanced_manufacturing": [
                    {"keywords": ["AI", "Manufacturing"], "boost": 20},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="advanced_manufacturing",
                name="Advanced Manufacturing",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"advanced_manufacturing": 50.0}

        # Text with different casing
        text = "ai for MANUFACTURING automation"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Should still match (case-insensitive)
        assert adjusted_scores["advanced_manufacturing"] == 70.0  # 50 + 20

    def test_context_rules_clamped_to_100(self):
        """Test that scores are clamped to 100 after context rule boost."""
        config = {
            "context_rules": {
                "enabled": True,
                "biotechnologies": [
                    {"keywords": ["ai", "genomic"], "boost": 30},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="biotechnologies",
                name="Biotechnologies",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"biotechnologies": 85.0}

        text = "AI for genomic analysis"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Should be clamped to 100 (not 85 + 30 = 115)
        assert adjusted_scores["biotechnologies"] == 100.0

    def test_context_rules_disabled(self):
        """Test that context rules can be disabled."""
        config = {
            "context_rules": {
                "enabled": False,  # Disabled
                "medical_devices": [
                    {"keywords": ["ai", "diagnostic"], "boost": 20},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"medical_devices": 50.0}

        # Text with matching keywords
        text = "AI-powered diagnostic system"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Score should be unchanged (rules disabled)
        assert adjusted_scores["medical_devices"] == 50.0

    def test_context_rules_for_multiple_cets(self):
        """Test context rules for multiple different CETs."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": ["ai", "medical"], "boost": 20},
                ],
                "advanced_manufacturing": [
                    {"keywords": ["ai", "manufacturing"], "boost": 18},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
            CETArea(
                cet_id="advanced_manufacturing",
                name="Advanced Manufacturing",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {
            "medical_devices": 45.0,
            "advanced_manufacturing": 55.0,
        }

        # Text matching manufacturing rule only
        text = "AI system for manufacturing process control"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Only manufacturing should be boosted
        assert adjusted_scores["medical_devices"] == 45.0  # Unchanged
        assert adjusted_scores["advanced_manufacturing"] == 73.0  # 55 + 18


class TestContextRulesEdgeCases:
    """Test edge cases and error handling."""

    def test_context_rules_missing_config(self):
        """Test that missing context_rules config doesn't crash."""
        config = {
            # No context_rules section
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"artificial_intelligence": 60.0}
        text = "Machine learning research"

        # Should not crash
        adjusted_scores = model._apply_context_rules(scores, text)
        assert adjusted_scores["artificial_intelligence"] == 60.0

    def test_context_rules_invalid_format(self):
        """Test that invalid rule format is handled gracefully."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": "invalid_format",  # Should be a list
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"medical_devices": 50.0}
        text = "AI diagnostic system"

        # Should not crash, score unchanged
        adjusted_scores = model._apply_context_rules(scores, text)
        assert adjusted_scores["medical_devices"] == 50.0

    def test_context_rule_empty_keywords(self):
        """Test that rules with empty keywords are skipped."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": [], "boost": 20},  # Empty keywords list
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {"medical_devices": 50.0}
        text = "AI diagnostic system"

        adjusted_scores = model._apply_context_rules(scores, text)

        # Score should be unchanged (rule skipped)
        assert adjusted_scores["medical_devices"] == 50.0


class TestContextRulesRealWorldScenarios:
    """Test realistic scenarios."""

    def test_ai_for_medical_diagnostics_disambiguation(self):
        """Test disambiguation: AI for medical → medical_devices, not AI."""
        config = {
            "context_rules": {
                "enabled": True,
                "medical_devices": [
                    {"keywords": ["ai", "diagnostic"], "boost": 25},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=["ai", "machine learning"],
                taxonomy_version="NSTC-2025Q1",
            ),
            CETArea(
                cet_id="medical_devices",
                name="Medical Devices",
                definition="Test",
                keywords=["medical", "diagnostic"],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        # Initial scores (hypothetical): AI slightly higher than medical devices
        scores = {
            "artificial_intelligence": 65.0,
            "medical_devices": 60.0,
        }

        text = "AI-powered diagnostic tool for medical imaging"

        adjusted_scores = model._apply_context_rules(scores, text)

        # medical_devices should now be higher due to context rule
        assert adjusted_scores["artificial_intelligence"] == 65.0  # Unchanged
        assert adjusted_scores["medical_devices"] == 85.0  # 60 + 25 > AI

    def test_ai_for_manufacturing_disambiguation(self):
        """Test disambiguation: AI for manufacturing → advanced_manufacturing."""
        config = {
            "context_rules": {
                "enabled": True,
                "advanced_manufacturing": [
                    {"keywords": ["machine learning", "production"], "boost": 22},
                ],
            },
            "priors": {"enabled": False},
        }

        cet_areas = [
            CETArea(
                cet_id="artificial_intelligence",
                name="Artificial Intelligence",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
            CETArea(
                cet_id="advanced_manufacturing",
                name="Advanced Manufacturing",
                definition="Test",
                keywords=[],
                taxonomy_version="NSTC-2025Q1",
            ),
        ]

        model = ApplicabilityModel(cet_areas, config, "NSTC-2025Q1")

        scores = {
            "artificial_intelligence": 70.0,
            "advanced_manufacturing": 55.0,
        }

        text = "Machine learning for production line optimization"

        adjusted_scores = model._apply_context_rules(scores, text)

        assert adjusted_scores["artificial_intelligence"] == 70.0
        assert adjusted_scores["advanced_manufacturing"] == 77.0  # 55 + 22


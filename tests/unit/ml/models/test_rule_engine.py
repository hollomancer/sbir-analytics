"""
Unit tests for the RuleEngine class.
"""

import pytest

from src.ml.models.rule_engine import RuleEngine


@pytest.fixture
def rule_engine_config():
    """
    Provides a sample config for the RuleEngine.
    """
    return {
        "priors": {
            "enabled": True,
            "agencies": {
                "NASA": {"space_systems": 10},
                "NIH": {"biotechnology": 15, "_all_cets": 5},
            },
            "branches": {
                "DARPA": {"AI_ML": 20},
            },
        },
        "context_rules": {
            "enabled": True,
            "AI_ML": [{"keywords": ["deep learning", "neural network"], "boost": 10}],
            "biotechnology": [{"keywords": ["crispr"], "boost": 20}],
        },
    }


@pytest.fixture
def cet_negative_keywords():
    """
    Provides sample negative keywords.
    """
    return {
        "quantum_computing": ["quantum mechanics"],
        "AI_ML": ["artificial insemination"],
    }


@pytest.fixture
def rule_engine(rule_engine_config, cet_negative_keywords):
    """
    Provides a RuleEngine instance.
    """
    return RuleEngine(rule_engine_config, cet_negative_keywords)


def test_apply_negative_keyword_penalty(rule_engine):
    scores = {"quantum_computing": 80.0, "AI_ML": 70.0}
    text = "This is about quantum mechanics and artificial intelligence."

    adjusted_scores = rule_engine._apply_negative_keyword_penalty(scores, text)

    assert adjusted_scores["quantum_computing"] == 80.0 * 0.7
    assert adjusted_scores["AI_ML"] == 70.0


def test_apply_agency_branch_priors(rule_engine):
    scores = {"space_systems": 50.0, "biotechnology": 60.0, "AI_ML": 70.0}

    # Test agency prior
    adjusted_scores = rule_engine._apply_agency_branch_priors(scores, "NASA", None)
    assert adjusted_scores["space_systems"] == 60.0
    assert adjusted_scores["biotechnology"] == 60.0
    assert adjusted_scores["AI_ML"] == 70.0

    # Test branch prior
    adjusted_scores = rule_engine._apply_agency_branch_priors(scores, "DOD", "DARPA")
    assert adjusted_scores["space_systems"] == 50.0
    assert adjusted_scores["biotechnology"] == 60.0
    assert adjusted_scores["AI_ML"] == 90.0

    # Test _all_cets prior
    adjusted_scores = rule_engine._apply_agency_branch_priors(scores, "NIH", None)
    assert adjusted_scores["space_systems"] == 55.0
    assert adjusted_scores["biotechnology"] == 75.0
    assert adjusted_scores["AI_ML"] == 75.0


def test_apply_context_rules(rule_engine):
    scores = {"AI_ML": 60.0, "biotechnology": 70.0}
    text = "This document discusses deep learning and neural networks for crispr."

    adjusted_scores = rule_engine._apply_context_rules(scores, text)

    assert adjusted_scores["AI_ML"] == 70.0
    assert adjusted_scores["biotechnology"] == 90.0


def test_apply_all_rules(rule_engine):
    scores = {"AI_ML": 60.0, "quantum_computing": 80.0}
    text = "This is about deep learning, neural networks, and quantum mechanics."

    adjusted_scores = rule_engine.apply_all_rules(scores, text, "DOD", "DARPA")

    # AI_ML: 60 (base) + 10 (context) + 20 (branch) = 90
    # quantum_computing: 80 (base) * 0.7 (negative keyword) = 56
    assert adjusted_scores["AI_ML"] == 90.0
    assert adjusted_scores["quantum_computing"] == 56.0

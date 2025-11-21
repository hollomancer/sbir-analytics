"""Tests covering Neo4j transition pathway queries."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _build_mock_queries():
    from src.transition.queries.pathway_queries import TransitionPathwayQueries

    mock_driver = MagicMock()
    session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = session
    return TransitionPathwayQueries(mock_driver), session


def test_award_to_contract_pathway_query():
    """Award → Transition → Contract pathway returns structured result."""
    queries, session = _build_mock_queries()

    mock_result = {
        "award_id": "SBIR-2020-001",
        "award_name": "AI Research",
        "transition_id": "TRANS-001",
        "transition_score": 0.85,
        "contract_id": "CONTRACT-001",
        "contract_name": "AI Development",
    }
    session.run.return_value = [MagicMock(items=lambda: mock_result.items())]

    result = queries.award_to_transition_to_contract(min_score=0.8)

    assert result.pathway_name == "Award → Transition → Contract"
    assert result.records_count >= 0


def test_transition_rates_by_cet_area_query():
    """CET area query returns metadata and record counts."""
    queries, _ = _build_mock_queries()
    result = queries.transition_rates_by_cet_area()

    assert result.pathway_name is not None
    assert isinstance(result.records_count, int)


def test_company_profile_queries_exposed():
    """Transition query object exposes the expected helper functions."""
    from src.transition.queries.pathway_queries import TransitionPathwayQueries

    queries = TransitionPathwayQueries(MagicMock())

    for attr in (
        "award_to_transition_to_contract",
        "award_to_patent_to_transition_to_contract",
        "award_to_cet_to_transition",
        "company_to_transition_profile",
        "transition_rates_by_cet_area",
        "patent_backed_transition_rates_by_cet_area",
    ):
        assert hasattr(queries, attr)


def test_pathway_query_execution_structure():
    """Mock query execution returns expected shape."""
    queries, session = _build_mock_queries()
    session.run.return_value = [
        MagicMock(items=lambda: [("pathway", {"award_id": "A1", "contract_id": "C1"})]),
        MagicMock(items=lambda: [("pathway", {"award_id": "A2", "contract_id": "C2"})]),
    ]

    result = queries.award_to_transition_to_contract(min_score=0.8)

    assert hasattr(result, "pathway_name")
    assert hasattr(result, "records_count")
    assert hasattr(result, "records")
    assert hasattr(result, "metadata")


"""Unit tests for PI enrichment orchestration logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sbir_etl.enrichers.pi_enrichment import (
    ORCIDRecord,
    PIPatentRecord,
    PIPublicationRecord,
    _is_sbir_award_type,
    _split_pi_name,
    lookup_pi_orcid,
    lookup_pi_patents,
    lookup_pi_publications,
)


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# _split_pi_name
# ---------------------------------------------------------------------------


class TestSplitPIName:
    def test_first_last(self):
        assert _split_pi_name("Jane Doe") == ("Jane", "Doe")

    def test_last_comma_first(self):
        assert _split_pi_name("Doe, Jane") == ("Jane", "Doe")

    def test_single_name(self):
        assert _split_pi_name("Madonna") == ("Madonna", "")

    def test_whitespace_stripped(self):
        assert _split_pi_name("  Jane   Doe  ") == ("Jane", "Doe")

    def test_multi_part_name_takes_first_and_last(self):
        assert _split_pi_name("Mary Jane Watson") == ("Mary", "Watson")


# ---------------------------------------------------------------------------
# _is_sbir_award_type
# ---------------------------------------------------------------------------


class TestIsSbirAwardType:
    @patch("sbir_etl.enrichers.pi_enrichment.classify_sbir_award")
    def test_returns_true_when_classified(self, mock_classify):
        mock_classify.return_value = {"program": "SBIR"}
        assert _is_sbir_award_type("SBIR Phase I", "12.900") is True
        mock_classify.assert_called_once_with(cfda_number="12.900", description="SBIR Phase I")

    @patch("sbir_etl.enrichers.pi_enrichment.classify_sbir_award")
    def test_returns_false_when_not_classified(self, mock_classify):
        mock_classify.return_value = None
        assert _is_sbir_award_type("General contract", "10.001") is False


# ---------------------------------------------------------------------------
# lookup_pi_patents
# ---------------------------------------------------------------------------


class TestLookupPIPatents:
    @patch("sbir_etl.enrichers.pi_enrichment.PatentsViewClient")
    def test_success_returns_record(self, MockClient):
        client = MockClient.return_value
        client.query_patents_by_assignee.return_value = [
            {
                "patent_title": "Novel Widget",
                "assignee_organization": "Acme Corp",
                "grant_date": "2020-01-15",
            },
            {
                "patent_title": "Better Widget",
                "assignee_organization": "Acme Corp",
                "grant_date": "2022-06-01",
            },
        ]

        result = lookup_pi_patents("Jane Doe", "Acme Corp")

        assert isinstance(result, PIPatentRecord)
        assert result.total_patents == 2
        assert "Novel Widget" in result.sample_titles
        assert "Acme Corp" in result.assignees
        assert result.date_range == ("2020-01-15", "2022-06-01")

    @patch("sbir_etl.enrichers.pi_enrichment.PatentsViewClient")
    def test_empty_results_returns_none(self, MockClient):
        client = MockClient.return_value
        client.query_patents_by_assignee.return_value = []

        result = lookup_pi_patents("Jane Doe", "Acme Corp")
        assert result is None

    @patch("sbir_etl.enrichers.pi_enrichment.PatentsViewClient")
    def test_api_error_returns_none(self, MockClient):
        client = MockClient.return_value
        client.query_patents_by_assignee.side_effect = RuntimeError("API down")

        result = lookup_pi_patents("Jane Doe", "Acme Corp")
        assert result is None

    def test_single_name_returns_none(self):
        """Single name has no last name, should return None early."""
        result = lookup_pi_patents("Madonna")
        assert result is None


# ---------------------------------------------------------------------------
# lookup_pi_publications
# ---------------------------------------------------------------------------


class TestLookupPIPublications:
    @patch("sbir_etl.enrichers.pi_enrichment.SemanticScholarClient")
    def test_success_returns_record(self, MockClient):
        mock_rec = MagicMock()
        mock_rec.total_papers = 42
        mock_rec.h_index = 10
        mock_rec.citation_count = 500
        mock_rec.sample_titles = ["Paper A", "Paper B"]
        mock_rec.affiliations = ["MIT"]

        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup_author.return_value = mock_rec

        result = lookup_pi_publications("Jane Doe")

        assert isinstance(result, PIPublicationRecord)
        assert result.total_papers == 42
        assert result.h_index == 10
        assert result.citation_count == 500
        assert result.affiliations == ["MIT"]

    @patch("sbir_etl.enrichers.pi_enrichment.SemanticScholarClient")
    def test_none_result_returns_none(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup_author.return_value = None

        result = lookup_pi_publications("Jane Doe")
        assert result is None

    @patch("sbir_etl.enrichers.pi_enrichment.SemanticScholarClient")
    def test_api_error_returns_none(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup_author.side_effect = RuntimeError("timeout")

        result = lookup_pi_publications("Jane Doe")
        assert result is None

    def test_single_name_returns_none(self):
        result = lookup_pi_publications("Prince")
        assert result is None


# ---------------------------------------------------------------------------
# lookup_pi_orcid
# ---------------------------------------------------------------------------


class TestLookupPIOrcid:
    @patch("sbir_etl.enrichers.pi_enrichment.ORCIDClient")
    def test_success_returns_record(self, MockClient):
        mock_rec = MagicMock()
        mock_rec.orcid_id = "0000-0001-2345-6789"
        mock_rec.given_name = "Jane"
        mock_rec.family_name = "Doe"
        mock_rec.affiliations = ["Stanford"]
        mock_rec.works_count = 20
        mock_rec.sample_work_titles = ["Study X"]
        mock_rec.funding_count = 3
        mock_rec.keywords = ["AI", "ML"]

        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup.return_value = mock_rec

        result = lookup_pi_orcid("Jane Doe")

        assert isinstance(result, ORCIDRecord)
        assert result.orcid_id == "0000-0001-2345-6789"
        assert result.given_name == "Jane"
        assert result.affiliations == ["Stanford"]
        assert result.works_count == 20

    @patch("sbir_etl.enrichers.pi_enrichment.ORCIDClient")
    def test_none_result_returns_none(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup.return_value = None

        result = lookup_pi_orcid("Jane Doe")
        assert result is None

    @patch("sbir_etl.enrichers.pi_enrichment.ORCIDClient")
    def test_api_error_returns_none(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup.side_effect = RuntimeError("connection refused")

        result = lookup_pi_orcid("Jane Doe")
        assert result is None

    def test_single_name_returns_none(self):
        result = lookup_pi_orcid("Cher")
        assert result is None

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
    lookup_pi_orcid_with_fallback,
    lookup_pi_patents,
    lookup_pi_patents_with_fallback,
    lookup_pi_publications,
    lookup_pi_publications_with_fallback,
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
    @patch("sbir_etl.enrichers.pi_enrichment.SyncSemanticScholarClient")
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

    @patch("sbir_etl.enrichers.pi_enrichment.SyncSemanticScholarClient")
    def test_none_result_returns_none(self, MockClient):
        ctx = MockClient.return_value.__enter__.return_value
        ctx.lookup_author.return_value = None

        result = lookup_pi_publications("Jane Doe")
        assert result is None

    @patch("sbir_etl.enrichers.pi_enrichment.SyncSemanticScholarClient")
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


# ---------------------------------------------------------------------------
# lookup_pi_patents_with_fallback
# ---------------------------------------------------------------------------

MODULE = "sbir_etl.enrichers.pi_enrichment"


class TestLookupPIPatentsWithFallback:
    @patch(f"{MODULE}.lookup_pi_patents")
    def test_returns_primary_when_available(self, mock_primary):
        record = PIPatentRecord(
            total_patents=3, sample_titles=["A"], assignees=["Acme"], date_range=("2020-01-01", "2023-01-01"),
        )
        mock_primary.return_value = record

        result = lookup_pi_patents_with_fallback("Jane Doe", "Acme Corp")
        assert result is record
        mock_primary.assert_called_once()

    @patch(f"{MODULE}.LensPatentClient")
    @patch(f"{MODULE}.lookup_pi_patents", return_value=None)
    def test_falls_back_to_lens_when_primary_returns_none(self, mock_primary, MockLens):
        from sbir_etl.enrichers.lens_patents import LensPatentRecord

        lens_ctx = MockLens.return_value.__enter__.return_value
        lens_ctx.search_patents_by_assignee.return_value = [
            LensPatentRecord(
                patent_number="LENS-001", title="Smart Widget",
                assignee="Acme Corp", filing_date="2021-03-15",
            ),
            LensPatentRecord(
                patent_number="LENS-002", title="Better Widget",
                assignee="Acme Corp", filing_date="2023-07-01",
            ),
        ]

        result = lookup_pi_patents_with_fallback("Jane Doe", "Acme Corp")

        assert result is not None
        assert isinstance(result, PIPatentRecord)
        assert result.total_patents == 2
        assert "Smart Widget" in result.sample_titles
        assert "Acme Corp" in result.assignees
        assert result.date_range == ("2021-03-15", "2023-07-01")

    @patch(f"{MODULE}.LensPatentClient")
    @patch(f"{MODULE}.lookup_pi_patents", return_value=None)
    def test_returns_none_when_both_fail(self, mock_primary, MockLens):
        lens_ctx = MockLens.return_value.__enter__.return_value
        lens_ctx.search_patents_by_assignee.return_value = []

        result = lookup_pi_patents_with_fallback("Jane Doe", "Acme Corp")
        assert result is None


# ---------------------------------------------------------------------------
# lookup_pi_publications_with_fallback
# ---------------------------------------------------------------------------


class TestLookupPIPublicationsWithFallback:
    @patch(f"{MODULE}.lookup_pi_publications")
    def test_returns_primary_when_available(self, mock_primary):
        record = PIPublicationRecord(
            total_papers=10, h_index=5, citation_count=100,
            sample_titles=["Paper A"], affiliations=["MIT"],
        )
        mock_primary.return_value = record

        result = lookup_pi_publications_with_fallback("Jane Doe")
        assert result is record

    @patch(f"{MODULE}.lookup_pi_orcid")
    @patch(f"{MODULE}.lookup_pi_publications", return_value=None)
    def test_falls_back_to_orcid_when_primary_returns_none(self, mock_primary, mock_orcid):
        mock_orcid.return_value = ORCIDRecord(
            orcid_id="0000-0001-2345-6789", given_name="Jane", family_name="Doe",
            affiliations=["Stanford"], works_count=15,
            sample_work_titles=["Study X", "Study Y"],
            funding_count=2, keywords=["AI"],
        )

        result = lookup_pi_publications_with_fallback("Jane Doe")

        assert result is not None
        assert isinstance(result, PIPublicationRecord)
        assert result.total_papers == 15
        assert result.h_index is None  # ORCID doesn't provide h-index
        assert result.citation_count == 0
        assert result.sample_titles == ["Study X", "Study Y"]
        assert result.affiliations == ["Stanford"]

    @patch(f"{MODULE}.lookup_pi_orcid", return_value=None)
    @patch(f"{MODULE}.lookup_pi_publications", return_value=None)
    def test_returns_none_when_both_fail(self, mock_primary, mock_orcid):
        result = lookup_pi_publications_with_fallback("Jane Doe")
        assert result is None


# ---------------------------------------------------------------------------
# lookup_pi_orcid_with_fallback
# ---------------------------------------------------------------------------


class TestLookupPIOrcidWithFallback:
    @patch(f"{MODULE}.lookup_pi_orcid")
    def test_returns_primary_when_available(self, mock_primary):
        record = ORCIDRecord(
            orcid_id="0000-0001-2345-6789", given_name="Jane", family_name="Doe",
            affiliations=["MIT"], works_count=20, sample_work_titles=["Study X"],
            funding_count=3, keywords=["AI"],
        )
        mock_primary.return_value = record

        result = lookup_pi_orcid_with_fallback("Jane Doe")
        assert result is record

    @patch(f"{MODULE}.lookup_pi_orcid", return_value=None)
    def test_returns_none_when_orcid_not_found(self, mock_primary):
        """Should NOT synthesize a fake ORCIDRecord."""
        result = lookup_pi_orcid_with_fallback("Jane Doe")
        assert result is None

"""Tests for Semantic Scholar client."""

from unittest.mock import Mock, patch

import pytest

from sbir_etl.enrichers.semantic_scholar import PublicationRecord, SemanticScholarClient

pytestmark = pytest.mark.fast


class TestSemanticScholarClient:
    def test_lookup_author_success(self):
        mock_http = Mock()
        # Search response
        search_resp = Mock()
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "data": [{"authorId": "12345", "name": "Jane Smith"}]
        }
        # Detail response
        detail_resp = Mock()
        detail_resp.status_code = 200
        detail_resp.json.return_value = {
            "name": "Jane Smith",
            "hIndex": 15,
            "citationCount": 500,
            "affiliations": ["MIT"],
            "papers": [
                {"title": "Paper 1", "year": 2024},
                {"title": "Paper 2", "year": 2023},
            ],
        }
        mock_http.get.side_effect = [search_resp, detail_resp]

        client = SemanticScholarClient()
        client._client = mock_http
        rec = client.lookup_author("Jane Smith")

        assert rec is not None
        assert rec.h_index == 15
        assert rec.total_papers == 2
        assert rec.citation_count == 500
        assert "MIT" in rec.affiliations

    def test_lookup_author_not_found(self):
        mock_http = Mock()
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"data": []}
        mock_http.get.return_value = resp

        client = SemanticScholarClient()
        client._client = mock_http
        assert client.lookup_author("Nobody") is None

    def test_context_manager(self):
        with SemanticScholarClient() as client:
            assert hasattr(client, "lookup_author")

    def test_publication_record_fields(self):
        rec = PublicationRecord(
            total_papers=10, h_index=5, citation_count=100,
            sample_titles=["T1"], affiliations=["Uni"]
        )
        assert rec.total_papers == 10

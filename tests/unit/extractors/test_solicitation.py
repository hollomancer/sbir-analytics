"""Tests for SolicitationExtractor."""

from unittest.mock import Mock

import pytest

from sbir_etl.extractors.solicitation import SolicitationExtractor

pytestmark = pytest.mark.fast


@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def extractor(mock_client):
    return SolicitationExtractor(http_client=mock_client)


def _ok_response(data):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = data
    return resp


class TestQueryByKeyword:
    def test_returns_matching_topics(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([
            {"topicCode": "AF241-001", "topicTitle": "Sensor Fusion"},
        ])
        results = extractor.query_by_keyword("AF241-001")
        assert len(results) == 1
        assert results[0]["topicCode"] == "AF241-001"

    def test_returns_empty_on_no_match(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([])
        results = extractor.query_by_keyword("NONEXISTENT")
        assert results == []

    def test_returns_empty_on_error(self, extractor, mock_client):
        mock_client.get.side_effect = Exception("network error")
        results = extractor.query_by_keyword("test")
        assert results == []


class TestQueryAwardsForTopic:
    def test_finds_matching_award(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([
            {"topicCode": "AF241-001", "topicTitle": "Sensor", "abstract": "Research on sensors"},
            {"topicCode": "AF241-002", "topicTitle": "Other"},
        ])
        result = extractor.query_awards_for_topic("AF241-001")
        assert result is not None
        assert result["topic_code"] == "AF241-001"
        assert result["title"] == "Sensor"
        assert result["description"] == "Research on sensors"

    def test_returns_none_when_no_match(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([
            {"topicCode": "OTHER", "topicTitle": "Unrelated"},
        ])
        result = extractor.query_awards_for_topic("AF241-001")
        assert result is None

    def test_returns_none_on_empty(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([])
        result = extractor.query_awards_for_topic("AF241-001")
        assert result is None

    def test_returns_none_on_error(self, extractor, mock_client):
        mock_client.get.side_effect = Exception("network error")
        result = extractor.query_awards_for_topic("test")
        assert result is None

    def test_prefers_topic_description(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([
            {
                "topicCode": "TC1",
                "topicTitle": "Title",
                "topicDescription": "Full topic desc",
                "abstract": "Award abstract",
            },
        ])
        result = extractor.query_awards_for_topic("TC1")
        assert result["description"] == "Full topic desc"

    def test_falls_back_to_abstract(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response([
            {"topicCode": "TC1", "awardTitle": "Award", "abstract": "Abstract text"},
        ])
        result = extractor.query_awards_for_topic("TC1")
        assert result["description"] == "Abstract text"
        assert result["title"] == "Award"


class TestQuerySolicitationsKeywordParam:
    def test_keyword_passed_to_api(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response({"results": []})
        extractor._query_solicitations(keyword="AF241-001", rows=25)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["keyword"] == "AF241-001"

    def test_keyword_and_year_combined(self, extractor, mock_client):
        mock_client.get.return_value = _ok_response({"results": []})
        extractor._query_solicitations(keyword="test", year=2025, rows=10)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["keyword"] == "test"
        assert params["year"] == 2025

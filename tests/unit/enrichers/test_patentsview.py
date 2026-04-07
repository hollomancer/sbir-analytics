"""Unit tests for PatentsView/ODP client query construction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sbir_etl.enrichers.patentsview import PatentsViewClient


pytestmark = pytest.mark.fast


@pytest.fixture
def client():
    """Create a PatentsViewClient with mocked config and API key."""
    mock_config = MagicMock()
    mock_config.enrichment.patentsview_api = {
        "base_url": "https://data.uspto.gov/api/v1/patent/applications",
        "api_key_env_var": "USPTO_ODP_API_KEY",
        "rate_limit_per_minute": 60,
        "timeout_seconds": 30,
        "cache": {"enabled": False, "cache_dir": "/tmp/test_cache", "ttl_hours": 1},
    }
    with patch("sbir_etl.enrichers.patentsview.get_config", return_value=mock_config):
        return PatentsViewClient(api_key="test-key")


class TestQueryPatentsByAssignee:
    """Test that query_patents_by_assignee builds correct API requests."""

    def test_uses_search_endpoint_with_q_param(self, client):
        """Verify /search endpoint and q parameter with quoted phrase."""
        client._make_request = MagicMock(return_value={"patentFileWrapperDataBag": []})

        client.query_patents_by_assignee("Acme Corp")

        client._make_request.assert_called_once()
        args, kwargs = client._make_request.call_args
        assert args[0] == "/search"
        assert kwargs["method"] == "GET"
        params = kwargs["params"]
        assert params["q"] == 'assignees.assigneeName:"Acme Corp"'

    def test_quotes_company_name_with_special_characters(self, client):
        """Company names with commas/periods are quoted for phrase matching."""
        client._make_request = MagicMock(return_value={"patentFileWrapperDataBag": []})

        client.query_patents_by_assignee("Verinomics, Inc.")

        params = client._make_request.call_args[1]["params"]
        assert params["q"] == 'assignees.assigneeName:"Verinomics, Inc."'

    def test_pagination_params(self, client):
        """Verify offset and limit are passed through."""
        client._make_request = MagicMock(return_value={"patentFileWrapperDataBag": []})

        client.query_patents_by_assignee("Test Co")

        params = client._make_request.call_args[1]["params"]
        assert params["offset"] == 0
        assert params["limit"] == 100


class TestQueryAssigneeByName:
    """Test that query_assignee_by_name builds correct API requests."""

    def test_uses_search_endpoint_with_q_param(self, client):
        """Verify /search endpoint and q parameter with quoted phrase."""
        client._make_request = MagicMock(return_value={"patentFileWrapperDataBag": []})

        client.query_assignee_by_name("Acme Corp")

        client._make_request.assert_called_once()
        args, kwargs = client._make_request.call_args
        assert args[0] == "/search"
        assert kwargs["method"] == "GET"
        params = kwargs["params"]
        assert params["q"] == 'assignees.assigneeName:"Acme Corp"'

    def test_quotes_company_name_with_special_characters(self, client):
        """Company names with commas/periods are quoted for phrase matching."""
        client._make_request = MagicMock(return_value={"patentFileWrapperDataBag": []})

        client.query_assignee_by_name("AERODYNE RESEARCH, INC.")

        params = client._make_request.call_args[1]["params"]
        assert params["q"] == 'assignees.assigneeName:"AERODYNE RESEARCH, INC."'


class TestEscapeLuceneQuery:
    """Test Lucene special character escaping."""

    def test_escapes_common_special_chars(self):
        assert PatentsViewClient._escape_lucene_query("a+b") == r"a\+b"
        assert PatentsViewClient._escape_lucene_query("a:b") == r"a\:b"
        assert PatentsViewClient._escape_lucene_query('a"b') == r'a\"b'

    def test_leaves_plain_text_unchanged(self):
        assert PatentsViewClient._escape_lucene_query("Acme Corp") == "Acme Corp"

    def test_does_not_escape_non_special_chars(self):
        # Commas and periods are not Lucene special characters
        result = PatentsViewClient._escape_lucene_query("Verinomics, Inc.")
        assert result == "Verinomics, Inc."

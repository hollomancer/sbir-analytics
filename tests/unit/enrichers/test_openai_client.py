"""Tests for OpenAI client."""

from unittest.mock import Mock

import pytest

from sbir_etl.enrichers.openai_client import OpenAIClient, WebSearchResult

pytestmark = pytest.mark.fast


class TestOpenAIClient:
    def test_chat_success(self):
        mock_http = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "  Hello world  "}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_resp.raise_for_status = Mock()
        mock_http.request.return_value = mock_resp

        client = OpenAIClient(api_key="test-key")
        client._client = mock_http
        result = client.chat("system", "user")

        assert result == "Hello world"

    def test_chat_failure_returns_none(self):
        import httpx

        mock_http = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=Mock(), response=mock_resp
        )
        mock_http.request.return_value = mock_resp

        client = OpenAIClient(api_key="test-key", max_concurrent=1)
        client._client = mock_http
        # Will retry and eventually return None
        result = client.chat("sys", "usr")
        assert result is None

    def test_web_search_success(self):
        mock_http = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Acme Corp is a defense tech company.",
                            "annotations": [
                                {"url": "https://example.com/1"},
                                {"url": "https://example.com/2"},
                            ],
                        }
                    ],
                }
            ]
        }
        mock_resp.raise_for_status = Mock()
        mock_http.request.return_value = mock_resp

        client = OpenAIClient(api_key="test-key")
        client._client = mock_http
        result = client.web_search("Acme Corp SBIR")

        assert result is not None
        assert "Acme Corp" in result.summary
        assert len(result.source_urls) == 2

    def test_web_search_empty_returns_none(self):
        mock_http = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"output": []}
        mock_resp.raise_for_status = Mock()
        mock_http.request.return_value = mock_resp

        client = OpenAIClient(api_key="test-key")
        client._client = mock_http
        assert client.web_search("query") is None

    def test_context_manager(self):
        with OpenAIClient(api_key="test") as client:
            assert hasattr(client, "chat")
            assert hasattr(client, "web_search")

    def test_web_search_result_fields(self):
        r = WebSearchResult(summary="test", source_urls=["url1"])
        assert r.summary == "test"
        assert r.source_urls == ["url1"]

"""Tests for SBIRQueryService."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sbir_rag.config import LightRAGConfig
from sbir_rag.query_service import SBIRQueryService


@pytest.fixture
def config():
    return LightRAGConfig(
        default_retrieval_mode="hybrid",
        retrieval_top_k=5,
    )


@pytest.fixture
def service(config):
    return SBIRQueryService(config)


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class TestSBIRQueryService:
    """Tests for the query service dispatch and formatting."""

    def test_query_dispatches_to_default_mode(self, service, config):
        """Default mode from config is used when none specified."""
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "hybrid result"
        service._rag = mock_rag

        result = _run(service.query("test query"))

        mock_rag.aquery.assert_called_once()
        call_args = mock_rag.aquery.call_args
        assert call_args[1]["param"]["mode"] == "hybrid"

    def test_query_dispatches_to_explicit_mode(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "naive result"
        service._rag = mock_rag

        result = _run(service.query("test", mode="naive"))

        call_args = mock_rag.aquery.call_args
        assert call_args[1]["param"]["mode"] == "naive"

    def test_query_invalid_mode_raises(self, service):
        with pytest.raises(ValueError, match="Unknown retrieval mode"):
            _run(service.query("test", mode="invalid"))

    def test_semantic_search_returns_list(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "result text"
        service._rag = mock_rag

        result = _run(service.semantic_search("quantum computing"))

        assert isinstance(result, list)
        assert result[0]["mode"] == "naive"
        assert result[0]["content"] == "result text"

    def test_entity_neighborhood_returns_list(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = [
            {"text": "result 1"},
            {"text": "result 2"},
        ]
        service._rag = mock_rag

        result = _run(service.entity_neighborhood("autonomous vehicles"))

        assert isinstance(result, list)
        assert len(result) == 2

    def test_thematic_summary_returns_string(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "Thematic summary of quantum research..."
        service._rag = mock_rag

        result = _run(service.thematic_summary("quantum research themes"))

        assert isinstance(result, str)
        assert "quantum" in result.lower()

    def test_hybrid_query_returns_dict(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "combined result"
        service._rag = mock_rag

        result = _run(service.hybrid_query("counter-UAS detection"))

        assert isinstance(result, dict)
        assert result["mode"] == "hybrid"
        assert result["query"] == "counter-UAS detection"

    def test_top_k_override(self, service):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "result"
        service._rag = mock_rag

        _run(service.semantic_search("test", top_k=20))

        call_args = mock_rag.aquery.call_args
        assert call_args[1]["param"]["top_k"] == 20

    def test_top_k_defaults_to_config(self, service, config):
        mock_rag = AsyncMock()
        mock_rag.aquery.return_value = "result"
        service._rag = mock_rag

        _run(service.semantic_search("test"))

        call_args = mock_rag.aquery.call_args
        assert call_args[1]["param"]["top_k"] == config.retrieval_top_k

    def test_format_results_string(self):
        results = SBIRQueryService._format_results("plain text", mode="naive")
        assert len(results) == 1
        assert results[0]["content"] == "plain text"
        assert results[0]["mode"] == "naive"

    def test_format_results_list_of_dicts(self):
        results = SBIRQueryService._format_results(
            [{"text": "a"}, {"text": "b"}], mode="local"
        )
        assert len(results) == 2
        assert results[0]["text"] == "a"
        assert results[0]["mode"] == "local"

    def test_format_results_list_of_strings(self):
        results = SBIRQueryService._format_results(
            ["result 1", "result 2"], mode="naive"
        )
        assert len(results) == 2
        assert results[0]["content"] == "result 1"

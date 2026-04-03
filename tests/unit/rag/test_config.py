"""Tests for LightRAGConfig."""

import os
from unittest.mock import patch

import pytest

from sbir_rag.config import LightRAGConfig


class TestLightRAGConfigDefaults:
    """Test default configuration values."""

    def test_defaults(self):
        cfg = LightRAGConfig()
        assert cfg.enabled is False
        assert cfg.workspace == "sbir"
        assert cfg.embedding_dim == 768
        assert cfg.embedding_model == "nomic-ai/modernbert-embed-base"
        assert cfg.llm_model == "claude-haiku-4-5-20251001"
        assert cfg.chunk_size == 1200
        assert cfg.chunk_overlap == 100
        assert cfg.community_algorithm == "leiden"
        assert cfg.max_community_levels == 3
        assert cfg.default_retrieval_mode == "hybrid"
        assert cfg.retrieval_top_k == 10
        assert cfg.similarity_threshold == 0.75
        assert cfg.neo4j_database == "neo4j"

    def test_neo4j_env_var_resolution(self):
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://prod:7687",
                "NEO4J_USER": "admin",
                "NEO4J_PASSWORD": "secret",
            },
        ):
            cfg = LightRAGConfig()
            assert cfg.neo4j_uri == "bolt://prod:7687"
            assert cfg.neo4j_username == "admin"
            assert cfg.neo4j_password == "secret"

    def test_explicit_values_override_env(self):
        with patch.dict(os.environ, {"NEO4J_URI": "bolt://env:7687"}):
            cfg = LightRAGConfig(neo4j_uri="bolt://explicit:7687")
            assert cfg.neo4j_uri == "bolt://explicit:7687"


class TestLightRAGConfigValidation:
    """Test Pydantic validation rules."""

    def test_chunk_size_minimum(self):
        with pytest.raises(Exception):
            LightRAGConfig(chunk_size=50)

    def test_similarity_threshold_bounds(self):
        with pytest.raises(Exception):
            LightRAGConfig(similarity_threshold=1.5)

    def test_temperature_bounds(self):
        with pytest.raises(Exception):
            LightRAGConfig(llm_temperature=-0.1)

    def test_community_levels_minimum(self):
        with pytest.raises(Exception):
            LightRAGConfig(max_community_levels=0)


class TestLightRAGConfigFromYAML:
    """Test construction from YAML config dict."""

    def test_from_yaml_config_basic(self):
        yaml_config = {
            "lightrag": {
                "enabled": True,
                "workspace": "test",
            }
        }
        cfg = LightRAGConfig.from_yaml_config(yaml_config)
        assert cfg.enabled is True
        assert cfg.workspace == "test"

    def test_from_yaml_config_nested_sections(self):
        yaml_config = {
            "lightrag": {
                "enabled": True,
                "llm": {
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 2048,
                    "temperature": 0.5,
                },
                "chunking": {
                    "chunk_size": 2000,
                    "chunk_overlap": 200,
                },
                "community_detection": {
                    "algorithm": "leiden",
                    "max_levels": 5,
                    "resolution": 1.5,
                },
                "retrieval": {
                    "default_mode": "local",
                    "top_k": 20,
                    "similarity_threshold": 0.80,
                },
            }
        }
        cfg = LightRAGConfig.from_yaml_config(yaml_config)
        assert cfg.llm_model == "claude-sonnet-4-6"
        assert cfg.llm_max_tokens == 2048
        assert cfg.llm_temperature == 0.5
        assert cfg.chunk_size == 2000
        assert cfg.chunk_overlap == 200
        assert cfg.max_community_levels == 5
        assert cfg.community_resolution == 1.5
        assert cfg.default_retrieval_mode == "local"
        assert cfg.retrieval_top_k == 20
        assert cfg.similarity_threshold == 0.80

    def test_from_yaml_config_empty(self):
        cfg = LightRAGConfig.from_yaml_config({})
        assert cfg.enabled is False
        assert cfg.workspace == "sbir"

    def test_from_yaml_config_partial(self):
        yaml_config = {
            "lightrag": {
                "enabled": True,
                "llm": {
                    "model": "gpt-4o-mini",
                },
            }
        }
        cfg = LightRAGConfig.from_yaml_config(yaml_config)
        assert cfg.llm_model == "gpt-4o-mini"
        # Other fields should have defaults
        assert cfg.chunk_size == 1200

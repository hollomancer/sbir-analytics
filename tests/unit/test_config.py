"""Unit tests for configuration management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.config.loader import (
    ConfigurationError,
    _apply_env_overrides,
    _convert_env_value,
    _deep_merge_dicts,
    get_config,
    load_config_from_files,
    reload_config,
)
from src.config.schemas import PipelineConfig


class TestDeepMergeDicts:
    """Test deep dictionary merging functionality."""

    def test_merge_empty_dicts(self):
        """Test merging empty dictionaries."""
        base = {}
        override = {}
        result = _deep_merge_dicts(base, override)
        assert result == {}

    def test_merge_simple_keys(self):
        """Test merging dictionaries with simple keys."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge_dicts(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self):
        """Test merging nested dictionaries."""
        base = {"data": {"quality": {"threshold": 0.8}}}
        override = {"data": {"quality": {"enabled": True}}}
        result = _deep_merge_dicts(base, override)
        expected = {
            "data": {
                "quality": {
                    "threshold": 0.8,
                    "enabled": True
                }
            }
        }
        assert result == expected

    def test_override_replaces_non_dict(self):
        """Test that override completely replaces non-dict values."""
        base = {"setting": {"nested": "value"}}
        override = {"setting": "new_value"}
        result = _deep_merge_dicts(base, override)
        assert result == {"setting": "new_value"}


class TestConvertEnvValue:
    """Test environment variable value conversion."""

    def test_convert_boolean_true(self):
        """Test boolean true conversion."""
        assert _convert_env_value("true") is True
        assert _convert_env_value("True") is True
        assert _convert_env_value("TRUE") is True

    def test_convert_boolean_false(self):
        """Test boolean false conversion."""
        assert _convert_env_value("false") is False
        assert _convert_env_value("False") is False
        assert _convert_env_value("FALSE") is False

    def test_convert_integer(self):
        """Test integer conversion."""
        assert _convert_env_value("42") == 42
        assert _convert_env_value("0") == 0
        assert _convert_env_value("-1") == -1

    def test_convert_float(self):
        """Test float conversion."""
        assert _convert_env_value("3.14") == 3.14
        assert _convert_env_value("0.0") == 0.0

    def test_convert_string(self):
        """Test string passthrough."""
        assert _convert_env_value("hello") == "hello"
        assert _convert_env_value("123abc") == "123abc"


class TestApplyEnvOverrides:
    """Test environment variable override application."""

    def test_no_env_vars(self):
        """Test with no environment variables."""
        config = {"pipeline": {"name": "test"}}
        result = _apply_env_overrides(config)
        assert result == config

    @patch.dict(os.environ, {"SBIR_ETL__PIPELINE__NAME": "overridden"})
    def test_simple_override(self):
        """Test simple key override."""
        config = {"pipeline": {"name": "original"}}
        result = _apply_env_overrides(config)
        assert result["pipeline"]["name"] == "overridden"

    @patch.dict(os.environ, {"SBIR_ETL__DATA_QUALITY__COMPLETENESS__THRESHOLD": "0.95"})
    def test_nested_override(self):
        """Test nested key override."""
        config = {"data_quality": {"completeness": {"threshold": 0.8}}}
        result = _apply_env_overrides(config)
        assert result["data_quality"]["completeness"]["threshold"] == 0.95

    @patch.dict(os.environ, {"SBIR_ETL__NEO4J__BATCH_SIZE": "5000"})
    def test_integer_override(self):
        """Test integer type conversion."""
        config = {"neo4j": {"batch_size": 1000}}
        result = _apply_env_overrides(config)
        assert result["neo4j"]["batch_size"] == 5000

    @patch.dict(os.environ, {"SBIR_ETL__LOGGING__ENABLED": "true"})
    def test_boolean_override(self):
        """Test boolean type conversion."""
        config = {"logging": {"enabled": False}}
        result = _apply_env_overrides(config)
        assert result["logging"]["enabled"] is True


class TestLoadConfigFromFiles:
    """Test configuration loading from YAML files."""

    def test_load_base_only(self):
        """Test loading base configuration only."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            base_file = config_dir / "base.yaml"
            base_file.write_text("pipeline:\n  name: test\n")

            result = load_config_from_files(Path.cwd(), config_dir=config_dir)
            assert result == {"pipeline": {"name": "test"}}

    def test_load_with_environment_override(self):
        """Test loading with environment-specific overrides."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Base config
            base_file = config_dir / "base.yaml"
            base_file.write_text("pipeline:\n  name: base\nsetting: base_value\n")

            # Dev config
            dev_file = config_dir / "dev.yaml"
            dev_file.write_text("pipeline:\n  name: dev\nsetting: dev_value\n")

            result = load_config_from_files(
                Path.cwd(), environment="dev", config_dir=config_dir
            )
            assert result == {
                "pipeline": {"name": "dev"},
                "setting": "dev_value"
            }

    def test_missing_base_file(self):
        """Test error when base file is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            with pytest.raises(ConfigurationError, match="Base configuration file not found"):
                load_config_from_files(Path.cwd(), config_dir=config_dir)

    def test_invalid_yaml(self):
        """Test error with invalid YAML."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            base_file = config_dir / "base.yaml"
            base_file.write_text("invalid: yaml: content: [\n")

            with pytest.raises(ConfigurationError, match="Failed to parse base config"):
                load_config_from_files(Path.cwd(), config_dir=config_dir)


class TestGetConfig:
    """Test main configuration loading function."""

    def test_get_config_success(self):
        """Test successful configuration loading."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create base config
            base_file = config_dir / "base.yaml"
            base_config = {
                "pipeline": {"name": "test", "version": "1.0.0", "environment": "test"},
                "data_quality": {"completeness": {"award_id": 1.0}},
                "neo4j": {"batch_size": 1000},
            }
            base_file.write_text(yaml.dump(base_config))

            result = get_config(config_dir=config_dir, apply_env_overrides_flag=False)
            assert isinstance(result, PipelineConfig)
            assert result.pipeline["name"] == "test"

    def test_get_config_validation_error(self):
        """Test configuration validation error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create invalid config
            base_file = config_dir / "base.yaml"
            base_file.write_text("data_quality:\n  completeness:\n    award_id: 1.5\n")  # Invalid percentage

            with pytest.raises(ConfigurationError, match="Configuration validation failed"):
                get_config(config_dir=config_dir, apply_env_overrides_flag=False)

    def test_config_caching(self):
        """Test that configuration is cached."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create base config
            base_file = config_dir / "base.yaml"
            base_config = {
                "pipeline": {"name": "test", "version": "1.0.0", "environment": "test"},
            }
            base_file.write_text(yaml.dump(base_config))

            # First call
            config1 = get_config(config_dir=config_dir, apply_env_overrides_flag=False)

            # Modify file
            base_file.write_text(yaml.dump({"pipeline": {"name": "modified"}}))

            # Second call should return cached result
            config2 = get_config(config_dir=config_dir, apply_env_overrides_flag=False)

            assert config1.pipeline["name"] == config2.pipeline["name"] == "test"

    def test_config_reload(self):
        """Test configuration cache clearing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)

            # Create base config
            base_file = config_dir / "base.yaml"
            base_config = {
                "pipeline": {"name": "test", "version": "1.0.0", "environment": "test"},
            }
            base_file.write_text(yaml.dump(base_config))

            # First call
            config1 = get_config(config_dir=config_dir, apply_env_overrides_flag=False)

            # Modify file
            base_file.write_text(yaml.dump({"pipeline": {"name": "modified", "version": "1.0.0", "environment": "test"}}))

            # Reload and get new config
            reload_config()
            config2 = get_config(config_dir=config_dir, apply_env_overrides_flag=False)

            assert config1.pipeline["name"] == "test"
            assert config2.pipeline["name"] == "modified"
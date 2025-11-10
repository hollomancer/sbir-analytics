"""Tests for configuration loader."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

import yaml

from src.config.loader import (
    _deep_merge_dicts,
    _convert_env_value,
    _apply_env_overrides,
    load_config_from_files,
    get_config,
    reload_config,
)
from src.config.schemas import PipelineConfig
from src.exceptions import ConfigurationError


class TestDeepMergeDicts:
    """Tests for _deep_merge_dicts function."""

    def test_merge_flat_dicts(self):
        """Test merging flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge_dicts(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self):
        """Test merging nested dictionaries."""
        base = {"outer": {"inner1": 1, "inner2": 2}}
        override = {"outer": {"inner2": 3, "inner3": 4}}
        result = _deep_merge_dicts(base, override)
        assert result == {"outer": {"inner1": 1, "inner2": 3, "inner3": 4}}

    def test_merge_deeply_nested_dicts(self):
        """Test merging deeply nested dictionaries."""
        base = {"level1": {"level2": {"level3": {"value": 1}}}}
        override = {"level1": {"level2": {"level3": {"value": 2, "new": 3}}}}
        result = _deep_merge_dicts(base, override)
        assert result == {"level1": {"level2": {"level3": {"value": 2, "new": 3}}}}

    def test_merge_override_non_dict_with_dict(self):
        """Test merging where override replaces non-dict with dict."""
        base = {"key": "string_value"}
        override = {"key": {"nested": "dict"}}
        result = _deep_merge_dicts(base, override)
        assert result == {"key": {"nested": "dict"}}

    def test_merge_override_dict_with_non_dict(self):
        """Test merging where override replaces dict with non-dict."""
        base = {"key": {"nested": "dict"}}
        override = {"key": "string_value"}
        result = _deep_merge_dicts(base, override)
        assert result == {"key": "string_value"}

    def test_merge_empty_base(self):
        """Test merging with empty base dictionary."""
        base = {}
        override = {"a": 1, "b": 2}
        result = _deep_merge_dicts(base, override)
        assert result == {"a": 1, "b": 2}

    def test_merge_empty_override(self):
        """Test merging with empty override dictionary."""
        base = {"a": 1, "b": 2}
        override = {}
        result = _deep_merge_dicts(base, override)
        assert result == {"a": 1, "b": 2}

    def test_merge_preserves_base(self):
        """Test merging does not mutate base dictionary."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}}
        result = _deep_merge_dicts(base, override)
        assert base == {"a": 1, "b": {"c": 2}}  # Base unchanged


class TestConvertEnvValue:
    """Tests for _convert_env_value function."""

    def test_convert_boolean_true(self):
        """Test converting 'true' string to boolean."""
        assert _convert_env_value("true") is True
        assert _convert_env_value("True") is True
        assert _convert_env_value("TRUE") is True

    def test_convert_boolean_false(self):
        """Test converting 'false' string to boolean."""
        assert _convert_env_value("false") is False
        assert _convert_env_value("False") is False
        assert _convert_env_value("FALSE") is False

    def test_convert_integer(self):
        """Test converting integer strings."""
        assert _convert_env_value("42") == 42
        assert _convert_env_value("0") == 0
        assert _convert_env_value("-10") == -10

    def test_convert_float(self):
        """Test converting float strings."""
        assert _convert_env_value("3.14") == 3.14
        assert _convert_env_value("0.5") == 0.5
        assert _convert_env_value("-2.5") == -2.5

    def test_convert_string(self):
        """Test strings that cannot be converted remain strings."""
        assert _convert_env_value("hello") == "hello"
        assert _convert_env_value("bolt://localhost:7687") == "bolt://localhost:7687"
        assert _convert_env_value("") == ""

    def test_convert_numeric_string_prefers_int(self):
        """Test numeric strings are converted to int before float."""
        result = _convert_env_value("100")
        assert result == 100
        assert isinstance(result, int)


class TestApplyEnvOverrides:
    """Tests for _apply_env_overrides function."""

    def test_apply_single_level_override(self):
        """Test applying single-level environment override."""
        config = {"logging": {"level": "INFO"}}
        with patch.dict(os.environ, {"SBIR_ETL__LOGGING__LEVEL": "DEBUG"}):
            result = _apply_env_overrides(config)
        assert result["logging"]["level"] == "DEBUG"

    def test_apply_multi_level_override(self):
        """Test applying multi-level environment override."""
        config = {"neo4j": {"connection": {"timeout": 30}}}
        with patch.dict(os.environ, {"SBIR_ETL__NEO4J__CONNECTION__TIMEOUT": "60"}):
            result = _apply_env_overrides(config)
        assert result["neo4j"]["connection"]["timeout"] == 60

    def test_apply_creates_missing_keys(self):
        """Test environment override creates missing nested keys."""
        config = {}
        with patch.dict(os.environ, {"SBIR_ETL__NEW__NESTED__KEY": "value"}):
            result = _apply_env_overrides(config)
        assert result["new"]["nested"]["key"] == "value"

    def test_apply_converts_boolean(self):
        """Test environment override converts boolean strings."""
        config = {"feature": {"enabled": False}}
        with patch.dict(os.environ, {"SBIR_ETL__FEATURE__ENABLED": "true"}):
            result = _apply_env_overrides(config)
        assert result["feature"]["enabled"] is True

    def test_apply_converts_numeric(self):
        """Test environment override converts numeric strings."""
        config = {"batch": {"size": 1000}}
        with patch.dict(os.environ, {"SBIR_ETL__BATCH__SIZE": "5000"}):
            result = _apply_env_overrides(config)
        assert result["batch"]["size"] == 5000

    def test_apply_ignores_non_prefixed_vars(self):
        """Test environment override ignores non-prefixed variables."""
        config = {"key": "original"}
        with patch.dict(os.environ, {"OTHER__KEY": "value"}):
            result = _apply_env_overrides(config)
        assert result == {"key": "original"}

    def test_apply_custom_prefix(self):
        """Test environment override with custom prefix."""
        config = {}
        with patch.dict(os.environ, {"CUSTOM__KEY": "value"}):
            result = _apply_env_overrides(config, prefix="CUSTOM")
        assert result["key"] == "value"

    def test_apply_replaces_non_dict_with_dict(self):
        """Test environment override creates dict when path component is non-dict."""
        config = {"key": "string_value"}
        with patch.dict(os.environ, {"SBIR_ETL__KEY__NESTED": "value"}):
            result = _apply_env_overrides(config)
        assert result["key"] == {"nested": "value"}

    def test_apply_preserves_original(self):
        """Test environment override does not mutate original config."""
        config = {"key": "original"}
        with patch.dict(os.environ, {"SBIR_ETL__KEY": "modified"}):
            result = _apply_env_overrides(config)
        assert config["key"] == "original"  # Original unchanged
        assert result["key"] == "modified"


class TestLoadConfigFromFiles:
    """Tests for load_config_from_files function."""

    def test_load_base_config_only(self):
        """Test loading base configuration without environment override."""
        base_content = {"logging": {"level": "INFO"}, "neo4j": {"uri": "bolt://localhost:7687"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"
            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            result = load_config_from_files(
                base_path=Path.cwd(),
                environment=None,
                config_dir=config_dir,
            )

            assert result["logging"]["level"] == "INFO"
            assert result["neo4j"]["uri"] == "bolt://localhost:7687"

    def test_load_with_environment_override(self):
        """Test loading with environment-specific override."""
        base_content = {"logging": {"level": "INFO"}, "feature": {"enabled": False}}
        prod_content = {"logging": {"level": "ERROR"}, "feature": {"enabled": True}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"
            prod_file = config_dir / "production.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)
            with open(prod_file, "w") as f:
                yaml.dump(prod_content, f)

            result = load_config_from_files(
                base_path=Path.cwd(),
                environment="production",
                config_dir=config_dir,
            )

            assert result["logging"]["level"] == "ERROR"
            assert result["feature"]["enabled"] is True

    def test_load_missing_base_file_raises_error(self):
        """Test loading with missing base.yaml raises ConfigurationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)

            with pytest.raises(ConfigurationError) as exc_info:
                load_config_from_files(
                    base_path=Path.cwd(),
                    environment=None,
                    config_dir=config_dir,
                )

            assert "Base configuration file not found" in str(exc_info.value)

    def test_load_missing_environment_file_uses_base(self):
        """Test loading with missing environment file uses base only."""
        base_content = {"logging": {"level": "INFO"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            # Request 'development' environment but file doesn't exist
            result = load_config_from_files(
                base_path=Path.cwd(),
                environment="development",
                config_dir=config_dir,
            )

            # Should still load base config without error
            assert result["logging"]["level"] == "INFO"

    def test_load_invalid_yaml_raises_error(self):
        """Test loading invalid YAML raises ConfigurationError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                f.write("invalid: yaml: content: :[")

            with pytest.raises(ConfigurationError) as exc_info:
                load_config_from_files(
                    base_path=Path.cwd(),
                    environment=None,
                    config_dir=config_dir,
                )

            assert "Failed to parse base config" in str(exc_info.value)

    def test_load_empty_yaml_file(self):
        """Test loading empty YAML file returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                f.write("")  # Empty file

            result = load_config_from_files(
                base_path=Path.cwd(),
                environment=None,
                config_dir=config_dir,
            )

            assert result == {}

    def test_load_merges_nested_configs(self):
        """Test loading merges nested configurations correctly."""
        base_content = {
            "neo4j": {
                "uri": "bolt://localhost:7687",
                "batch_size": 1000,
                "timeout": 30,
            }
        }
        env_content = {
            "neo4j": {
                "uri": "bolt://prod:7687",
                "batch_size": 5000,
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"
            env_file = config_dir / "prod.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)
            with open(env_file, "w") as f:
                yaml.dump(env_content, f)

            result = load_config_from_files(
                base_path=Path.cwd(),
                environment="prod",
                config_dir=config_dir,
            )

            # Override values should be updated
            assert result["neo4j"]["uri"] == "bolt://prod:7687"
            assert result["neo4j"]["batch_size"] == 5000
            # Non-overridden values should be preserved
            assert result["neo4j"]["timeout"] == 30


class TestGetConfig:
    """Tests for get_config function."""

    def setup_method(self):
        """Clear config cache before each test."""
        reload_config()

    def test_get_config_returns_pipeline_config(self):
        """Test get_config returns PipelineConfig instance."""
        base_content = {
            "pipeline": {"name": "test", "version": "1.0"},
            "logging": {"level": "INFO"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            config = get_config(environment=None, config_dir=config_dir)

            assert isinstance(config, PipelineConfig)
            assert config.pipeline["name"] == "test"

    def test_get_config_applies_env_overrides_by_default(self):
        """Test get_config applies environment variable overrides."""
        base_content = {"logging": {"level": "INFO"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            with patch.dict(os.environ, {"SBIR_ETL__LOGGING__LEVEL": "DEBUG"}):
                reload_config()  # Clear cache
                config = get_config(environment=None, config_dir=config_dir)

            assert config.logging.level == "DEBUG"

    def test_get_config_skips_env_overrides_when_disabled(self):
        """Test get_config skips env overrides when flag is False."""
        base_content = {"logging": {"level": "INFO"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            with patch.dict(os.environ, {"SBIR_ETL__LOGGING__LEVEL": "DEBUG"}):
                reload_config()  # Clear cache
                config = get_config(
                    environment=None,
                    config_dir=config_dir,
                    apply_env_overrides_flag=False,
                )

            # Should use base config level, not env override
            assert config.logging.level == "INFO"

    def test_get_config_applies_neo4j_defaults(self):
        """Test get_config applies Neo4j runtime defaults."""
        base_content = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            reload_config()  # Clear cache
            config = get_config(environment="development", config_dir=config_dir)

            # Should have default Neo4j settings
            assert config.neo4j.uri == "bolt://localhost:7687"
            assert config.neo4j.batch_size == 1000

    def test_get_config_uses_production_defaults(self):
        """Test get_config uses production defaults for prod environment."""
        base_content = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            reload_config()  # Clear cache
            config = get_config(environment="production", config_dir=config_dir)

            # Production should use different default URI
            assert config.neo4j.uri == "bolt://prod-neo4j:7687"

    def test_get_config_respects_explicit_neo4j_uri_env(self):
        """Test get_config respects explicit NEO4J_URI environment variable."""
        base_content = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            with patch.dict(os.environ, {"NEO4J_URI": "bolt://custom:7687"}):
                reload_config()  # Clear cache
                config = get_config(environment="development", config_dir=config_dir)

            assert config.neo4j.uri == "bolt://custom:7687"

    def test_get_config_handles_legacy_loading_neo4j(self):
        """Test get_config handles legacy 'loading.neo4j' structure."""
        base_content = {
            "loading": {
                "neo4j": {
                    "uri": "bolt://legacy:7687",
                    "batch_size": 2000,
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            reload_config()  # Clear cache
            config = get_config(environment=None, config_dir=config_dir)

            # Legacy structure should be mapped to top-level neo4j
            assert config.neo4j.uri == "bolt://legacy:7687"
            assert config.neo4j.batch_size == 2000

    def test_get_config_is_cached(self):
        """Test get_config caches results."""
        base_content = {"logging": {"level": "INFO"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            reload_config()  # Clear cache
            config1 = get_config(environment=None, config_dir=config_dir)
            config2 = get_config(environment=None, config_dir=config_dir)

            # Should return same cached instance
            assert config1 is config2

    def test_get_config_validation_error_raises_configuration_error(self):
        """Test get_config raises ConfigurationError on validation failure."""
        base_content = {
            "data_quality": {
                "sbir_awards": {
                    "pass_rate_threshold": 1.5  # Invalid: > 1.0
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            reload_config()  # Clear cache
            with pytest.raises(ConfigurationError) as exc_info:
                get_config(environment=None, config_dir=config_dir)

            assert "Configuration validation failed" in str(exc_info.value)


class TestReloadConfig:
    """Tests for reload_config function."""

    def test_reload_clears_cache(self):
        """Test reload_config clears the configuration cache."""
        base_content = {"logging": {"level": "INFO"}}

        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            with open(base_file, "w") as f:
                yaml.dump(base_content, f)

            # Get initial config
            reload_config()
            config1 = get_config(environment=None, config_dir=config_dir)

            # Reload should clear cache
            reload_config()

            # Get config again - should be new instance
            config2 = get_config(environment=None, config_dir=config_dir)

            # Different instances (cache was cleared)
            assert config1 is not config2

    def test_reload_allows_config_changes(self):
        """Test reload_config allows configuration changes to take effect."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            base_file = config_dir / "base.yaml"

            # Write initial config
            with open(base_file, "w") as f:
                yaml.dump({"logging": {"level": "INFO"}}, f)

            reload_config()
            config1 = get_config(environment=None, config_dir=config_dir)
            assert config1.logging.level == "INFO"

            # Update config file
            with open(base_file, "w") as f:
                yaml.dump({"logging": {"level": "DEBUG"}}, f)

            # Without reload, would still see cached value
            # After reload, should see new value
            reload_config()
            config2 = get_config(environment=None, config_dir=config_dir)
            assert config2.logging.level == "DEBUG"

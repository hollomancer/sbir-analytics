"""Unit tests for configuration accessor utilities."""

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.fast

from src.utils.config_accessor import ConfigAccessor


class TestConfigAccessor:
    """Tests for ConfigAccessor utility class."""

    def test_get_nested_with_attribute_access(self):
        """Test get_nested with attribute access."""
        # Create mock config with nested attributes
        config = MagicMock()
        config.ml = MagicMock()
        config.ml.paecter = MagicMock()
        config.ml.paecter.use_local = True
        config.ml.paecter.batch_size = 32

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local")
        assert result is True

        result = ConfigAccessor.get_nested(config, "ml.paecter.batch_size")
        assert result == 32

    def test_get_nested_with_dict_access(self):
        """Test get_nested with dictionary-like access."""
        config = {
            "ml": {
                "paecter": {
                    "use_local": False,
                    "batch_size": 64,
                }
            }
        }

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local")
        assert result is False

        result = ConfigAccessor.get_nested(config, "ml.paecter.batch_size")
        assert result == 64

    def test_get_nested_returns_default_when_not_found(self):
        """Test get_nested returns default when path not found."""
        config = MagicMock()

        result = ConfigAccessor.get_nested(config, "nonexistent.path", default="default_value")
        assert result == "default_value"

    def test_get_nested_returns_default_when_none(self):
        """Test get_nested returns default when intermediate value is None."""
        config = MagicMock()
        config.ml = None

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local", default=False)
        assert result is False

    def test_get_nested_with_single_level(self):
        """Test get_nested with single-level path."""
        config = MagicMock()
        config.log_level = "DEBUG"

        result = ConfigAccessor.get_nested(config, "log_level")
        assert result == "DEBUG"

    def test_get_nested_with_empty_path(self):
        """Test get_nested with empty path."""
        config = MagicMock()

        result = ConfigAccessor.get_nested(config, "", default="default")
        assert result == "default"

    def test_get_nested_mixed_attribute_and_dict(self):
        """Test get_nested with mixed attribute and dict access."""
        config = MagicMock()
        config.ml = {"paecter": {"use_local": True}}

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local")
        assert result is True


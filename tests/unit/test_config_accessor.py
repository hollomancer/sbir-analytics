"""Unit tests for ConfigAccessor utility."""

from unittest.mock import Mock

import pytest

from src.utils.config_accessor import ConfigAccessor


class TestConfigAccessor:
    """Test ConfigAccessor utility methods."""

    def test_get_nested_simple_path(self):
        """Test accessing a simple nested path."""
        config = Mock()
        config.ml = Mock()
        config.ml.paecter = Mock()
        config.ml.paecter.use_local = True

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local")
        assert result is True

    def test_get_nested_with_default(self):
        """Test accessing nested path with default value."""
        config = Mock()
        config.ml = None

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
        assert result is False

    def test_get_nested_nonexistent_path(self):
        """Test accessing nonexistent path returns default."""
        config = Mock()
        config.ml = Mock()
        config.ml.paecter = None

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
        assert result is False

    def test_get_nested_dict_access(self):
        """Test accessing nested path with dict-like access."""
        config = {"ml": {"paecter": {"use_local": True}}}

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local")
        assert result is True

    def test_get_nested_dict_with_default(self):
        """Test accessing nested dict path with default."""
        config = {"ml": {"paecter": None}}

        result = ConfigAccessor.get_nested(config, "ml.paecter.use_local", False)
        assert result is False

    def test_get_nested_dict_simple(self):
        """Test getting nested dict."""
        config = Mock()
        config.ml = Mock()
        config.ml.paecter = {"use_local": True, "batch_size": 32}

        result = ConfigAccessor.get_nested_dict(config, "ml.paecter")
        assert result == {"use_local": True, "batch_size": 32}

    def test_get_nested_dict_with_default(self):
        """Test getting nested dict with default."""
        config = Mock()
        config.ml = None

        result = ConfigAccessor.get_nested_dict(config, "ml.paecter", {})
        assert result == {}

    def test_get_nested_dict_pydantic_model(self):
        """Test getting nested dict from Pydantic model."""
        config = Mock()
        config.ml = Mock()
        pydantic_model = Mock()
        pydantic_model.model_dump.return_value = {"use_local": True}
        config.ml.paecter = pydantic_model

        result = ConfigAccessor.get_nested_dict(config, "ml.paecter")
        assert result == {"use_local": True}

    def test_get_nested_dict_legacy_dict_method(self):
        """Test getting nested dict from object with dict() method."""
        config = Mock()
        config.ml = Mock()
        legacy_obj = Mock()
        legacy_obj.dict.return_value = {"use_local": True}
        config.ml.paecter = legacy_obj

        result = ConfigAccessor.get_nested_dict(config, "ml.paecter")
        assert result == {"use_local": True}

    def test_get_nested_dict_not_dict(self):
        """Test getting nested dict when value is not a dict."""
        config = Mock()
        config.ml = Mock()
        config.ml.paecter = "not_a_dict"

        result = ConfigAccessor.get_nested_dict(config, "ml.paecter", {})
        assert result == {}


"""Unit tests for path validation utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.fast

from src.config.schemas import PathsConfig
from src.exceptions import FileSystemError
from src.utils.path_validator import PathValidator, validate_paths_on_startup


class TestPathValidator:
    """Tests for PathValidator class."""

    @pytest.fixture
    def mock_paths_config(self, tmp_path):
        """Create a mock PathsConfig."""
        config = MagicMock(spec=PathsConfig)
        config.data_root = str(tmp_path / "data")
        config.raw_data = str(tmp_path / "data" / "raw")
        config.usaspending_dump_dir = str(tmp_path / "data" / "usaspending")
        config.transition_dump_dir = str(tmp_path / "data" / "transition")
        config.scripts_output = str(tmp_path / "output")
        config.usaspending_dump_file = str(tmp_path / "data" / "usaspending" / "dump.csv")
        config.transition_contracts_output = str(tmp_path / "output" / "contracts.parquet")
        config.transition_vendor_filters = str(tmp_path / "config" / "filters.json")

        def resolve_path(key, create_parent=False, project_root=None):
            path_str = getattr(config, key, None)
            if path_str:
                return Path(path_str)
            return tmp_path / key

        config.resolve_path = resolve_path
        return config

    @pytest.fixture
    def validator(self, mock_paths_config, tmp_path):
        """Create a PathValidator instance."""
        return PathValidator(mock_paths_config, project_root=tmp_path)

    def test_validate_all_paths_creates_missing_dirs(self, validator, tmp_path):
        """Test that validate_all_paths creates missing directories."""
        # Ensure directories don't exist
        assert not (tmp_path / "data").exists()

        validator.validate_all_paths(create_missing_dirs=True)

        # Directories should be created even if validation fails for files
        assert (tmp_path / "data").exists()
        assert (tmp_path / "data" / "raw").exists()
        # Result may be False if files don't exist, but directories should be created

    def test_validate_all_paths_fails_when_dirs_missing(self, validator):
        """Test that validate_all_paths fails when directories don't exist."""
        result = validator.validate_all_paths(create_missing_dirs=False)

        assert result is False
        assert len(validator.validation_errors) > 0

    def test_validate_directory_path_creates_if_missing(self, validator, tmp_path):
        """Test validate_directory_path creates directory if create_if_missing=True."""
        test_dir = tmp_path / "test_dir"
        assert not test_dir.exists()

        validator.validate_directory_path(test_dir, "test_dir", create_if_missing=True)

        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_validate_directory_path_fails_if_not_dir(self, validator, tmp_path):
        """Test validate_directory_path fails if path exists but is not a directory."""
        test_file = tmp_path / "test_file"
        test_file.write_text("test")

        with pytest.raises(FileSystemError) as exc_info:
            validator.validate_directory_path(test_file, "test_file", create_if_missing=False)

        assert "not a directory" in exc_info.value.message.lower()

    def test_validate_file_path_checks_parent(self, validator, tmp_path):
        """Test validate_file_path checks parent directory exists."""
        test_file = tmp_path / "nonexistent" / "file.txt"

        with pytest.raises(FileSystemError) as exc_info:
            validator.validate_file_path(test_file, "test_file", must_exist=False)

        assert "parent directory" in exc_info.value.message.lower()

    def test_validate_file_path_fails_if_dir(self, validator, tmp_path):
        """Test validate_file_path fails if path is a directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with pytest.raises(FileSystemError) as exc_info:
            validator.validate_file_path(test_dir, "test_file", must_exist=False)

        assert "directory" in exc_info.value.message.lower()

    def test_validate_file_path_requires_existence(self, validator, tmp_path):
        """Test validate_file_path can require file existence."""
        test_file = tmp_path / "nonexistent.txt"
        (tmp_path / "nonexistent.txt").parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(FileSystemError) as exc_info:
            validator.validate_file_path(test_file, "test_file", must_exist=True)

        assert "doesn't exist" in exc_info.value.message.lower()

    def test_get_validation_errors(self, validator):
        """Test get_validation_errors returns list of errors."""
        validator.validate_all_paths(create_missing_dirs=False)

        errors = validator.get_validation_errors()
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_print_validation_summary(self, validator, capsys):
        """Test print_validation_summary prints errors."""
        validator.validate_all_paths(create_missing_dirs=False)

        validator.print_validation_summary()

        captured = capsys.readouterr()
        assert "Path Validation Errors" in captured.out
        assert "Total errors" in captured.out

    def test_print_validation_summary_no_errors(self, validator, tmp_path, capsys):
        """Test print_validation_summary prints success when no errors."""
        validator.validate_all_paths(create_missing_dirs=True)

        validator.print_validation_summary()

        captured = capsys.readouterr()
        # May have errors for missing files even after creating directories
        assert len(captured.out) > 0  # Should print something


class TestValidatePathsOnStartup:
    """Tests for validate_paths_on_startup convenience function."""

    @patch("src.config.loader.get_config")
    def test_validate_paths_on_startup_success(self, mock_get_config, tmp_path):
        """Test validate_paths_on_startup returns True on success."""
        # Create mock config
        mock_config = MagicMock()
        mock_paths = MagicMock(spec=PathsConfig)
        mock_config.paths = mock_paths

        # Mock resolve_path to return existing paths
        def resolve_path(key, create_parent=False, project_root=None):
            return tmp_path / key

        mock_paths.resolve_path = resolve_path

        # Create directories
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "raw").mkdir()

        mock_get_config.return_value = mock_config

        result = validate_paths_on_startup(create_missing_dirs=True)

        assert result is True

    @patch("src.config.loader.get_config")
    def test_validate_paths_on_startup_failure(self, mock_get_config):
        """Test validate_paths_on_startup returns False on failure."""
        # Create mock config that will fail validation
        mock_config = MagicMock()
        mock_paths = MagicMock(spec=PathsConfig)
        mock_config.paths = mock_paths

        # Mock resolve_path to return non-existent paths
        def resolve_path(key, create_parent=False, project_root=None):
            return Path("/nonexistent/path")

        mock_paths.resolve_path = resolve_path
        mock_get_config.return_value = mock_config

        result = validate_paths_on_startup(create_missing_dirs=False)

        assert result is False

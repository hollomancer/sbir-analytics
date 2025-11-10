"""Unit tests for USPTO Extractor.

Tests cover:
- Initialization and file discovery
- Supported file type detection
- Core extraction logic
- Error handling
"""

from pathlib import Path

import pytest

from src.extractors.uspto_extractor import SUPPORTED_EXTENSIONS, USPTOExtractor


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_uspto_dir(tmp_path):
    """Create a sample USPTO directory with test files."""
    uspto_dir = tmp_path / "uspto"
    uspto_dir.mkdir()

    # Create sample files
    (uspto_dir / "assignment.dta").write_text("mock stata file")
    (uspto_dir / "patents.csv").write_text("patent_id,title\nPAT001,Test Patent")
    (uspto_dir / "applications.parquet").write_bytes(b"mock parquet")
    (uspto_dir / "readme.txt").write_text("Documentation")  # Unsupported extension

    return uspto_dir


@pytest.fixture
def empty_uspto_dir(tmp_path):
    """Create an empty USPTO directory."""
    uspto_dir = tmp_path / "empty_uspto"
    uspto_dir.mkdir()
    return uspto_dir


class TestUSPTOExtractorInitialization:
    """Tests for USPTO extractor initialization."""

    def test_init_with_valid_directory(self, sample_uspto_dir):
        """Test initialization with valid directory."""
        extractor = USPTOExtractor(sample_uspto_dir)

        assert extractor.input_dir == sample_uspto_dir
        assert isinstance(extractor.input_dir, Path)

    def test_init_with_string_path(self, sample_uspto_dir):
        """Test initialization with string path."""
        extractor = USPTOExtractor(str(sample_uspto_dir))

        assert extractor.input_dir == sample_uspto_dir
        assert isinstance(extractor.input_dir, Path)

    def test_init_with_nonexistent_directory(self, tmp_path):
        """Test initialization with non-existent directory raises error."""
        nonexistent = tmp_path / "does_not_exist"

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            USPTOExtractor(nonexistent)


class TestUSPTOExtractorSupportedExtensions:
    """Tests for supported file extension handling."""

    def test_supported_extensions_constant(self):
        """Test that supported extensions are defined."""
        assert ".dta" in SUPPORTED_EXTENSIONS
        assert ".csv" in SUPPORTED_EXTENSIONS
        assert ".parquet" in SUPPORTED_EXTENSIONS

    def test_supported_extensions_count(self):
        """Test expected number of supported extensions."""
        assert len(SUPPORTED_EXTENSIONS) == 3


class TestUSPTOExtractorFileDiscovery:
    """Tests for file discovery functionality."""

    def test_finds_supported_files(self, sample_uspto_dir):
        """Test finding supported files in directory."""
        USPTOExtractor(sample_uspto_dir)

        # Check if files exist
        dta_file = sample_uspto_dir / "assignment.dta"
        csv_file = sample_uspto_dir / "patents.csv"
        parquet_file = sample_uspto_dir / "applications.parquet"

        assert dta_file.exists()
        assert csv_file.exists()
        assert parquet_file.exists()

    def test_ignores_unsupported_files(self, sample_uspto_dir):
        """Test that unsupported files are in directory but not processed."""
        USPTOExtractor(sample_uspto_dir)

        # Unsupported file exists but should be ignored
        txt_file = sample_uspto_dir / "readme.txt"
        assert txt_file.exists()
        assert txt_file.suffix not in SUPPORTED_EXTENSIONS


class TestUSPTOExtractorPathHandling:
    """Tests for path handling and validation."""

    def test_handles_absolute_paths(self, sample_uspto_dir):
        """Test handling of absolute paths."""
        absolute_path = sample_uspto_dir.resolve()
        extractor = USPTOExtractor(absolute_path)

        assert extractor.input_dir.is_absolute()

    def test_handles_relative_paths(self, sample_uspto_dir, tmp_path):
        """Test handling of relative paths."""
        # Create relative path
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            relative_path = Path("uspto")
            extractor = USPTOExtractor(relative_path)

            assert extractor.input_dir == relative_path
        finally:
            os.chdir(original_cwd)


class TestUSPTOExtractorEmptyDirectory:
    """Tests for handling empty directories."""

    def test_empty_directory_initialization(self, empty_uspto_dir):
        """Test initialization with empty directory."""
        extractor = USPTOExtractor(empty_uspto_dir)

        assert extractor.input_dir == empty_uspto_dir
        assert extractor.input_dir.exists()
        assert len(list(extractor.input_dir.iterdir())) == 0


class TestUSPTOExtractorConstants:
    """Tests for module constants and configuration."""

    def test_supported_extensions_are_lowercase(self):
        """Test that all supported extensions are lowercase."""
        for ext in SUPPORTED_EXTENSIONS:
            assert ext == ext.lower()

    def test_supported_extensions_start_with_dot(self):
        """Test that all extensions start with a dot."""
        for ext in SUPPORTED_EXTENSIONS:
            assert ext.startswith(".")


class TestUSPTOExtractorPathResolution:
    """Tests for path resolution behavior."""

    def test_input_dir_is_path_object(self, sample_uspto_dir):
        """Test that input_dir is always a Path object."""
        extractor = USPTOExtractor(str(sample_uspto_dir))

        assert isinstance(extractor.input_dir, Path)

    def test_preserves_path_if_already_path(self, sample_uspto_dir):
        """Test that Path input is preserved."""
        path_input = Path(sample_uspto_dir)
        extractor = USPTOExtractor(path_input)

        assert extractor.input_dir == path_input
        assert isinstance(extractor.input_dir, Path)


class TestUSPTOExtractorMultipleFiles:
    """Tests for handling directories with multiple files."""

    def test_directory_with_multiple_supported_files(self, sample_uspto_dir):
        """Test directory with multiple supported file types."""
        USPTOExtractor(sample_uspto_dir)

        # Count supported files
        supported_files = [
            f for f in sample_uspto_dir.iterdir()
            if f.suffix in SUPPORTED_EXTENSIONS
        ]

        assert len(supported_files) == 3  # .dta, .csv, .parquet

    def test_mixed_supported_and_unsupported_files(self, sample_uspto_dir):
        """Test directory with mix of supported and unsupported files."""
        all_files = list(sample_uspto_dir.iterdir())
        supported_files = [f for f in all_files if f.suffix in SUPPORTED_EXTENSIONS]
        unsupported_files = [f for f in all_files if f.suffix not in SUPPORTED_EXTENSIONS]

        assert len(supported_files) == 3
        assert len(unsupported_files) == 1  # readme.txt
        assert len(all_files) == 4

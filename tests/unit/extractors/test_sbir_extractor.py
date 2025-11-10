"""Unit tests for SBIR DuckDB Extractor.

Tests cover:
- Initialization and configuration
- CSV import with various modes
- Data extraction methods
- Error handling
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.extractors.sbir import SbirDuckDBExtractor


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create a sample SBIR CSV file."""
    csv_file = tmp_path / "sbir_sample.csv"

    # Create a minimal SBIR CSV with header
    csv_content = """award_id,company_name,award_amount,award_year,agency
AWARD001,Test Company,100000,2023,DOD
AWARD002,Another Company,150000,2023,NASA
AWARD003,Third Company,200000,2024,NSF
"""
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def mock_duckdb_client():
    """Mock DuckDB client."""
    client = MagicMock()
    client.escape_identifier = Mock(side_effect=lambda x: f'"{x}"')
    client.import_csv = Mock(return_value=True)
    client.import_csv_incremental = Mock(return_value=True)
    client.create_table_from_df = Mock(return_value=True)
    client.get_table_info = Mock(return_value={
        "row_count": 3,
        "columns": [{"column_name": f"col{i}"} for i in range(42)]
    })
    client.query = Mock(return_value=Mock())
    return client


class TestSbirDuckDBExtractorInitialization:
    """Tests for SBIR extractor initialization."""

    @patch('src.extractors.sbir.DuckDBClient')
    def test_init_with_defaults(self, mock_duckdb_class, sample_csv_file):
        """Test initialization with default parameters."""
        mock_duckdb_class.return_value = MagicMock()

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)

        assert extractor.csv_path == sample_csv_file
        assert extractor.table_name == "sbir_awards"
        assert extractor._imported is False
        mock_duckdb_class.assert_called_once_with(database_path=":memory:")

    @patch('src.extractors.sbir.DuckDBClient')
    def test_init_with_custom_params(self, mock_duckdb_class, sample_csv_file, tmp_path):
        """Test initialization with custom parameters."""
        mock_duckdb_class.return_value = MagicMock()
        db_path = str(tmp_path / "test.duckdb")

        extractor = SbirDuckDBExtractor(
            csv_path=sample_csv_file,
            duckdb_path=db_path,
            table_name="custom_table"
        )

        assert extractor.csv_path == sample_csv_file
        assert extractor.table_name == "custom_table"
        mock_duckdb_class.assert_called_once_with(database_path=db_path)

    @patch('src.extractors.sbir.DuckDBClient')
    def test_init_with_string_path(self, mock_duckdb_class, tmp_path):
        """Test initialization with string path."""
        mock_duckdb_class.return_value = MagicMock()
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("header\ndata")

        extractor = SbirDuckDBExtractor(csv_path=str(csv_file))

        assert extractor.csv_path == csv_file
        assert isinstance(extractor.csv_path, Path)


class TestSbirDuckDBExtractorImport:
    """Tests for CSV import functionality."""

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_csv_bulk_mode(self, mock_duckdb_class, sample_csv_file, mock_duckdb_client):
        """Test bulk CSV import (default mode)."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        result = extractor.import_csv(incremental=False)

        mock_duckdb_client.import_csv.assert_called_once()
        assert "import_duration_seconds" in result
        assert "file_size_mb" in result
        assert extractor._imported is True

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_csv_incremental_mode(self, mock_duckdb_class, sample_csv_file, mock_duckdb_client):
        """Test incremental CSV import."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        extractor.import_csv(incremental=True, batch_size=1000)

        mock_duckdb_client.import_csv_incremental.assert_called_once()
        call_args = mock_duckdb_client.import_csv_incremental.call_args
        assert call_args.kwargs.get("batch_size") == 1000

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_csv_missing_file(self, mock_duckdb_class, tmp_path):
        """Test import with non-existent CSV file."""
        mock_duckdb_class.return_value = MagicMock()
        missing_file = tmp_path / "nonexistent.csv"

        extractor = SbirDuckDBExtractor(csv_path=missing_file)

        with pytest.raises(FileNotFoundError):
            extractor.import_csv()

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_csv_custom_delimiter(self, mock_duckdb_class, sample_csv_file, mock_duckdb_client):
        """Test CSV import with custom delimiter."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        extractor.import_csv(delimiter="|", encoding="latin-1")

        call_args = mock_duckdb_client.import_csv.call_args
        assert call_args.kwargs.get("delimiter") == "|"
        assert call_args.kwargs.get("encoding") == "latin-1"

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_csv_legacy_parameter(self, mock_duckdb_class, sample_csv_file, mock_duckdb_client):
        """Test backward compatibility with use_incremental parameter."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        # use_incremental should override incremental parameter
        extractor.import_csv(incremental=False, use_incremental=True)

        # Should use incremental import
        mock_duckdb_client.import_csv_incremental.assert_called_once()


class TestSbirDuckDBExtractorEdgeCases:
    """Tests for edge cases and error handling."""

    @patch('src.extractors.sbir.DuckDBClient')
    def test_import_tracks_metadata(self, mock_duckdb_class, sample_csv_file, mock_duckdb_client):
        """Test that import tracks metadata correctly."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        result = extractor.import_csv()

        assert "extraction_start_utc" in result
        assert "import_duration_seconds" in result
        assert "file_size_mb" in result
        assert result["file_size_mb"] >= 0  # Can be 0 for very small files

    @patch('src.extractors.sbir.DuckDBClient')
    def test_default_batch_size_when_not_specified(
        self, mock_duckdb_class, sample_csv_file, mock_duckdb_client
    ):
        """Test that default batch size is used when not specified."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        extractor.import_csv(incremental=True)  # No batch_size specified

        call_args = mock_duckdb_client.import_csv_incremental.call_args
        # Should use default of 10000
        assert call_args.kwargs.get("batch_size") == 10000


class TestSbirDuckDBExtractorTableIdentifier:
    """Tests for table identifier escaping."""

    @patch('src.extractors.sbir.DuckDBClient')
    def test_table_identifier_is_escaped(self, mock_duckdb_class, sample_csv_file):
        """Test that table name is properly escaped."""
        mock_client = MagicMock()
        mock_client.escape_identifier = Mock(return_value='"sbir_awards"')
        mock_duckdb_class.return_value = mock_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)

        mock_client.escape_identifier.assert_called_with("sbir_awards")
        assert extractor._table_identifier == '"sbir_awards"'


class TestSbirDuckDBExtractorImportedFlag:
    """Tests for _imported flag tracking."""

    @patch('src.extractors.sbir.DuckDBClient')
    def test_imported_flag_set_after_successful_import(
        self, mock_duckdb_class, sample_csv_file, mock_duckdb_client
    ):
        """Test that _imported flag is set after successful import."""
        mock_duckdb_class.return_value = mock_duckdb_client

        extractor = SbirDuckDBExtractor(csv_path=sample_csv_file)
        assert extractor._imported is False

        extractor.import_csv()

        assert extractor._imported is True


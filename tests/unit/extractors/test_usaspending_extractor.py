"""Tests for USAspending DuckDB extractor."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.extractors.usaspending import DuckDBUSAspendingExtractor, extract_usaspending_from_config


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def mock_connection():
    """Mock DuckDB connection."""
    conn = Mock()
    conn.execute = Mock(return_value=Mock(fetchone=Mock(return_value=(100,))))
    conn.close = Mock()
    return conn


@pytest.fixture
def sample_dump_file(tmp_path):
    """Sample PostgreSQL dump file."""
    dump_file = tmp_path / "usaspending.sql"
    dump_file.write_text("-- Sample PostgreSQL dump\nCREATE TABLE test_table (id INT);")
    return dump_file


# ==================== Initialization Tests ====================


class TestDuckDBUSAspendingExtractorInitialization:
    """Tests for DuckDBUSAspendingExtractor initialization."""

    def test_initialization_in_memory(self):
        """Test initialization with in-memory database."""
        extractor = DuckDBUSAspendingExtractor()

        assert extractor.db_path == ":memory:"
        assert extractor.connection is None

    def test_initialization_with_path(self, temp_db_path):
        """Test initialization with file path."""
        extractor = DuckDBUSAspendingExtractor(db_path=temp_db_path)

        assert extractor.db_path == temp_db_path
        assert extractor.connection is None


# ==================== Connection Management Tests ====================


class TestConnectionManagement:
    """Tests for connection management."""

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_connect_creates_connection(self, mock_connect):
        """Test connect creates new connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        conn = extractor.connect()

        assert conn == mock_conn
        mock_connect.assert_called_once_with(":memory:")
        mock_conn.execute.assert_called_once_with("SET enable_object_cache=true")

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_connect_reuses_existing_connection(self, mock_connect):
        """Test connect reuses existing connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        conn1 = extractor.connect()
        conn2 = extractor.connect()

        assert conn1 == conn2
        # Should only call connect once
        assert mock_connect.call_count == 1

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_close_connection(self, mock_connect):
        """Test close closes connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connect()
        extractor.close()

        mock_conn.close.assert_called_once()
        assert extractor.connection is None

    def test_close_without_connection(self):
        """Test close does nothing without active connection."""
        extractor = DuckDBUSAspendingExtractor()
        # Should not raise
        extractor.close()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_context_manager(self, mock_connect):
        """Test context manager protocol."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        with DuckDBUSAspendingExtractor() as extractor:
            assert extractor is not None

        # Should have closed connection on exit
        mock_conn.close.assert_called_once()


# ==================== Escape Functions Tests ====================


class TestEscapeFunctions:
    """Tests for SQL escaping functions."""

    @patch("src.extractors.usaspending.duckdb.escape_identifier")
    def test_escape_identifier_with_duckdb(self, mock_escape):
        """Test escape_identifier using DuckDB function."""
        mock_escape.return_value = '"table_name"'

        result = DuckDBUSAspendingExtractor._escape_identifier("table_name")

        assert result == '"table_name"'
        mock_escape.assert_called_once_with("table_name")

    def test_escape_identifier_fallback(self):
        """Test escape_identifier fallback when DuckDB function unavailable."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then patch it to raise AttributeError
        original = getattr(usaspending_module.duckdb, "escape_identifier", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_identifier"):
                delattr(usaspending_module.duckdb, "escape_identifier")
            result = DuckDBUSAspendingExtractor._escape_identifier("table_name")
            assert result == '"table_name"'
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_identifier = original

    def test_escape_identifier_with_quotes(self):
        """Test escape_identifier with embedded quotes."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_identifier", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_identifier"):
                delattr(usaspending_module.duckdb, "escape_identifier")
            result = DuckDBUSAspendingExtractor._escape_identifier('table"name')

            # Should escape internal quotes
            assert result == '"table""name"'
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_identifier = original

    @patch("src.extractors.usaspending.duckdb.escape_string_literal")
    def test_escape_literal_with_duckdb(self, mock_escape):
        """Test escape_literal using DuckDB function."""
        mock_escape.return_value = "'value'"

        result = DuckDBUSAspendingExtractor._escape_literal("value")

        assert result == "'value'"
        mock_escape.assert_called_once_with("value")

    def test_escape_literal_fallback(self):
        """Test escape_literal fallback when DuckDB function unavailable."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_string_literal", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_string_literal"):
                delattr(usaspending_module.duckdb, "escape_string_literal")
            result = DuckDBUSAspendingExtractor._escape_literal("value")
            assert result == "'value'"
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_string_literal = original

    def test_escape_literal_with_quotes(self):
        """Test escape_literal with embedded quotes."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_string_literal", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_string_literal"):
                delattr(usaspending_module.duckdb, "escape_string_literal")
            result = DuckDBUSAspendingExtractor._escape_literal("val'ue")

            # Should escape internal quotes
            assert result == "'val''ue'"
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_string_literal = original

    def test_escape_literal_with_backslashes(self):
        """Test escape_literal with backslashes."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_string_literal", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_string_literal"):
                delattr(usaspending_module.duckdb, "escape_string_literal")
            result = DuckDBUSAspendingExtractor._escape_literal("val\\ue")

            # Should escape backslashes
            assert result == "'val\\\\ue'"
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_string_literal = original


# ==================== Import Tests ====================


class TestImportPostgresDump:
    """Tests for import_postgres_dump method."""

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_nonexistent_file(self, mock_connect, tmp_path):
        """Test import raises error for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.sql"

        extractor = DuckDBUSAspendingExtractor()

        with pytest.raises(FileNotFoundError, match="PostgreSQL dump file not found"):
            extractor.import_postgres_dump(nonexistent)

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_sql_dump(self, mock_connect, sample_dump_file):
        """Test import of plain SQL dump."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(extractor, "_import_sql_dump", return_value=True) as mock_import:
            result = extractor.import_postgres_dump(sample_dump_file)

        assert result is True
        mock_import.assert_called_once()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump(self, mock_connect, tmp_path):
        """Test import of zipped dump."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(extractor, "_import_zipped_dump", return_value=True) as mock_import:
            result = extractor.import_postgres_dump(zip_file)

        assert result is True
        mock_import.assert_called_once()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_gzipped_dump(self, mock_connect, tmp_path):
        """Test import of gzipped dump."""
        gz_file = tmp_path / "usaspending.gz"
        gz_file.touch()

        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(extractor, "_import_gzipped_dump", return_value=True) as mock_import:
            result = extractor.import_postgres_dump(gz_file)

        assert result is True
        mock_import.assert_called_once()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_handles_exception(self, mock_connect, sample_dump_file):
        """Test import handles exceptions gracefully."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(extractor, "_import_sql_dump", side_effect=RuntimeError("Import failed")):
            result = extractor.import_postgres_dump(sample_dump_file)

        # Should return False on error
        assert result is False


# ==================== Zipped Dump Import Tests ====================


class TestZippedDumpImport:
    """Tests for _import_zipped_dump method."""

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_postgres_scanner_success(self, mock_connect, tmp_path):
        """Test zipped dump import with postgres_scanner."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        mock_conn = Mock()
        mock_conn.execute = Mock(return_value=Mock(fetchone=Mock(return_value=(1000,))))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor._import_zipped_dump(zip_file, "test_table")

        assert result is True
        # Should have executed CREATE VIEW
        assert any(
            "CREATE OR REPLACE VIEW" in str(call) for call in mock_conn.execute.call_args_list
        )

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_fallback_to_copy_files(self, mock_connect, tmp_path):
        """Test zipped dump import falls back to COPY files."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        mock_conn = Mock()
        # First execute (test query) fails, triggers fallback
        mock_conn.execute = Mock(side_effect=Exception("postgres_scanner failed"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        with patch.object(extractor, "_import_copy_files", return_value=True) as mock_copy:
            result = extractor._import_zipped_dump(zip_file, "test_table")

        assert result is True
        mock_copy.assert_called_once()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_final_fallback(self, mock_connect, tmp_path):
        """Test zipped dump import final fallback to extraction."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        mock_conn = Mock()
        mock_conn.execute = Mock(side_effect=Exception("postgres_scanner failed"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        with patch.object(extractor, "_import_copy_files", return_value=False):
            with patch.object(
                extractor, "_extract_and_import_dump", return_value=True
            ) as mock_extract:
                result = extractor._import_zipped_dump(zip_file, "test_table")

        assert result is True
        mock_extract.assert_called_once()


# ==================== Query Tests ====================


class TestQueryAwards:
    """Tests for query_awards method."""

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_query_awards_basic(self, mock_connect):
        """Test basic query_awards."""
        mock_conn = Mock()
        mock_df = pd.DataFrame({"award_id": [1, 2, 3]})
        mock_conn.execute = Mock(return_value=Mock(df=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor.query_awards()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_filters(self, mock_connect):
        """Test query_awards with filters."""
        mock_conn = Mock()
        mock_df = pd.DataFrame({"award_id": [1]})
        mock_conn.execute = Mock(return_value=Mock(df=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        filters = {"fiscal_year": 2023}
        extractor.query_awards(filters=filters)

        # Should have executed query with WHERE clause
        executed_query = str(mock_conn.execute.call_args[0][0])
        assert "WHERE" in executed_query

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_columns(self, mock_connect):
        """Test query_awards with specific columns."""
        mock_conn = Mock()
        mock_df = pd.DataFrame({"award_id": [1], "amount": [100]})
        mock_conn.execute = Mock(return_value=Mock(df=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        columns = ["award_id", "amount"]
        extractor.query_awards(columns=columns)

        # Should have selected specific columns
        executed_query = str(mock_conn.execute.call_args[0][0])
        assert "award_id" in executed_query
        assert "amount" in executed_query

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_limit(self, mock_connect):
        """Test query_awards with limit."""
        mock_conn = Mock()
        mock_df = pd.DataFrame({"award_id": [1]})
        mock_conn.execute = Mock(return_value=Mock(df=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        extractor.query_awards(limit=10)

        executed_query = str(mock_conn.execute.call_args[0][0])
        assert "LIMIT" in executed_query


# ==================== Table Info Tests ====================


class TestGetTableInfo:
    """Tests for get_table_info method."""

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_get_table_info_success(self, mock_connect):
        """Test get_table_info returns table information."""
        mock_conn = Mock()
        mock_conn.execute = Mock(
            return_value=Mock(
                fetchall=Mock(
                    return_value=[
                        ("id", "INTEGER"),
                        ("name", "VARCHAR"),
                    ]
                )
            )
        )
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        info = extractor.get_table_info()

        assert "columns" in info
        assert len(info["columns"]) == 2

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_get_table_info_table_not_found(self, mock_connect):
        """Test get_table_info handles missing table."""
        mock_conn = Mock()
        mock_conn.execute = Mock(side_effect=Exception("Table not found"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        info = extractor.get_table_info()

        # Should return dict with error info
        assert isinstance(info, dict)


# ==================== Dump Tables Listing Tests ====================


class TestListDumpTables:
    """Tests for list_dump_tables method."""

    @patch("src.extractors.usaspending.duckdb.connect")
    @patch("subprocess.run")
    def test_list_dump_tables_success(self, mock_run, mock_connect, tmp_path):
        """Test list_dump_tables lists available tables."""
        dump_file = tmp_path / "usaspending.zip"
        dump_file.touch()

        mock_run.return_value = Mock(
            returncode=0,
            stdout="table1\ntable2\ntable3\n",
            stderr="",
        )

        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        tables = extractor.list_dump_tables(dump_file)

        assert isinstance(tables, list)


# ==================== Module Function Tests ====================


class TestModuleFunctions:
    """Tests for module-level functions."""

    @patch("src.extractors.usaspending.get_config")
    @patch("src.extractors.usaspending.DuckDBUSAspendingExtractor")
    def test_extract_usaspending_from_config(self, mock_extractor_class, mock_get_config):
        """Test extract_usaspending_from_config function."""
        from tests.utils.config_mocks import create_mock_pipeline_config

        mock_config = create_mock_pipeline_config()
        # Set extractors.usaspending settings
        if hasattr(mock_config, "extraction"):
            if not hasattr(mock_config.extraction, "usaspending"):
                mock_config.extraction.usaspending = Mock()
            mock_config.extraction.usaspending.dump_file = "/path/to/dump.zip"
            mock_config.extraction.usaspending.db_path = "/path/to/db"
        # Also check for extractors attribute (backward compatibility)
        if not hasattr(mock_config, "extraction") and hasattr(mock_config, "extractors"):
            if not hasattr(mock_config.extractors, "usaspending"):
                mock_config.extractors.usaspending = Mock()
            mock_config.extractors.usaspending.dump_file = "/path/to/dump.zip"
            mock_config.extractors.usaspending.db_path = "/path/to/db"
        mock_get_config.return_value = mock_config

        mock_extractor = Mock()
        mock_extractor.import_postgres_dump = Mock(return_value=True)
        mock_extractor.query_awards = Mock(return_value=pd.DataFrame())
        mock_extractor_class.return_value = mock_extractor

        result = extract_usaspending_from_config()

        assert isinstance(result, pd.DataFrame)
        mock_extractor.import_postgres_dump.assert_called_once()


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_escape_identifier_empty_string(self):
        """Test escape_identifier with empty string."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_identifier", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_identifier"):
                delattr(usaspending_module.duckdb, "escape_identifier")
            result = DuckDBUSAspendingExtractor._escape_identifier("")
            assert result == '""'
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_identifier = original

    def test_escape_literal_empty_string(self):
        """Test escape_literal with empty string."""
        import src.extractors.usaspending as usaspending_module
        # Remove the attribute if it exists, then test fallback
        original = getattr(usaspending_module.duckdb, "escape_string_literal", None)
        try:
            if hasattr(usaspending_module.duckdb, "escape_string_literal"):
                delattr(usaspending_module.duckdb, "escape_string_literal")
            result = DuckDBUSAspendingExtractor._escape_literal("")
            assert result == "''"
        finally:
            # Restore the original attribute if it existed
            if original is not None:
                usaspending_module.duckdb.escape_string_literal = original

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_multiple_close_calls(self, mock_connect):
        """Test multiple close calls don't error."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connect()
        extractor.close()
        # Second close should not raise
        extractor.close()

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_query_awards_empty_result(self, mock_connect):
        """Test query_awards with empty result."""
        mock_conn = Mock()
        mock_df = pd.DataFrame()
        mock_conn.execute = Mock(return_value=Mock(df=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor.query_awards()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_import_sql_dump_execute_fails(self, mock_connect, sample_dump_file):
        """Test SQL dump import handles execution failures."""
        mock_conn = Mock()
        mock_conn.execute = Mock(side_effect=Exception("SQL execution failed"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor._import_sql_dump(sample_dump_file, "test_table")

        # Should return False on failure
        assert result is False

    @patch("src.extractors.usaspending.duckdb.connect")
    def test_context_manager_with_exception(self, mock_connect):
        """Test context manager closes connection even on exception."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        try:
            with DuckDBUSAspendingExtractor():
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should still have closed connection
        mock_conn.close.assert_called_once()

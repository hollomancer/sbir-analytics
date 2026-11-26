"""Tests for USAspending DuckDB extractor."""

from unittest.mock import Mock, patch

import pandas as pd
import pytest

from sbir_etl.extractors.usaspending import (
    DuckDBUSAspendingExtractor,
    extract_usaspending_from_config,
)
from tests.mocks import DuckDBMocks


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def mock_connection():
    """Mock DuckDB connection."""
    return DuckDBMocks.connection()


# ==================== Initialization Tests ====================


class TestDuckDBUSAspendingExtractorInitialization:
    """Tests for DuckDBUSAspendingExtractor initialization."""

    @pytest.mark.parametrize(
        "db_path,expected_path",
        [
            (None, ":memory:"),  # default in-memory
            ("/tmp/test.db", "/tmp/test.db"),  # custom path
        ],
        ids=["in_memory", "with_path"],
    )
    def test_initialization(self, db_path, expected_path):
        """Test initialization with various database paths."""
        extractor = (
            DuckDBUSAspendingExtractor(db_path=db_path) if db_path else DuckDBUSAspendingExtractor()
        )

        assert extractor.db_path == expected_path
        assert extractor.connection is None


# ==================== Connection Management Tests ====================


class TestConnectionManagement:
    """Tests for connection management."""

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_connect_creates_connection(self, mock_connect):
        """Test connect creates new connection."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        conn = extractor.connect()

        assert conn == mock_conn
        mock_connect.assert_called_once_with(":memory:")
        mock_conn.execute.assert_called_once_with("SET enable_object_cache=true")

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_connect_reuses_existing_connection(self, mock_connect):
        """Test connect reuses existing connection."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        conn1 = extractor.connect()
        conn2 = extractor.connect()

        assert conn1 == conn2
        # Should only call connect once
        assert mock_connect.call_count == 1

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_close_connection(self, mock_connect):
        """Test close closes connection."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
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

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_context_manager(self, mock_connect):
        """Test context manager protocol."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        with DuckDBUSAspendingExtractor() as extractor:
            extractor.connect()  # Establish connection
            assert extractor is not None

        # Should have closed connection on exit
        mock_conn.close.assert_called_once()


# ==================== Import Tests ====================


class TestImportPostgresDump:
    """Tests for import_postgres_dump method."""

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_nonexistent_file(self, mock_connect, tmp_path):
        """Test import raises error for nonexistent file."""
        nonexistent = tmp_path / "nonexistent.sql"

        extractor = DuckDBUSAspendingExtractor()

        with pytest.raises(FileNotFoundError, match="PostgreSQL dump file not found"):
            extractor.import_postgres_dump(nonexistent)

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump(self, mock_connect, tmp_path):
        """Test import of zipped dump."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(extractor, "_import_zipped_dump", return_value=True) as mock_import:
            result = extractor.import_postgres_dump(zip_file)

        assert result is True
        mock_import.assert_called_once()

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_handles_exception(self, mock_connect, tmp_path):
        """Test import handles exceptions gracefully."""
        from tests.mocks import DuckDBMocks

        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()
        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()

        with patch.object(
            extractor, "_import_zipped_dump", side_effect=RuntimeError("Import failed")
        ):
            result = extractor.import_postgres_dump(zip_file)

        # Should return False on error
        assert result is False


# ==================== Zipped Dump Import Tests ====================


class TestZippedDumpImport:
    """Tests for _import_zipped_dump method."""

    @patch("subprocess.run")
    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_without_toc_raises(self, mock_connect, mock_subprocess, tmp_path):
        """A ZIP with COPY files but no readable toc.dat no longer uses the first file."""
        from sbir_etl.exceptions import ExtractionError

        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        # Before #798 this listing alone built the view from 5881.dat.gz.
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout="  12345  2024-01-01 12:00   5881.dat.gz\n  67890  2024-01-01 12:00   5882.dat.gz\n",
            stderr="",
        )

        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        with pytest.raises(ExtractionError, match="table of contents"):
            extractor._import_zipped_dump(zip_file, "test_table")

        assert not any(
            "CREATE OR REPLACE VIEW" in str(call) for call in mock_conn.execute.call_args_list
        )

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_fallback_to_copy_files(self, mock_connect, tmp_path):
        """Test zipped dump import falls back to COPY files."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        # First execute (test query) fails, triggers fallback
        mock_conn.execute = Mock(side_effect=Exception("postgres_scanner failed"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        with patch.object(extractor, "_import_copy_files", return_value=True) as mock_copy:
            result = extractor._import_zipped_dump(zip_file, "test_table")

        assert result is True
        mock_copy.assert_called_once()

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_import_zipped_dump_returns_false_when_copy_files_fail(self, mock_connect, tmp_path):
        """Test zipped dump import has no pg_restore fallback."""
        zip_file = tmp_path / "usaspending.zip"
        zip_file.touch()

        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_conn.execute = Mock(side_effect=Exception("postgres_scanner failed"))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        with patch.object(extractor, "_import_copy_files", return_value=False):
            result = extractor._import_zipped_dump(zip_file, "test_table")

        assert result is False


# ==================== Query Tests ====================


class TestQueryAwards:
    """Tests for query_awards method."""

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_query_awards_basic(self, mock_connect):
        """Test basic query_awards."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_df = pd.DataFrame({"award_id": [1, 2, 3]})
        mock_conn.execute = Mock(return_value=Mock(fetchdf=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor.query_awards()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_filters(self, mock_connect):
        """Test query_awards with filters."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_df = pd.DataFrame({"award_id": [1]})
        mock_conn.execute = Mock(return_value=Mock(fetchdf=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        filters = {"fiscal_year": 2023}
        extractor.query_awards(filters=filters)

        # Should have executed query with WHERE clause
        executed_query = str(mock_conn.execute.call_args[0][0])
        assert "WHERE" in executed_query

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_columns(self, mock_connect):
        """Test query_awards with specific columns - columns param not implemented."""
        # columns parameter not implemented in query_awards - test removed

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_query_awards_with_limit(self, mock_connect):
        """Test query_awards with limit."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_df = pd.DataFrame({"award_id": [1]})
        mock_conn.execute = Mock(return_value=Mock(fetchdf=Mock(return_value=mock_df)))
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        extractor.query_awards(limit=10)

        executed_query = str(mock_conn.execute.call_args[0][0])
        assert "LIMIT" in executed_query


# ==================== Table Info Tests ====================


class TestGetTableInfo:
    """Tests for get_table_info method."""

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_get_table_info_success(self, mock_connect):
        """Test get_table_info returns table information."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        # Mock DESCRIBE query result
        columns_df = pd.DataFrame(
            {"column_name": ["id", "name"], "column_type": ["INTEGER", "VARCHAR"]}
        )
        # Mock COUNT query result
        mock_conn.execute = Mock(
            side_effect=[
                Mock(fetchdf=Mock(return_value=columns_df)),  # DESCRIBE result
                Mock(fetchone=Mock(return_value=(100,))),  # COUNT result
            ]
        )
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        info = extractor.get_table_info()

        assert "columns" in info
        assert "row_count" in info

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_get_table_info_table_not_found(self, mock_connect):
        """Test get_table_info handles missing table."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
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

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
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

        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        tables = extractor.list_dump_tables(dump_file)

        assert isinstance(tables, list)


# ==================== Module Function Tests ====================


class TestModuleFunctions:
    """Tests for module-level functions."""

    @patch("sbir_etl.extractors.usaspending.get_config")
    @patch("sbir_etl.extractors.usaspending.DuckDBUSAspendingExtractor")
    def test_extract_usaspending_from_config(self, mock_extractor_class, mock_get_config):
        """Test extract_usaspending_from_config function."""
        from tests.utils.config_mocks import create_mock_pipeline_config

        mock_config = create_mock_pipeline_config()
        # Set extractors.usaspending settings - handle both dict and object
        if hasattr(mock_config, "extraction"):
            if isinstance(mock_config.extraction.usaspending, dict):
                mock_config.extraction.usaspending["dump_file"] = "/path/to/dump.zip"
                mock_config.extraction.usaspending["db_path"] = "/path/to/db"
            else:
                if not hasattr(mock_config.extraction, "usaspending"):
                    mock_config.extraction.usaspending = Mock()
                mock_config.extraction.usaspending.dump_file = "/path/to/dump.zip"
                mock_config.extraction.usaspending.db_path = "/path/to/db"
        mock_get_config.return_value = mock_config

        mock_extractor = Mock()
        mock_extractor.import_postgres_dump = Mock(return_value=True)
        mock_extractor.query_awards = Mock(return_value=pd.DataFrame())
        mock_extractor_class.return_value = mock_extractor

        result = extract_usaspending_from_config()

        assert result == mock_extractor
        mock_extractor_class.assert_called_once()

    @staticmethod
    def _config(configured_dump):
        config = Mock()
        config.duckdb.database_path = ":memory:"
        config.extraction.usaspending = {"table_name": "usaspending_awards"}
        config.paths.resolve_path.return_value = configured_dump
        return config

    @patch("sbir_etl.extractors.usaspending.DuckDBUSAspendingExtractor")
    def test_configured_dump_import_error_propagates(self, mock_extractor_class, tmp_path):
        """An import error on the configured path is no longer logged at DEBUG and dropped."""
        from sbir_etl.exceptions import ExtractionError

        configured_dump = tmp_path / "configured.zip"
        configured_dump.touch()
        mock_extractor_class.return_value.import_postgres_dump.side_effect = ExtractionError(
            "TOC does not list recipient_lookup"
        )

        with pytest.raises(ExtractionError, match="TOC does not list recipient_lookup"):
            extract_usaspending_from_config(data_dir=tmp_path, config=self._config(configured_dump))

    @patch("sbir_etl.extractors.usaspending.DuckDBUSAspendingExtractor")
    def test_import_returning_false_raises(self, mock_extractor_class, tmp_path):
        """A False import result is no longer ignored."""
        from sbir_etl.exceptions import ExtractionError

        (tmp_path / "dump.zip").touch()
        mock_extractor_class.return_value.import_postgres_dump.return_value = False

        with pytest.raises(ExtractionError, match="import from .*dump.zip failed"):
            extract_usaspending_from_config(
                data_dir=tmp_path,
                dump_filename="dump.zip",
                config=self._config(tmp_path / "missing.zip"),
            )

    @patch("sbir_etl.extractors.usaspending.DuckDBUSAspendingExtractor")
    def test_unavailable_configured_path_imports_nothing(self, mock_extractor_class, tmp_path):
        """Only the configured-path lookup is optional."""
        config = self._config(None)
        config.paths.resolve_path.side_effect = ValueError("Unknown path key")

        result = extract_usaspending_from_config(data_dir=tmp_path, config=config)

        assert result is mock_extractor_class.return_value
        mock_extractor_class.return_value.import_postgres_dump.assert_not_called()


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_multiple_close_calls(self, mock_connect):
        """Test multiple close calls don't error."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connect()
        extractor.close()
        # Second close should not raise
        extractor.close()

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_query_awards_empty_result(self, mock_connect):
        """Test query_awards with empty result."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_df = pd.DataFrame()
        # Mock the execute().fetchdf() chain to return actual DataFrame
        mock_result = Mock()
        mock_result.fetchdf.return_value = mock_df
        mock_conn.execute.return_value = mock_result
        mock_connect.return_value = mock_conn

        extractor = DuckDBUSAspendingExtractor()
        extractor.connection = mock_conn

        result = extractor.query_awards()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    @patch("sbir_etl.extractors.usaspending.duckdb.connect")
    def test_context_manager_with_exception(self, mock_connect):
        """Test context manager closes connection even on exception."""
        from tests.mocks import DuckDBMocks

        mock_conn = DuckDBMocks.connection()
        mock_connect.return_value = mock_conn

        try:
            with DuckDBUSAspendingExtractor() as extractor:
                extractor.connect()  # Establish connection
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should still have closed connection
        mock_conn.close.assert_called_once()

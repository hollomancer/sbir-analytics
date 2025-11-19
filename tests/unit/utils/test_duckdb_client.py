"""Unit tests for DuckDB client utilities.

Tests cover:
- Client initialization (in-memory and file-based)
- Connection management and context managers
- Query execution (with and without parameters)
- CSV import functionality
- Batch operations
- Identifier and literal escaping
- Error handling and transactions
"""

import csv

import pytest

from src.utils.data.duckdb_client import DuckDBClient


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create a sample CSV file for testing."""
    csv_file = tmp_path / "test_data.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "value"])
        writer.writerow(["1", "Alice", "100"])
        writer.writerow(["2", "Bob", "200"])
        writer.writerow(["3", "Charlie", "300"])
    return csv_file


class TestDuckDBClientInitialization:
    """Tests for DuckDB client initialization."""

    def test_init_in_memory(self):
        """Test initialization with in-memory database."""
        client = DuckDBClient()

        assert client.database_path == ":memory:"
        assert client.read_only is False
        assert client._connection is None

    def test_init_with_file_path(self, tmp_path):
        """Test initialization with file-based database."""
        db_path = str(tmp_path / "test.db")
        client = DuckDBClient(database_path=db_path)

        assert client.database_path == db_path
        assert client.read_only is False

    def test_init_read_only(self, tmp_path):
        """Test initialization in read-only mode."""
        db_path = str(tmp_path / "test.db")
        client = DuckDBClient(database_path=db_path, read_only=True)

        assert client.read_only is True


class TestDuckDBClientIdentifierEscaping:
    """Tests for identifier and literal escaping."""

    def test_escape_identifier_simple(self):
        """Test escaping simple identifier."""
        result = DuckDBClient.escape_identifier("table_name")

        assert result == '"table_name"'

    def test_escape_identifier_with_quotes(self):
        """Test escaping identifier with quotes."""
        result = DuckDBClient.escape_identifier('table"name')

        assert '""' in result or result == '"table\\"name"'

    def test_escape_identifier_special_chars(self):
        """Test escaping identifier with special characters."""
        result = DuckDBClient.escape_identifier("table-name")

        assert '"' in result

    def test_escape_literal_simple(self):
        """Test escaping simple string literal."""
        result = DuckDBClient.escape_literal("test string")

        assert result == "'test string'"

    def test_escape_literal_with_quotes(self):
        """Test escaping literal with single quotes."""
        result = DuckDBClient.escape_literal("test's string")

        assert "''" in result or "\\'s" in result

    def test_escape_literal_with_backslash(self):
        """Test escaping literal with backslash."""
        result = DuckDBClient.escape_literal("test\\string")

        assert "\\\\" in result or result == "'test\\string'"


class TestDuckDBClientConnection:
    """Tests for connection management."""

    def test_connection_context_manager(self):
        """Test connection context manager."""
        client = DuckDBClient()

        with client.connection() as conn:
            assert conn is not None
            result = conn.execute("SELECT 1 as num").fetchall()
            assert result[0][0] == 1

    def test_in_memory_persistent_connection(self):
        """Test that in-memory databases maintain persistent connection."""
        client = DuckDBClient()

        with client.connection() as conn1:
            conn1.execute("CREATE TABLE test (id INTEGER)")

        # Should be able to access the table in subsequent connections
        with client.connection() as conn2:
            result = conn2.execute("SELECT * FROM test").fetchall()
            assert result == []

    def test_file_database_separate_connections(self, tmp_path):
        """Test that file databases create separate connections."""
        db_path = str(tmp_path / "test.db")
        client = DuckDBClient(database_path=db_path)

        # Create table
        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")

        # Should be accessible in new connection
        with client.connection() as conn:
            result = conn.execute("SELECT * FROM test").fetchall()
            assert result == []

    def test_close_persistent_connection(self):
        """Test closing persistent connection."""
        client = DuckDBClient()

        # Create connection
        with client.connection() as conn:
            conn.execute("SELECT 1")

        assert client._persistent_conn is not None
        client.close()
        assert client._persistent_conn is None


class TestDuckDBClientQueryExecution:
    """Tests for query execution."""

    def test_execute_query_simple(self):
        """Test executing simple query."""
        client = DuckDBClient()

        results = client.execute_query("SELECT 1 as num, 'test' as text")

        assert len(results) == 1
        assert results[0]["num"] == 1
        assert results[0]["text"] == "test"

    def test_execute_query_with_parameters(self):
        """Test executing query with parameters."""
        client = DuckDBClient()

        # Create table and insert data
        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
            conn.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")

        # Query with parameters
        results = client.execute_query("SELECT * FROM test WHERE id = $id", parameters={"id": 1})

        assert len(results) == 1
        assert results[0]["name"] == "Alice"

    def test_execute_query_empty_result(self):
        """Test query returning empty result."""
        client = DuckDBClient()

        results = client.execute_query("SELECT * FROM (SELECT 1 as x) WHERE x > 10")

        assert len(results) == 0
        assert isinstance(results, list)

    def test_execute_query_multiple_rows(self):
        """Test query returning multiple rows."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, value INTEGER)")
            conn.execute("INSERT INTO test VALUES (1, 100), (2, 200), (3, 300)")

        results = client.execute_query("SELECT * FROM test ORDER BY id")

        assert len(results) == 3
        assert results[0]["id"] == 1
        assert results[2]["value"] == 300

    def test_execute_query_df(self):
        """Test executing query returning DataFrame."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
            conn.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")

        df = client.execute_query_df("SELECT * FROM test ORDER BY id")

        assert len(df) == 2
        assert list(df.columns) == ["id", "name"]
        assert df.iloc[0]["name"] == "Alice"


class TestDuckDBClientCSVImport:
    """Tests for CSV import functionality."""

    def test_import_csv_basic(self, sample_csv_file):
        """Test basic CSV import."""
        client = DuckDBClient()

        success = client.import_csv(sample_csv_file, "test_table")

        assert success is True

        # Verify data was imported
        results = client.execute_query("SELECT * FROM test_table ORDER BY id")
        assert len(results) == 3
        assert results[0]["name"] == "Alice"

    def test_import_csv_custom_delimiter(self, tmp_path):
        """Test CSV import with custom delimiter."""
        csv_file = tmp_path / "test.tsv"
        with open(csv_file, "w") as f:
            f.write("id\tname\n1\tAlice\n2\tBob\n")

        client = DuckDBClient()
        success = client.import_csv(csv_file, "test_table", delimiter="\t")

        assert success is True
        results = client.execute_query("SELECT * FROM test_table")
        assert len(results) == 2

    def test_import_csv_no_header(self, tmp_path):
        """Test CSV import without header."""
        csv_file = tmp_path / "test.csv"
        with open(csv_file, "w") as f:
            f.write("1,Alice\n2,Bob\n")

        client = DuckDBClient()
        success = client.import_csv(csv_file, "test_table", header=False)

        assert success is True

    def test_import_csv_missing_file(self, tmp_path):
        """Test CSV import with missing file."""
        client = DuckDBClient()
        missing_file = tmp_path / "missing.csv"

        success = client.import_csv(missing_file, "test_table")

        assert success is False

    def test_import_csv_creates_table(self, sample_csv_file):
        """Test that CSV import creates table if it doesn't exist."""
        client = DuckDBClient()

        # Verify table doesn't exist
        with client.connection() as conn:
            tables = conn.execute("SHOW TABLES").fetchall()
            assert "test_table" not in [t[0] for t in tables]

        # Import CSV
        client.import_csv(sample_csv_file, "test_table")

        # Verify table exists
        with client.connection() as conn:
            tables = conn.execute("SHOW TABLES").fetchall()
            assert "test_table" in [t[0] for t in tables]


class TestDuckDBClientTableOperations:
    """Tests for table operations."""

    def test_table_exists_true(self):
        """Test table_exists returns True for existing table."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")

        assert client.table_exists("test") is True

    def test_table_exists_false(self):
        """Test table_exists returns False for non-existent table."""
        client = DuckDBClient()

        assert client.table_exists("nonexistent") is False

    def test_get_table_info(self):
        """Test getting table information."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER, name VARCHAR)")
            conn.execute("INSERT INTO test VALUES (1, 'Alice'), (2, 'Bob')")

        info = client.get_table_info("test")

        assert info["table_name"] == "test"
        assert info["row_count"] == 2
        assert "columns" in info

    def test_get_table_info_nonexistent(self):
        """Test getting info for non-existent table."""
        client = DuckDBClient()

        info = client.get_table_info("nonexistent")

        assert "error" in info

    def test_create_table_from_df(self):
        """Test creating table from DataFrame."""
        import pandas as pd

        client = DuckDBClient()
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"]})

        success = client.create_table_from_df(df, "test_table")

        assert success is True
        results = client.execute_query("SELECT count(*) as cnt FROM test_table")
        assert results[0]["cnt"] == 3


class TestDuckDBClientTransactions:
    """Tests for transaction handling."""

    def test_transaction_commit(self):
        """Test transaction commit persists data."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("BEGIN TRANSACTION")
            conn.execute("INSERT INTO test VALUES (1)")
            conn.execute("COMMIT")

        # Verify data persisted
        results = client.execute_query("SELECT * FROM test")
        assert len(results) == 1

    def test_transaction_rollback(self):
        """Test transaction rollback discards changes."""
        client = DuckDBClient()

        with client.connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (1)")
            conn.execute("BEGIN TRANSACTION")
            conn.execute("INSERT INTO test VALUES (2)")
            conn.execute("ROLLBACK")

        # Verify only first insert persisted
        results = client.execute_query("SELECT * FROM test")
        assert len(results) == 1
        assert results[0]["id"] == 1


class TestDuckDBClientPagination:
    """Tests for pagination and chunking functionality."""

    def test_fetch_df_chunks_paginates_correctly(self, tmp_path):
        """
        Create a DuckDB file-backed database from a DataFrame and verify that
        fetch_df_chunks paginates results into chunks of at most batch_size rows,
        and that concatenating the chunks yields the original dataset.
        """
        import pandas as pd

        num_rows = 2500
        batch_size = 1000
        df = pd.DataFrame(
            {
                "id": list(range(num_rows)),
                "value": [f"val_{i}" for i in range(num_rows)],
            }
        )

        db_path = tmp_path / "test.duckdb"
        client = DuckDBClient(database_path=str(db_path))

        # Create table from the full DataFrame
        assert client.create_table_from_df(df, table_name="test_table") is True

        # Fetch chunks and verify sizes and total count
        chunks = list(client.fetch_df_chunks("SELECT * FROM test_table", batch_size=batch_size))

        # Ensure we received some chunks
        assert len(chunks) >= 1

        # Each chunk must be <= batch_size
        assert all(len(chunk) <= batch_size for chunk in chunks)

        # Total rows across chunks equals the original row count
        total = sum(len(chunk) for chunk in chunks)
        assert total == num_rows

        # Concatenate and compare contents (sorted by id to avoid reliance on insertion-order quirks)
        concatenated = pd.concat(chunks, ignore_index=True).sort_values("id").reset_index(drop=True)
        expected = df.sort_values("id").reset_index(drop=True)

        pd.testing.assert_frame_equal(concatenated, expected)

    def test_fetch_df_chunks_empty_table(self, tmp_path):
        """
        Ensure that fetching chunks from an empty table yields no chunks (empty generator).
        """
        import pandas as pd

        db_path = tmp_path / "empty.duckdb"
        client = DuckDBClient(database_path=str(db_path))
        empty_df = pd.DataFrame(columns=["id", "value"])

        assert client.create_table_from_df(empty_df, table_name="empty_table") is True

        chunks = list(client.fetch_df_chunks("SELECT * FROM empty_table", batch_size=10))
        assert chunks == []

    def test_import_csv_incremental_creates_and_counts_rows(self, tmp_path):
        """
        Write a CSV to disk and import it incrementally into DuckDB using import_csv_incremental.
        Verify the method returns True and that the table contains the expected number of rows.
        """
        import pandas as pd

        num_rows = 350
        chunk_size = 100

        # Create CSV file
        csv_path = tmp_path / "sample.csv"
        df = pd.DataFrame(
            {
                "id": list(range(num_rows)),
                "value": [f"val_{i}" for i in range(num_rows)],
            }
        )
        df.to_csv(csv_path, index=False)

        db_path = tmp_path / "inc.duckdb"
        client = DuckDBClient(database_path=str(db_path))

        # Import incrementally
        success = client.import_csv_incremental(
            csv_path=csv_path, table_name="inc_table", batch_size=chunk_size, delimiter=",", header=True
        )

        assert success is True

        # Verify row count via get_table_info
        info = client.get_table_info("inc_table")
        assert "row_count" in info
        assert int(info["row_count"]) == num_rows

        # Also check via SQL directly
        count_df = client.execute_query_df("SELECT COUNT(*) as cnt FROM inc_table")
        assert int(count_df["cnt"].iloc[0]) == num_rows

    def test_import_csv_incremental_appends_when_table_exists(self, tmp_path):
        """
        When a table already exists, incremental import should append rows.
        We simulate this by creating an initial table and then importing the same CSV again.
        """
        import pandas as pd

        single_rows = 45
        csv_path = tmp_path / "append.csv"
        df = pd.DataFrame(
            {
                "id": list(range(single_rows)),
                "value": [f"val_{i}" for i in range(single_rows)],
            }
        )
        df.to_csv(csv_path, index=False)

        db_path = tmp_path / "append.duckdb"
        client = DuckDBClient(database_path=str(db_path))

        # First import - create table
        ok = client.import_csv_incremental(csv_path=csv_path, table_name="append_table", batch_size=20)
        assert ok is True
        info1 = client.get_table_info("append_table")
        assert int(info1["row_count"]) == single_rows

        # Second import - append same CSV again
        ok2 = client.import_csv_incremental(
            csv_path=csv_path, table_name="append_table", batch_size=20, create_table_if_missing=False
        )
        assert ok2 is True
        info2 = client.get_table_info("append_table")
        # Now there should be twice the original rows
        assert int(info2["row_count"]) == single_rows * 2


class TestDuckDBClientErrorHandling:
    """Tests for error handling."""

    def test_execute_query_syntax_error(self):
        """Test handling of SQL syntax error."""
        client = DuckDBClient()

        with pytest.raises(Exception):  # DuckDB will raise an exception
            client.execute_query("SELECT * FORM invalid_syntax")

    def test_execute_query_table_not_found(self):
        """Test handling of missing table error."""
        client = DuckDBClient()

        with pytest.raises(Exception):
            client.execute_query("SELECT * FROM nonexistent_table")

    def test_close_without_connection(self):
        """Test closing client without active connection."""
        client = DuckDBClient()

        # Should not raise an error
        client.close()
        assert client._persistent_conn is None

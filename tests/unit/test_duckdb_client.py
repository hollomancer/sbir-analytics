from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

from src.utils.duckdb_client import DuckDBClient


def _make_dataframe(num_rows: int) -> pd.DataFrame:
    """Helper to create a simple DataFrame for tests."""
    return pd.DataFrame(
        {
            "id": list(range(num_rows)),
            "value": [f"val_{i}" for i in range(num_rows)],
        }
    )


def test_fetch_df_chunks_paginates_correctly(tmp_path: Path):
    """
    Create a DuckDB file-backed database from a DataFrame and verify that
    fetch_df_chunks paginates results into chunks of at most batch_size rows,
    and that concatenating the chunks yields the original dataset.
    """
    num_rows = 2500
    batch_size = 1000
    df = _make_dataframe(num_rows)

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


def test_fetch_df_chunks_empty_table(tmp_path: Path):
    """
    Ensure that fetching chunks from an empty table yields no chunks (empty generator).
    """
    db_path = tmp_path / "empty.duckdb"
    client = DuckDBClient(database_path=str(db_path))
    empty_df = pd.DataFrame(columns=["id", "value"])

    assert client.create_table_from_df(empty_df, table_name="empty_table") is True

    chunks = list(client.fetch_df_chunks("SELECT * FROM empty_table", batch_size=10))
    assert chunks == []


def test_import_csv_incremental_creates_and_counts_rows(tmp_path: Path):
    """
    Write a CSV to disk and import it incrementally into DuckDB using import_csv_incremental.
    Verify the method returns True and that the table contains the expected number of rows.
    """
    num_rows = 350
    chunk_size = 100

    # Create CSV file
    csv_path = tmp_path / "sample.csv"
    df = _make_dataframe(num_rows)
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


def test_import_csv_incremental_appends_when_table_exists(tmp_path: Path):
    """
    When a table already exists, incremental import should append rows.
    We simulate this by creating an initial table and then importing the same CSV again.
    """
    single_rows = 45
    csv_path = tmp_path / "append.csv"
    df = _make_dataframe(single_rows)
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

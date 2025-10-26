import os
from pathlib import Path

import pandas as pd
import pytest

from src.extractors.sbir import SbirDuckDBExtractor


FIXTURE_CSV = Path("tests/fixtures/sbir_sample.csv")


def test_import_csv_returns_metadata_and_columns(tmp_path: Path):
    """
    Using the provided sample fixture CSV, import into a file-backed DuckDB
    database and assert metadata contains columns, column counts, timestamps,
    and the expected row count from the fixture (3 rows).
    """
    assert FIXTURE_CSV.exists(), f"Expected fixture CSV at {FIXTURE_CSV} to exist"

    db_path = tmp_path / "sbir.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=FIXTURE_CSV, duckdb_path=str(db_path), table_name="sbir_test"
    )

    # Call import_csv (default is non-incremental); explicit param name used to match implementation
    metadata = extractor.import_csv(use_incremental=False)

    # Basic metadata presence checks
    assert isinstance(metadata, dict)
    for key in (
        "columns",
        "column_count",
        "extraction_start_utc",
        "extraction_end_utc",
        "row_count",
    ):
        assert key in metadata, f"Missing metadata key: {key}"

    # Expect the fixture to match the project's expected SBIR column count (42)
    assert metadata["column_count"] == 42

    # Fixture contains 3 sample rows
    assert int(metadata["row_count"]) == 3

    # Columns should be a list of strings and length matches column_count
    assert isinstance(metadata["columns"], list)
    assert all(isinstance(c, str) for c in metadata["columns"])
    assert len(metadata["columns"]) == metadata["column_count"]

    # Timestamps should be present and non-empty strings
    assert (
        isinstance(metadata["extraction_start_utc"], str)
        and len(metadata["extraction_start_utc"]) > 0
    )
    assert (
        isinstance(metadata["extraction_end_utc"], str) and len(metadata["extraction_end_utc"]) > 0
    )


def test_import_csv_raises_on_missing_columns(tmp_path: Path):
    """
    Create a deliberately malformed CSV (too few columns) and ensure the
    extractor raises a RuntimeError indicating column-count mismatch.
    """
    # Create a small CSV with only two columns to simulate a broken file
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("a,b\n1,2\n3,4\n")

    db_path = tmp_path / "bad.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=bad_csv, duckdb_path=str(db_path), table_name="sbir_bad"
    )

    with pytest.raises(RuntimeError) as excinfo:
        extractor.import_csv(use_incremental=False)

    # Error message should indicate expected vs found columns
    msg = str(excinfo.value)
    assert "expected" in msg.lower() and "columns" in msg.lower()


def test_extract_in_chunks_yields_expected_chunk_sizes(tmp_path: Path):
    """
    Import the sample fixture, then call extract_in_chunks with a small batch size
    and validate that chunks are yielded with lengths <= batch_size and that the
    total number of rows equals the table row count.
    """
    assert FIXTURE_CSV.exists(), f"Expected fixture CSV at {FIXTURE_CSV} to exist"

    db_path = tmp_path / "sbir_chunks.duckdb"
    extractor = SbirDuckDBExtractor(
        csv_path=FIXTURE_CSV, duckdb_path=str(db_path), table_name="sbir_chunks"
    )

    # Import CSV so table exists
    metadata = extractor.import_csv(use_incremental=False)
    total_rows = int(metadata["row_count"])
    assert total_rows == 3

    # Request chunks of size 2 -> expect two chunks (2, 1)
    chunks = list(extractor.extract_in_chunks(batch_size=2))
    assert len(chunks) >= 1
    assert all(len(chunk) <= 2 for chunk in chunks)

    # Total rows across all chunks must equal the metadata row count
    concatenated = pd.concat(chunks, ignore_index=True) if len(chunks) > 0 else pd.DataFrame()
    assert len(concatenated) == total_rows

    # Verify specific chunk sizing pattern (since fixture has 3 rows)
    lengths = [len(c) for c in chunks]
    assert lengths == [2, 1] or lengths == [
        3
    ]  # depending on pagination behavior, either one full or two pages

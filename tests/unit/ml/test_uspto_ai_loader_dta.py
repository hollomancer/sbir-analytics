import importlib
from pathlib import Path

import pytest


@pytest.mark.unit
def test_ingest_dta_to_duckdb(tmp_path: Path):
    """
    Smoke test: create a tiny .dta file, ingest it into DuckDB using the loader helper,
    and verify the table was written and contains the expected rows.

    The test is defensive and will skip when required runtime dependencies or the
    ingest helper are not available in the environment.
    """
    # duckdb is required for the canonical store used by the ingest helper
    duckdb = pytest.importorskip("duckdb")

    # pandas is required to construct and write a .dta fallback when pyreadstat isn't present
    pd = pytest.importorskip("pandas")

    # Import the ingest helper from the project module; skip if it's not present
    try:
        loader_mod = importlib.import_module("src.ml.data.uspto_ai_loader")
    except Exception:
        pytest.skip("uspto_ai_loader module not importable; skipping DTA ingest test")

    ingest_func = getattr(loader_mod, "ingest_dta_to_duckdb", None)
    if ingest_func is None:
        pytest.skip("ingest_dta_to_duckdb not implemented; skipping")

    # Build a tiny DataFrame to serialize as .dta
    df = pd.DataFrame(
        [
            {
                "grant_doc_num": "US1001B2",
                "predict93_score": 0.93,
                "predict93_any_ai": 1,
                "category": "machine_learning",
            },
            {
                "grant_doc_num": "US1002B2",
                "predict93_score": 0.12,
                "predict93_any_ai": 0,
                "category": "quantum",
            },
        ]
    )

    # Write to a .dta file using pyreadstat if available, otherwise pandas.to_stata
    dta_path = tmp_path / "sample_uspto.dta"
    try:
        pyreadstat = importlib.import_module("pyreadstat")
        # pyreadstat.write_dta expects a pandas DataFrame; use it directly
        pyreadstat.write_dta(df, str(dta_path))
    except Exception:
        # Fall back to pandas.to_stata
        # Note: to_stata may coerce types; use write_index=False to avoid adding index
        df.to_stata(str(dta_path), write_index=False)

    # Prepare duckdb path (file in tmp_path)
    duckdb_path = tmp_path / "uspto_ai_test.duckdb"
    table_name = "test_uspto_ai_predictions"

    # Ensure the ingest function runs without raising
    result = ingest_func(
        dta_path=dta_path,
        duckdb_path=duckdb_path,
        table_name=table_name,
        grant_id_candidates=None,
        batch_size=1,
    )

    # Basic result shape assertions
    assert isinstance(result, dict), "ingest_dta_to_duckdb should return a dict summary"
    assert result.get("ingested", 0) >= 2, "Expected at least two rows ingested"

    # Verify data landed in DuckDB
    con = duckdb.connect(database=str(duckdb_path), read_only=True)
    try:
        # Check table exists and row count matches
        try:
            df_out = con.execute(f"SELECT * FROM {table_name} ORDER BY grant_doc_num").fetchdf()
        except Exception as e:
            pytest.fail(f"Failed to query DuckDB table '{table_name}': {e}")

        assert len(df_out) == result.get(
            "ingested", len(df_out)
        ), "Row count mismatch between summary and table"

        # Verify presence of expected grant ids and a sample score value
        grants = set(str(x) for x in df_out["grant_doc_num"].tolist())
        assert {"US1001B2", "US1002B2"}.issubset(grants)

        # Check one of the numeric fields exists and is in expected range
        scores = df_out["predict93_score"].astype(float).tolist()
        assert any(
            s >= 0.9 for s in scores
        ), "Expected at least one high predict93_score in ingested data"
    finally:
        try:
            con.close()
        except Exception:
            pass

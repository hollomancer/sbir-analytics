import json
from types import SimpleNamespace
from pathlib import Path

import pandas as pd
import pytest
from dagster import build_asset_context

import src.assets.sbir_ingestion as assets_module


def _make_test_config(
    csv_path: str, db_path: str, table_name: str, pass_rate_threshold: float = 0.95
):
    """
    Create a minimal config object with the attributes the assets expect.
    Uses SimpleNamespace to mimic the nested Pydantic model used by get_config().
    """
    sbir = SimpleNamespace(
        csv_path=str(csv_path), database_path=str(db_path), table_name=table_name
    )
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=pass_rate_threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


def _fixture_csv_path():
    # Resolve absolute path to the fixture regardless of cwd
    # tests/integration/... -> parents[2] is repo root; fixture lives at tests/fixtures/sbir_sample.csv
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sbir_sample.csv"


def test_materialize_raw_validated_and_report_assets(tmp_path: Path, monkeypatch):
    """
    Integration-style test that exercises the three SBIR ingestion assets:
    - raw_sbir_awards
    - validated_sbir_awards
    - sbir_validation_report

    The test:
    - Points the assets' configuration to the sample CSV fixture and a temporary DuckDB file
    - Calls the asset functions directly using Dagster test contexts
    - Asserts that returned outputs have expected structure and that a validation report file is written
    """
    # Arrange: prepare fixture and temporary database path, and change cwd so report writes to tmp_path
    fixture_csv = _fixture_csv_path()
    assert fixture_csv.exists(), f"Expected fixture CSV at {fixture_csv}"

    db_path = tmp_path / "assets_test.duckdb"
    table_name = "sbir_assets_test"

    # Ensure the asset code writes report into tmp_path by changing cwd
    monkeypatch.chdir(tmp_path)

    # Build a minimal config object and monkeypatch get_config used in the assets module
    test_config = _make_test_config(
        csv_path=str(fixture_csv),
        db_path=str(db_path),
        table_name=table_name,
        pass_rate_threshold=0.0,
    )
    # Set threshold to 0.0 to ensure validation does not fail the asset check (makes assertions simpler)
    monkeypatch.setattr(assets_module, "get_config", lambda: test_config)

    # Act: materialize raw asset by calling the function with a Dagster test context
    raw_ctx = build_asset_context()
    raw_output = assets_module.raw_sbir_awards(context=raw_ctx)

    # raw_sbir_awards returns a Dagster Output wrapper in the implementation; the test should accept either pattern:
    # - If it's returning an Output from dagster, access .value; otherwise it may return DataFrame directly.
    raw_df = getattr(raw_output, "value", raw_output)

    # Assert basic properties of the raw extraction
    assert isinstance(raw_df, pd.DataFrame)
    assert len(raw_df) == 6  # fixture contains 6 rows

    # If metadata was returned via Output metadata, validate presence of extraction timestamps and columns
    metadata = getattr(raw_output, "metadata", None) or {}
    # The asset code stores metadata keys like 'extraction_start_utc', 'columns' etc.
    assert "extraction_start_utc" in metadata
    assert "extraction_end_utc" in metadata
    assert "columns" in metadata
    # columns should be a JSON-serializable string or object; attempt to parse if possible
    cols = metadata.get("columns")
    if isinstance(cols, str):
        try:
            parsed = json.loads(cols)
            assert isinstance(parsed, list)
        except Exception:
            # If not JSON, at least ensure a non-empty string was provided
            assert len(cols) > 0
    else:
        assert isinstance(cols, (list, tuple))

    # Act: run validation asset using the raw DataFrame
    validated_ctx = build_asset_context()
    validated_output = assets_module.validated_sbir_awards(
        context=validated_ctx, raw_sbir_awards=raw_df
    )
    validated_df = getattr(validated_output, "value", validated_output)

    # Assert validated asset returns a DataFrame and has <= rows than raw
    assert isinstance(validated_df, pd.DataFrame)
    assert len(validated_df) <= len(raw_df)

    # Act: generate validation report
    report_ctx = build_asset_context()
    report_output = assets_module.sbir_validation_report(context=report_ctx, raw_sbir_awards=raw_df)
    report = getattr(report_output, "value", report_output)

    # Assert the report structure and content
    assert isinstance(report, dict)
    assert report.get("total_records") == len(raw_df)
    assert "issues" in report and isinstance(report["issues"], list)

    # Assert that the report file was written to the expected relative path under the temp cwd
    report_path = Path("data") / "validated" / "sbir_validation_report.json"
    assert report_path.exists(), f"Expected validation report at {report_path}"

    # Load and validate the report JSON contents
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    assert report_data.get("total_records") == report.get("total_records")
    assert "issues_by_severity" in report_data
    assert "issues_by_field" in report_data

    # Cleanup: remove report file (test working dir is tmp_path, so safe to delete)
    report_path.unlink()
    # Optionally remove parent dirs if empty
    parent_dir = report_path.parent
    try:
        parent_dir.rmdir()
        (parent_dir.parent).rmdir()
    except Exception:
        # ignore if not empty or removal fails
        pass

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from dagster import build_asset_context

import sbir_analytics.assets.sbir_ingestion as assets_module


def _make_test_config(
    csv_path: str, db_path: str, table_name: str, pass_rate_threshold: float = 0.95
):
    """
    Create a minimal config object with the attributes the assets expect.
    Uses SimpleNamespace to mimic the nested Pydantic model used by get_config().
    """
    sbir = SimpleNamespace(
        csv_path=str(csv_path),
        database_path=str(db_path),
        table_name=table_name,
        csv_path_s3=None,
        use_s3_first=False,
    )
    extraction = SimpleNamespace(sbir=sbir)
    data_quality = SimpleNamespace(
        sbir_awards=SimpleNamespace(pass_rate_threshold=pass_rate_threshold)
    )
    return SimpleNamespace(extraction=extraction, data_quality=data_quality)


def test_materialize_raw_validated_and_report_assets(
    tmp_path: Path, monkeypatch, sbir_csv_path: Path
):
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
    # sbir_csv_path fixture automatically provides the right data source (sample or real)
    assert sbir_csv_path.exists(), f"Expected SBIR CSV at {sbir_csv_path}"

    db_path = tmp_path / "assets_test.duckdb"
    table_name = "sbir_assets_test"

    # Ensure the asset code writes report into tmp_path by changing cwd
    monkeypatch.chdir(tmp_path)

    # Build a minimal config object and monkeypatch get_config used in the assets module
    test_config = _make_test_config(
        csv_path=str(sbir_csv_path),
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
    assert len(raw_df) > 0  # Should have at least some rows (100 in sample, millions in real data)

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
        assert isinstance(cols, list | tuple)

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
    with open(report_path, encoding="utf-8") as f:
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


pytestmark = pytest.mark.integration


def test_reliability_manifest_written_by_pilot(
    tmp_path: Path, monkeypatch, sbir_csv_path: Path
):
    """Materialize validated_sbir_awards and assert the reliability manifest
    is written and MaterializationMetadata carries the three required keys."""
    assert sbir_csv_path.exists()

    db_path = tmp_path / "reliability_test.duckdb"
    monkeypatch.chdir(tmp_path)

    test_config = _make_test_config(
        csv_path=str(sbir_csv_path),
        db_path=str(db_path),
        table_name="sbir_reliability_test",
        pass_rate_threshold=0.0,
    )
    monkeypatch.setattr(assets_module, "get_config", lambda: test_config)

    raw_ctx = build_asset_context()
    raw_output = assets_module.raw_sbir_awards(context=raw_ctx)
    raw_df = getattr(raw_output, "value", raw_output)

    validated_ctx = build_asset_context()
    validated_output = assets_module.validated_sbir_awards(
        context=validated_ctx, raw_sbir_awards=raw_df
    )

    metadata = getattr(validated_output, "metadata", None) or {}
    assert "caveat_count" in metadata
    assert "resolved_caveat_count" in metadata
    assert "manifest_path" in metadata

    def _unwrap(v):
        return getattr(v, "value", v)

    caveat_count = _unwrap(metadata["caveat_count"])
    resolved_count = _unwrap(metadata["resolved_caveat_count"])
    manifest_path_value = _unwrap(metadata["manifest_path"])
    assert isinstance(caveat_count, int)
    assert isinstance(resolved_count, int)
    # Static qualitative caveat is always emitted, so there is at least one.
    assert caveat_count >= 1
    # First run has no prior manifest.
    assert resolved_count == 0

    manifest_path = Path(manifest_path_value)
    assert manifest_path.exists()
    assert manifest_path.parent == Path("reports/reliability/validated_sbir_awards")

    with open(manifest_path) as f:
        manifest = json.load(f)

    assert manifest["asset_name"] == "validated_sbir_awards"
    assert manifest["framework_reference"] == "GAO-20-283G"
    assert isinstance(manifest["caveats"], list)
    assert isinstance(manifest["provenance"], list)
    assert isinstance(manifest["resolved_caveats"], list)

    # Provenance was recorded from the upstream source stamp.
    assert len(manifest["provenance"]) == 1
    prov = manifest["provenance"][0]
    assert prov["source_id"] == "sbir_gov_bulk_download"
    assert prov["extractor_module"] == "sbir_etl.extractors.sbir"
    assert prov["row_count"] == len(raw_df)

    # Static qualitative caveat present.
    metric_names = {c["metric_name"] for c in manifest["caveats"]}
    assert "uei_missing_pre_2015_bifurcation" in metric_names


def test_reliability_manifest_cross_run_diff(
    tmp_path: Path, monkeypatch, sbir_csv_path: Path
):
    """Materialize the pilot twice with the caveat helper toggled between runs
    and assert the second run's resolved_caveats surfaces the metric absent on
    run 2. Uses filesystem renaming to give run 1 a distinct manifest filename,
    since build_asset_context in this Dagster version doesn't accept run_id and
    both invocations otherwise share run_id="EPHEMERAL".
    """
    assert sbir_csv_path.exists()

    db_path = tmp_path / "cross_run.duckdb"
    monkeypatch.chdir(tmp_path)

    test_config = _make_test_config(
        csv_path=str(sbir_csv_path),
        db_path=str(db_path),
        table_name="sbir_cross_run_test",
        pass_rate_threshold=0.0,
    )
    monkeypatch.setattr(assets_module, "get_config", lambda: test_config)

    original_emit = assets_module._emit_validation_caveats

    def emit_with_extra(collector, quality_report, filter_audit, raw_row_count):
        original_emit(collector, quality_report, filter_audit, raw_row_count)
        collector.emit_caveat(
            dimension="accuracy",
            metric_name="synthetic_test_caveat",
            observed_value=1,
            expected_value=0,
            description="synthetic",
            impact="test-only caveat",
        )

    def _unwrap(v):
        return getattr(v, "value", v)

    # Run 1: extra synthetic caveat emitted.
    monkeypatch.setattr(assets_module, "_emit_validation_caveats", emit_with_extra)
    raw_out = assets_module.raw_sbir_awards(context=build_asset_context())
    raw_df = raw_out.value
    run1_out = assets_module.validated_sbir_awards(
        context=build_asset_context(), raw_sbir_awards=raw_df
    )
    run1_manifest_path = Path(_unwrap((run1_out.metadata or {})["manifest_path"]))
    assert run1_manifest_path.exists()

    # Rename run 1's manifest so run 2 doesn't overwrite it (same EPHEMERAL run_id).
    run1_renamed = run1_manifest_path.parent / "run1-prior.json"
    run1_manifest_path.rename(run1_renamed)

    # Run 2: restore original helper -> synthetic_test_caveat should now resolve.
    monkeypatch.setattr(assets_module, "_emit_validation_caveats", original_emit)
    run2_out = assets_module.validated_sbir_awards(
        context=build_asset_context(), raw_sbir_awards=raw_df
    )
    run2_meta = getattr(run2_out, "metadata", None) or {}
    assert _unwrap(run2_meta["resolved_caveat_count"]) >= 1

    with open(_unwrap(run2_meta["manifest_path"])) as f:
        run2_manifest = json.load(f)
    resolved_metric_names = {c["metric_name"] for c in run2_manifest["resolved_caveats"]}
    assert "synthetic_test_caveat" in resolved_metric_names

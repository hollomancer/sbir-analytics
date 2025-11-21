import csv
from pathlib import Path

import pytest


pytest.importorskip("dagster")
from dagster import build_asset_context


pytest.importorskip("pandas")

transformation_assets = pytest.importorskip(
    "src.assets.uspto", reason="uspto assets module missing"
)


pytestmark = pytest.mark.fast


def _get_compute_fn(asset_def):
    """Helper to get the underlying compute function from an asset definition."""
    # Try different ways to access the compute function depending on Dagster version
    if hasattr(asset_def, "node_def") and hasattr(asset_def.node_def, "compute_fn"):
        fn = asset_def.node_def.compute_fn
        # Unwrap if it's a DecoratedOpFunction
        if hasattr(fn, "decorated_fn"):
            return fn.decorated_fn
        return fn
    elif hasattr(asset_def, "compute_fn"):
        fn = asset_def.compute_fn
        if hasattr(fn, "decorated_fn"):
            return fn.decorated_fn
        return fn
    elif hasattr(asset_def, "op") and hasattr(asset_def.op, "compute_fn"):
        fn = asset_def.op.compute_fn
        if hasattr(fn, "decorated_fn"):
            return fn.decorated_fn
        return fn
    else:
        # If it's already a function, return it directly
        return asset_def


def _write_csv(tmp_path: Path, name: str, rows):
    path = tmp_path / name
    headers = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return str(path)


def test_transformation_assets_pipeline(tmp_path: Path):
    assignment_path = _write_csv(
        tmp_path,
        "assignment.csv",
        [
            {
                "rf_id": "RF1",
                "file_id": "F001",
                "record_dt": "2023-01-01",
                "convey_text": "Assignment of rights",
                "reel_no": 10,
                "frame_no": 20,
                "cname": "Example Correspondent",
            }
        ],
    )
    assignee_path = _write_csv(
        tmp_path,
        "assignee.csv",
        [
            {
                "rf_id": "RF1",
                "ee_name": "Acme Corp",
                "ee_address_1": "123 Main St",
                "ee_city": "Springfield",
                "ee_state": "IL",
                "ee_postcode": "62704",
                "ee_country": "US",
            }
        ],
    )
    assignor_path = _write_csv(
        tmp_path,
        "assignor.csv",
        [
            {
                "rf_id": "RF1",
                "or_name": "John Smith",
                "exec_dt": "2022-12-15",
                "ack_dt": "2022-12-20",
            }
        ],
    )
    document_path = _write_csv(
        tmp_path,
        "document.csv",
        [
            {
                "rf_id": "RF1",
                "grant_doc_num": "PAT123",
                "appno_doc_num": "APP123",
                "appno_date": "2022-01-01",
                "grant_date": "2023-08-01",
                "title": "Widget",
                "lang": "EN",
            }
        ],
    )
    conveyance_path = _write_csv(
        tmp_path,
        "conveyance.csv",
        [{"rf_id": "RF1", "convey_ty": "assignment", "employer_assign": True}],
    )

    assignment_ctx = build_asset_context()
    # Mock add_output_metadata since it's not available when calling directly
    assignment_ctx.add_output_metadata = lambda x: None

    # Access underlying compute function when Dagster is installed
    transformed_assignments_fn = _get_compute_fn(
        transformation_assets.transformed_patent_assignments
    )
    transformed_result = transformed_assignments_fn(
        assignment_ctx,
        [assignment_path],
        [assignee_path],
        [assignor_path],
        [document_path],
        [conveyance_path],
        {"overall_success": True},
    )

    assert transformed_result["success_count"] == 1
    assert Path(transformed_result["output_path"]).exists()
    assert transformed_result["error_count"] == 0

    patents_ctx = build_asset_context()
    patents_ctx.add_output_metadata = lambda x: None
    patents_fn = _get_compute_fn(transformation_assets.transformed_patents)
    patents_result = patents_fn(patents_ctx, transformed_result)
    assert patents_result["patent_count"] == 1

    entities_ctx = build_asset_context()
    entities_ctx.add_output_metadata = lambda x: None
    entities_fn = _get_compute_fn(transformation_assets.transformed_patent_entities)
    entities_result = entities_fn(entities_ctx, transformed_result)
    assert entities_result["entity_count"] >= 1

    success_check_fn = _get_compute_fn(transformation_assets.uspto_transformation_success_check)
    success_check = success_check_fn(build_asset_context(), transformed_result)
    assert success_check.passed is True

    linkage_check_fn = _get_compute_fn(transformation_assets.uspto_company_linkage_check)
    linkage_check = linkage_check_fn(build_asset_context(), transformed_result)
    # No SBIR linkage data provided, so expect the linkage check to fail (coverage < target)
    assert linkage_check.passed is False

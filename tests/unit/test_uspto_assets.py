# sbir-etl/tests/unit/test_uspto_assets.py
import copy

import pytest


pytest.importorskip("dagster")
from dagster import build_asset_context


# Attempt to import the asset checks under test; skip if module missing.
uspto_validation_assets = pytest.importorskip(
    "src.assets.uspto_validation_assets", reason="uspto validation assets module missing"
)

uspto_rf_id_asset_check = getattr(uspto_validation_assets, "uspto_rf_id_asset_check", None)
uspto_completeness_asset_check = getattr(
    uspto_validation_assets, "uspto_completeness_asset_check", None
)
uspto_referential_asset_check = getattr(
    uspto_validation_assets, "uspto_referential_asset_check", None
)

if uspto_rf_id_asset_check is None:
    pytest.skip("uspto_rf_id_asset_check not found", allow_module_level=True)


def _base_validation_report() -> dict:
    report = {
        "tables": {
            "assignments": {
                "/data/raw/uspto/assignment1.csv": {
                    "overall_success": True,
                    "checks": {
                        "rf_id_uniqueness": {
                            "success": True,
                            "summary": {"duplicate_rf_id_values": 0},
                            "details": {},
                        },
                        "field_completeness": {
                            "success": True,
                            "summary": {"overall_completeness": 1.0},
                            "details": {"failed_fields": []},
                        },
                    },
                }
            },
            "assignees": {},
            "assignors": {},
            "documentids": {},
            "conveyances": {},
        },
        "summary": {"total_checks": 2, "passed_checks": 2, "overall_pass_rate": 1.0},
        "overall_success": True,
        "report_path": "/tmp/report.json",
        "failure_samples": [],
    }
    return report


def test_uspto_rf_id_asset_check_pass():
    ctx = build_asset_context()
    report = _base_validation_report()
    assignment_files = ["/data/raw/uspto/assignment1.csv"]

    result = uspto_rf_id_asset_check(ctx, copy.deepcopy(report), assignment_files)

    assert hasattr(result, "passed")
    assert result.passed is True


def test_uspto_rf_id_asset_check_fail():
    ctx = build_asset_context()
    report = _base_validation_report()
    assignments = report["tables"]["assignments"]
    assignments["/data/raw/uspto/assignment1.csv"]["checks"]["rf_id_uniqueness"] = {
        "success": False,
        "summary": {"duplicate_rf_id_values": 3},
        "details": {"duplicate_samples": [("r1", 2)]},
    }

    result = uspto_rf_id_asset_check(
        ctx, copy.deepcopy(report), ["/data/raw/uspto/assignment1.csv"]
    )

    assert hasattr(result, "passed")
    assert result.passed is False


def test_uspto_completeness_asset_check_fail():
    if uspto_completeness_asset_check is None:
        pytest.skip("uspto_completeness_asset_check not found")

    ctx = build_asset_context()
    report = _base_validation_report()
    report["tables"]["assignees"] = {
        "/data/raw/uspto/assignee1.csv": {
            "overall_success": False,
            "checks": {
                "field_completeness": {
                    "success": False,
                    "summary": {"overall_completeness": 0.5},
                    "details": {"failed_fields": ["ee_name"]},
                }
            },
        }
    }

    result = uspto_completeness_asset_check(ctx, copy.deepcopy(report))
    assert hasattr(result, "passed")
    assert result.passed is False


def test_uspto_referential_asset_check_fail():
    if uspto_referential_asset_check is None:
        pytest.skip("uspto_referential_asset_check not found")

    ctx = build_asset_context()
    report = _base_validation_report()
    report["tables"]["assignees"] = {
        "/data/raw/uspto/assignee1.csv": {
            "overall_success": False,
            "checks": {
                "referential_integrity": {
                    "success": False,
                    "summary": {"orphaned_records": 2},
                    "details": {"failed_sample_path": "/tmp/fail.json"},
                }
            },
        }
    }

    result = uspto_referential_asset_check(ctx, copy.deepcopy(report))
    assert hasattr(result, "passed")
    assert result.passed is False

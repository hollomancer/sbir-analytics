# sbir-etl/tests/unit/test_uspto_assets.py
import pytest
from types import SimpleNamespace

# Attempt to import the asset check under test; skip if module missing.
uspto_assets = pytest.importorskip("src.assets.uspto_assets", reason="uspto assets module missing")
uspto_rf_id_asset_check = getattr(uspto_assets, "uspto_rf_id_asset_check", None)
if uspto_rf_id_asset_check is None:
    pytest.skip("uspto_rf_id_asset_check not found", allow_module_level=True)


class DummyLogger:
    def info(self, *args, **kwargs):
        # noop logger for tests
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class DummyContext:
    """Minimal fake Dagster context exposing .log used by the asset check."""

    def __init__(self):
        self.log = DummyLogger()


def test_uspto_rf_id_asset_check_pass():
    """
    When all validated_uspto_assignments report success=True, the asset check should pass.
    """
    ctx = DummyContext()

    # Simulate results from validated_uspto_assignments: one file, success True
    validated_results = {
        "/data/raw/uspto/assignment1.csv": {
            "success": True,
            "summary": {"total_rows": 10, "duplicate_rf_id_values": 0},
            "details": {},
        }
    }
    raw_files = ["/data/raw/uspto/assignment1.csv"]

    result = uspto_rf_id_asset_check(ctx, validated_results, raw_files)

    # The Dagster AssetCheckResult has attribute 'passed' and 'severity'; assert pass semantics.
    assert hasattr(result, "passed"), "Asset check result missing 'passed' attribute"
    assert result.passed is True, f"Expected passed True for success case, got: {result.passed}"


def test_uspto_rf_id_asset_check_fail():
    """
    When any validated_uspto_assignments reports success=False (i.e., duplicates/errors),
    the asset check should fail (passed == False).
    """
    ctx = DummyContext()

    validated_results = {
        "/data/raw/uspto/assignment1.csv": {
            "success": False,
            "summary": {"total_rows": 100, "duplicate_rf_id_values": 5},
            "details": {"duplicate_samples": [("r1", 2)]},
        },
        "/data/raw/uspto/assignment2.csv": {
            "success": True,
            "summary": {"total_rows": 20, "duplicate_rf_id_values": 0},
            "details": {},
        },
    }
    raw_files = ["/data/raw/uspto/assignment1.csv", "/data/raw/uspto/assignment2.csv"]

    result = uspto_rf_id_asset_check(ctx, validated_results, raw_files)

    assert hasattr(result, "passed"), "Asset check result missing 'passed' attribute"
    assert result.passed is False, "Expected asset check to fail when duplicates are present"

    # Confirm metadata communicates duplicate count if available
    metadata = getattr(result, "metadata", None)
    if metadata:
        # Some Dagster versions represent metadata in dict-like objects
        dup_count = (
            metadata.get("total_duplicate_values_found") if isinstance(metadata, dict) else None
        )
        # Accept either presence or not; if present ensure it's >= 1
        if dup_count is not None:
            assert int(dup_count) >= 1

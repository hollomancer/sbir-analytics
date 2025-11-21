import json
from pathlib import Path

import pandas as pd  # noqa: F401  # kept for parity with other transition tests using pandas
import pytest


pytestmark = pytest.mark.fast


def _write_checks(path: Path, award, company) -> None:
    """
    Helper to write a minimal transition_analytics.checks.json payload
    that the asset check expects to consume.
    """
    payload = {
        "ok": True,
        "generated_at": "2024-01-01T00:00:00Z",
        "score_threshold": 0.6,
        "award_transition_rate": award,
        "company_transition_rate": company,
        "counts": {
            "total_awards": int(award.get("denominator") or 0),
            "transitioned_awards": int(award.get("numerator") or 0),
            "total_companies": int(company.get("denominator") or 0),
            "companies_transitioned": int(company.get("numerator") or 0),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_transition_analytics_quality_check_passes_with_valid_rates(monkeypatch, tmp_path):
    # Arrange: chdir into an isolated tmp working directory
    monkeypatch.chdir(tmp_path)

    # Import the asset check and a context logger shim (import-safe without Dagster)
    from src.assets.transition import transition_analytics_quality_check  # type: ignore

    # Write a valid checks JSON with positive denominators and rates within [0,1]
    checks_path = Path("data/processed/transition_analytics.checks.json")
    _write_checks(
        checks_path,
        award={"numerator": 2, "denominator": 4, "rate": 0.5},
        company={"numerator": 1, "denominator": 3, "rate": 1 / 3},
    )

    # Ensure no minimum thresholds are enforced by env
    monkeypatch.delenv("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", raising=False)
    monkeypatch.delenv("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", raising=False)

    # Act
    pytest.importorskip("dagster")
    from dagster import build_asset_context  # noqa: PLC0415

    ctx = build_asset_context()
    # Access underlying compute function when Dagster is installed
    check_asset = transition_analytics_quality_check
    if hasattr(check_asset, "node_def") and hasattr(check_asset.node_def, "compute_fn"):
        check_fn = check_asset.node_def.compute_fn
    elif hasattr(check_asset, "compute_fn"):
        check_fn = check_asset.compute_fn
    else:
        check_fn = check_asset
    result = check_fn(ctx)

    # Assert
    assert hasattr(result, "passed")
    assert bool(result.passed) is True


def test_transition_analytics_quality_check_fails_with_min_thresholds(monkeypatch, tmp_path):
    # Arrange
    monkeypatch.chdir(tmp_path)
    from src.assets.transition import transition_analytics_quality_check  # type: ignore

    checks_path = Path("data/processed/transition_analytics.checks.json")
    # Rates are below the thresholds we'll set next
    _write_checks(
        checks_path,
        award={"numerator": 2, "denominator": 5, "rate": 0.40},  # 40%
        company={"numerator": 3, "denominator": 10, "rate": 0.30},  # 30%
    )

    # Enforce minimum thresholds that are higher than rates above
    monkeypatch.setenv("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", "0.50")
    monkeypatch.setenv("SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE", "0.40")

    # Act
    pytest.importorskip("dagster")
    from dagster import build_asset_context  # noqa: PLC0415

    ctx = build_asset_context()
    # Access underlying compute function when Dagster is installed
    check_asset = transition_analytics_quality_check
    if hasattr(check_asset, "node_def") and hasattr(check_asset.node_def, "compute_fn"):
        check_fn = check_asset.node_def.compute_fn
    elif hasattr(check_asset, "compute_fn"):
        check_fn = check_asset.compute_fn
    else:
        check_fn = check_asset
    result = check_fn(ctx)

    # Assert
    assert hasattr(result, "passed")
    assert bool(result.passed) is False
    # Soft assertion on description to ensure helpful message formatting
    assert "award_rate" in (getattr(result, "description", "") or "")
    assert "company_rate" in (getattr(result, "description", "") or "")


def test_transition_analytics_quality_check_fails_on_zero_denominators(monkeypatch, tmp_path):
    # Arrange
    monkeypatch.chdir(tmp_path)
    from src.assets.transition import transition_analytics_quality_check  # type: ignore

    checks_path = Path("data/processed/transition_analytics.checks.json")
    # Zero denominators should cause the check to fail
    _write_checks(
        checks_path,
        award={"numerator": 0, "denominator": 0, "rate": 0.0},
        company={"numerator": 0, "denominator": 0, "rate": 0.0},
    )

    # Act
    pytest.importorskip("dagster")
    from dagster import build_asset_context  # noqa: PLC0415

    ctx = build_asset_context()
    # Access underlying compute function when Dagster is installed
    check_asset = transition_analytics_quality_check
    if hasattr(check_asset, "node_def") and hasattr(check_asset.node_def, "compute_fn"):
        check_fn = check_asset.node_def.compute_fn
    elif hasattr(check_asset, "compute_fn"):
        check_fn = check_asset.compute_fn
    else:
        check_fn = check_asset
    result = check_fn(ctx)

    # Assert
    assert hasattr(result, "passed")
    assert bool(result.passed) is False

"""Hermetic execution tests for the operated CET analytics assets."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.cet.analytics import (
    transformed_cet_analytics,
    transformed_cet_analytics_aggregates,
)


pytestmark = pytest.mark.fast


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def test_analytics_uses_ndjson_fallback_and_emits_successful_metrics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    processed_dir = tmp_path / "data/processed"
    _write_ndjson(
        processed_dir / "cet_award_classifications.ndjson",
        [
            {"award_id": "A-1", "primary_cet": "quantum", "primary_score": 0.9},
            {"award_id": "A-2", "primary_cet": "biotech", "primary_score": 0.8},
        ],
    )
    _write_ndjson(
        processed_dir / "cet_company_profiles.ndjson",
        [
            {"company_id": "C-1", "specialization_score": 0.25},
            {"company_id": "C-2", "specialization_score": 0.75},
            {"company_id": "C-3", "specialization_score": None},
        ],
    )
    (processed_dir / "cet_award_classifications.parquet").write_text("broken")
    (processed_dir / "cet_company_profiles.parquet").write_text("broken")

    def fail_parquet_read(*_args, **_kwargs):
        raise OSError("synthetic parquet failure")

    monkeypatch.setattr(pd, "read_parquet", fail_parquet_read)

    result = transformed_cet_analytics()

    assert result.value["coverage_rate"] == pytest.approx(1.0)
    assert result.value["num_awards"] == 2
    assert result.value["num_classified"] == 2
    assert result.value["company_specialization_avg"] == pytest.approx(0.5)

    checks_path = tmp_path / result.value["checks_path"]
    checks = _read_json(checks_path)
    assert checks["ok"] is True
    assert checks["award_coverage_rate"] == pytest.approx(1.0)
    assert checks["alerts"]["alert_count"] == 0
    assert _read_json(tmp_path / result.value["alerts_path"]) == checks["alerts"]


def test_analytics_empty_input_emits_zero_metrics_and_failed_coverage_check(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = transformed_cet_analytics()

    assert result.value["coverage_rate"] == 0.0
    assert result.value["num_awards"] == 0
    assert result.value["num_classified"] == 0
    assert result.value["company_specialization_avg"] is None

    checks = _read_json(tmp_path / result.value["checks_path"])
    assert checks["award_coverage_rate"] == 0.0
    assert checks["alerts"]["failure_count"] == 1
    assert checks["alerts"]["alerts"][0]["metric_name"] == "cet_award_coverage_rate"


def test_analytics_aggregates_write_dashboards_and_regression_alert(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    processed_dir = tmp_path / "data/processed"
    _write_ndjson(
        processed_dir / "cet_award_classifications.ndjson",
        [
            {"award_id": "A-1", "primary_cet": "quantum", "classified_at": "2024-01-01"},
            {"award_id": "A-2", "primary_cet": None, "classified_at": "2024-06-01"},
            {"award_id": "A-3", "primary_cet": "biotech", "classified_at": "2025-01-01"},
            {"award_id": "A-4", "primary_cet": None, "classified_at": "2025-06-01"},
            {"award_id": "A-5", "primary_cet": "space", "classified_at": "not-a-date"},
        ],
    )
    _write_ndjson(
        processed_dir / "cet_company_profiles.ndjson",
        [
            {"company_id": "C-1", "specialization_score": 0.1},
            {"company_id": "C-2", "specialization_score": 0.3},
            {"company_id": "C-3", "specialization_score": 0.6},
            {"company_id": "C-4", "specialization_score": 0.9},
        ],
    )
    baseline_path = tmp_path / "reports/benchmarks/baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({"cet": {"coverage_min": 0.75}}), encoding="utf-8")

    result = transformed_cet_analytics_aggregates()

    assert result.value["latest_year"] == 2025
    assert result.value["latest_coverage_rate"] == pytest.approx(0.5)
    assert result.value["total_awards"] == 5
    assert result.value["total_classified"] == 3
    assert result.value["specialization_avg"] == pytest.approx(0.475)

    coverage_rows = _read_json(tmp_path / result.value["coverage_dashboard_json"])
    coverage_by_year = {row["__year"]: row for row in coverage_rows}
    assert coverage_by_year["2025"]["coverage_rate"] == pytest.approx(0.5)
    assert coverage_by_year["unknown"]["classified"] == 1

    specialization_rows = _read_json(tmp_path / result.value["specialization_dashboard_json"])
    assert sum(row["count"] for row in specialization_rows) == 4

    alerts = _read_json(tmp_path / result.value["alerts_path"])
    assert alerts["failure_count"] == 1
    assert alerts["alerts"][0]["metric_name"] == "cet_award_latest_year_coverage"


def test_analytics_aggregates_empty_input_returns_empty_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = transformed_cet_analytics_aggregates()

    assert result.value["latest_year"] is None
    assert result.value["latest_coverage_rate"] is None
    assert result.value["total_awards"] == 0
    assert result.value["total_classified"] == 0
    assert result.value["specialization_avg"] is None
    assert not (tmp_path / result.value["coverage_dashboard_json"]).exists()
    assert not (tmp_path / result.value["specialization_dashboard_json"]).exists()
    assert _read_json(tmp_path / result.value["alerts_path"])["alert_count"] == 0

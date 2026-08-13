"""Hermetic execution tests for the operated CET validation assets."""

import json
from pathlib import Path

import pytest

from sbir_analytics.assets.cet.validation import (
    raw_cet_human_sampling,
    validated_cet_drift_detection,
    validated_cet_iaa_report,
)


pytestmark = pytest.mark.fast


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")


def _read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def test_human_sampling_balances_labels_and_tops_up_deterministically(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__CET__SAMPLE_SIZE", "4")
    monkeypatch.setenv("SBIR_ETL__CET__SAMPLE_SEED", "7")
    input_path = tmp_path / "data/processed/cet_award_classifications.ndjson"
    _write_ndjson(
        input_path,
        [
            {"award_id": "A-1", "primary_cet": "quantum", "primary_score": 0.9},
            {"award_id": "A-2", "primary_cet": "quantum", "primary_score": 0.8},
            {"award_id": "A-3", "primary_cet": "biotech", "primary_score": 0.7},
            {"award_id": "A-4", "primary_cet": "biotech", "primary_score": 0.6},
            {"award_id": "A-5", "primary_cet": "space", "primary_score": 0.5},
            {"award_id": "A-6", "primary_cet": "space", "primary_score": 0.4},
        ],
    )

    result = raw_cet_human_sampling()

    sample_path = tmp_path / result.value
    sampled = [json.loads(line) for line in sample_path.read_text().splitlines()]
    assert len(sampled) == 4
    assert len({row["award_id"] for row in sampled}) == 4
    assert {row["primary_cet"] for row in sampled} == {"quantum", "biotech", "space"}

    checks = _read_json(tmp_path / "data/processed/cet_human_sample.checks.json")
    assert checks == {
        "ok": True,
        "total_rows": 6,
        "sampled_rows": 4,
        "balanced_by_primary": True,
        "seed": 7,
        "source": "data/processed/cet_award_classifications.ndjson",
    }


def test_human_sampling_empty_input_writes_empty_artifact_and_checks(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/processed").mkdir(parents=True)

    result = raw_cet_human_sampling()

    assert (tmp_path / result.value).read_text(encoding="utf-8") == ""
    checks = _read_json(tmp_path / "data/processed/cet_human_sample.checks.json")
    assert checks["reason"] == "no_input"
    assert checks["total_rows"] == 0
    assert checks["sampled_rows"] == 0


def test_human_sampling_propagates_malformed_ndjson(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    input_path = tmp_path / "data/processed/cet_award_classifications.ndjson"
    input_path.parent.mkdir(parents=True)
    input_path.write_text('{"award_id": "A-1"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        raw_cet_human_sampling()

    assert not (tmp_path / "data/processed/cet_human_sample.ndjson").exists()
    assert not (tmp_path / "data/processed/cet_human_sample.checks.json").exists()


def test_iaa_report_computes_pairwise_kappa_and_exact_set_agreement(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_ndjson(
        tmp_path / "data/processed/annotations/review.ndjson",
        [
            {"award_id": "A-1", "annotator": "alice", "labels": ["quantum", "ai"]},
            {"award_id": "A-1", "annotator": "bob", "labels": ["ai", "quantum"]},
            {"award_id": "A-2", "annotator": "alice", "labels": ["biotech"]},
            {"award_id": "A-2", "annotator": "bob", "labels": ["biotech"]},
            {"award_id": "A-3", "annotator": "alice", "labels": ["space"]},
            {"award_id": "A-3", "annotator": "bob", "labels": ["cyber"]},
        ],
    )

    result = validated_cet_iaa_report()

    payload = _read_json(tmp_path / result.value)
    assert payload["ok"] is True
    assert payload["pairs"] == 1
    assert payload["kappa"]["alice__vs__bob"] == pytest.approx(0.25)
    assert payload["percent_agreement"] == pytest.approx(2 / 3)


def test_iaa_report_skips_malformed_files_and_reports_no_annotations(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    annotations_dir = tmp_path / "data/processed/annotations"
    annotations_dir.mkdir(parents=True)
    (annotations_dir / "broken.jsonl").write_text("not-json\n", encoding="utf-8")
    (annotations_dir / "ignored.txt").write_text("also-not-json\n", encoding="utf-8")

    result = validated_cet_iaa_report()

    payload = _read_json(tmp_path / result.value)
    assert payload["reason"] == "no_annotations"
    assert payload["pairs"] == 0
    assert payload["percent_agreement"] is None


def test_drift_detection_empty_input_writes_no_input_report(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__CET__DRIFT__SCORE_JS_THRESHOLD", "0.25")
    monkeypatch.setenv("SBIR_ETL__CET__DRIFT__LABEL_JS_THRESHOLD", "0.125")

    result = validated_cet_drift_detection()

    assert result.value["reason"] == "no_input"
    assert result.value["score_js_divergence"] is None
    assert result.value["label_js_divergence"] is None
    assert result.value["score_threshold"] == pytest.approx(0.25)
    assert result.value["label_threshold"] == pytest.approx(0.125)
    report = _read_json(tmp_path / "reports/benchmarks/cet_drift_report.json")
    assert report["reason"] == "no_input"


def test_drift_detection_without_baseline_writes_candidate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_ndjson(
        tmp_path / "data/processed/cet_award_classifications.ndjson",
        [
            {"award_id": "A-1", "primary_cet": "quantum", "primary_score": "5"},
            {"award_id": "A-2", "primary_cet": None, "primary_score": 95},
        ],
    )

    result = validated_cet_drift_detection()

    assert result.value["reason"] == "baseline_missing"
    candidate_path = tmp_path / result.value["candidate_path"]
    candidate = _read_json(candidate_path)
    assert candidate["label_pmf"] == {"quantum": 0.5, "__none__": 0.5}
    assert candidate["score_pmf"]["0-10"] == pytest.approx(0.5)
    assert candidate["score_pmf"]["90-100"] == pytest.approx(0.5)
    assert not (tmp_path / "reports/alerts/cet_drift_alerts.json").exists()


def test_drift_detection_emits_failure_for_large_label_shift(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__CET__DRIFT__SCORE_JS_THRESHOLD", "0.15")
    monkeypatch.setenv("SBIR_ETL__CET__DRIFT__LABEL_JS_THRESHOLD", "0.10")
    _write_ndjson(
        tmp_path / "data/processed/cet_award_classifications.ndjson",
        [
            {"award_id": "A-1", "primary_cet": "quantum", "primary_score": 5},
            {"award_id": "A-2", "primary_cet": "quantum", "primary_score": 5},
        ],
    )
    baseline_path = tmp_path / "reports/benchmarks/cet_baseline_distributions.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "label_pmf": {"biotech": 1.0},
                "score_pmf": {"0-10": 1.0},
            }
        ),
        encoding="utf-8",
    )

    result = validated_cet_drift_detection()

    assert result.value["label_js_divergence"] == pytest.approx(1.0)
    assert result.value["score_js_divergence"] == pytest.approx(0.0)
    alerts = _read_json(tmp_path / "reports/alerts/cet_drift_alerts.json")
    assert alerts["alert_count"] == 1
    assert alerts["failure_count"] == 1
    assert alerts["alerts"][0]["severity"] == "FAILURE"
    assert alerts["alerts"][0]["alert_type"] == "label_distribution_drift"

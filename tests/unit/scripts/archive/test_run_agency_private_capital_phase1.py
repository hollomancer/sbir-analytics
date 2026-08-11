"""Regression tests for the standalone Phase 1 real-data runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "archive" / "data" / "run_agency_private_capital_phase1.py"
SPEC = importlib.util.spec_from_file_location("run_agency_private_capital_phase1", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_ma_event_loader_uses_versioned_organization_name_key(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"company_name": "Acme Research, Inc."}\n', encoding="utf-8")

    assert MODULE._load_ma_event_companies(events_path) == {"name:acme research"}


def test_committed_review_report_is_bound_to_manifest_results_and_hash() -> None:
    manifest_path = (
        REPO_ROOT / "docs" / "research" / "agency-private-capital-phase1-nsf.manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    review = manifest["review_artifact"]
    report_path = REPO_ROOT / review["path"]

    assert MODULE._sha256_file(report_path) == review["sha256"]
    assert report_path.stat().st_size == review["size_bytes"]
    assert manifest["results"]["headline_graduation"] == {
        "available": True,
        "ci_high": pytest.approx(0.4726517838014854),
        "ci_low": pytest.approx(0.42242349183627115),
        "denominator": 1502,
        "horizon_years": 5,
        "numerator": 672,
        "rate": pytest.approx(0.4474034620505992),
        "vintage_bucket": "2015-2019",
    }
    report = report_path.read_text(encoding="utf-8")
    assert "| 5 years | 672 | 1,502 | 44.7% |" in report
    assert "1,160 UEI-backed" in report
    assert "326 DUNS-backed" in report
    assert "16 normalized-name-only" in report


def test_runner_emits_deterministic_portable_manifest_and_labeled_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    awards_path = tmp_path / "sbir_awards.csv"
    pd.DataFrame(
        [
            {
                "Company": "Acme",
                "Agency": "National Science Foundation",
                "Phase": "Phase I",
                "Award Year": "2015",
                "UEI": "ACME00000001",
            },
            {
                "Company": "Acme",
                "Agency": "National Science Foundation",
                "Phase": "Phase II",
                "Award Year": "2017",
                "UEI": "ACME00000001",
            },
        ]
    ).to_csv(awards_path, index=False)
    missing_ma_path = tmp_path / "missing_ma_events.jsonl"
    registry_path = REPO_ROOT / "config" / "agency_private_capital" / "published_baselines.yaml"

    manifests: list[str] = []
    for output_name in ("first", "second"):
        output_dir = tmp_path / output_name
        monkeypatch.setattr(
            sys,
            "argv",
            [
                str(SCRIPT_PATH),
                "--awards-csv",
                str(awards_path),
                "--ma-events",
                str(missing_ma_path),
                "--registry",
                str(registry_path),
                "--output-dir",
                str(output_dir),
                "--run-date",
                "2026-08-11",
                "--awards-retrieved-at",
                "2026-08-10",
                "--skip-download",
            ],
        )

        assert MODULE.main() == 0
        manifests.append((output_dir / "run_manifest.json").read_text(encoding="utf-8"))

        report = (output_dir / "agency_vs_published_baselines.md").read_text(encoding="utf-8")
        assert "**Exploratory / non-citable.**" in report
        assert "**Phase I -> Phase II graduation horizon:** 5 years." in report
        assert "**Unavailable metrics in this run:**" in report
        assert "`phase_ii_to_federal_contract_transition`" in report
        assert "`five_year_survival_proxy`" in report
        assert "`ma_exit_rate`" in report
        assert "`patent_rate`" in report
        assert "## Graduation-horizon sensitivity" in report
        assert "| Unbounded | 1 | 1 | 100.0% |" in report
        assert "## Entity-resolution coverage" in report

    assert manifests[0] == manifests[1]
    payload = json.loads(manifests[0])
    assert payload["schema_version"] == 2
    assert payload["epistemic_tier"] == "exploratory"
    assert payload["citable"] is False
    assert payload["run_date"] == "2026-08-11"
    assert payload["parameters"]["graduation_horizon_years"] == 5
    assert payload["inputs"]["awards_csv"]["path"] == awards_path.name
    assert payload["inputs"]["awards_csv"]["row_count"] == 2
    assert payload["inputs"]["awards_csv"]["size_bytes"] == awards_path.stat().st_size
    assert len(payload["inputs"]["awards_csv"]["sha256"]) == 64
    assert payload["inputs"]["awards_csv"]["source_url"] == MODULE.SBIR_AWARDS_CSV_URL
    assert payload["inputs"]["awards_csv"]["retrieved_at"] == "2026-08-10"
    assert payload["inputs"]["awards_csv"]["retrieved_at_basis"] == "provided"
    assert payload["inputs"]["ma_events_jsonl"]["available"] is False
    assert payload["results"]["headline_graduation"]["numerator"] == 1
    assert payload["results"]["headline_graduation"]["denominator"] == 1
    assert [
        row["horizon_years"] for row in payload["results"]["graduation_horizon_sensitivity"]
    ] == [2, 3, 5, None]
    assert payload["results"]["identity_coverage"]["company_basis_counts"] == {
        "duns": 0,
        "name": 0,
        "uei": 1,
    }
    assert set(payload["outputs"]) == {
        "agency_baseline_comparison_json",
        "agency_cohort_outcomes_parquet",
        "agency_vs_published_baselines_markdown",
    }
    assert all(len(output["sha256"]) == 64 for output in payload["outputs"].values())
    assert str(tmp_path) not in manifests[0]
    assert "generated_at" not in payload

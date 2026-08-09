"""Regression tests for the standalone Phase 1 real-data runner."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "archive" / "data" / "run_agency_private_capital_phase1.py"
SPEC = importlib.util.spec_from_file_location("run_agency_private_capital_phase1", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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

    assert manifests[0] == manifests[1]
    payload = json.loads(manifests[0])
    assert payload["schema_version"] == 1
    assert payload["epistemic_tier"] == "exploratory"
    assert payload["citable"] is False
    assert payload["parameters"]["graduation_horizon_years"] == 5
    assert payload["inputs"]["awards_csv"]["path"] == awards_path.name
    assert payload["inputs"]["awards_csv"]["row_count"] == 2
    assert payload["inputs"]["awards_csv"]["size_bytes"] == awards_path.stat().st_size
    assert len(payload["inputs"]["awards_csv"]["sha256"]) == 64
    assert payload["inputs"]["ma_events_jsonl"]["available"] is False
    assert str(tmp_path) not in manifests[0]
    assert "generated_at" not in payload

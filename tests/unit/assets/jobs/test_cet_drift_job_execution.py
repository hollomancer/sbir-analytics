"""Layer-3 execution test for cet_drift_job.

``cet_drift_job`` is defined inline in ``sbir_analytics/definitions.py`` as a
single-asset selection over ``["ml", "validated_cet_drift_detection"]``,
conditional on that asset having been discovered:

    cet_drift_job = define_asset_job(
        name="cet_drift_job",
        selection=AssetSelection.keys(["ml", "validated_cet_drift_detection"]),
        description="Run CET drift detection asset",
    )

Reconstructing that same selection here rather than importing the literal
``cet_drift_job`` object from ``sbir_analytics.definitions`` is deliberate:
importing that module forces ``load_assets_from_modules`` over *every*
discovered asset module (CET/ML/fiscal/NLP included, since
``DAGSTER_LOAD_HEAVY_ASSETS`` is unset by default in the test env), which
would make this "simplest of the three" job's test the slowest one in the
file. ``validated_cet_drift_detection`` itself has no such cost -- it does
its own lazy numpy/pandas imports inside the function body and its module
(``sbir_analytics.assets.cet.validation``) only imports the lightweight
``.utils`` shim at import time -- so importing it directly and wrapping it in
an equivalent job keeps this test both fast and representative of what
``cet_drift_job`` actually runs. If the selection in definitions.py ever
drifts from this, ``tests/unit/assets/test_asset_discovery.py`` and
``tests/unit/test_server_schedule_gating.py`` already assert the job is
discovered/scheduled by name.

The asset itself is hermetic by construction: with no
``data/processed/cet_award_classifications.{parquet,ndjson}`` present, it
writes a `{"ok": True, "reason": "no_input"}` report and succeeds rather than
requiring a trained model or Neo4j, so no dependency mocking is needed here.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from dagster import AssetSelection, Definitions, define_asset_job

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _defs() -> Definitions:
    from sbir_analytics.assets.cet.validation import validated_cet_drift_detection

    job = define_asset_job(
        name="cet_drift_job",
        selection=AssetSelection.keys(["ml", "validated_cet_drift_detection"]),
        description="Run CET drift detection asset",
    )
    return Definitions(assets=[validated_cet_drift_detection], jobs=[job])


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_job_succeeds_with_no_classifications_present(workspace):
    """No award classifications materialized yet: the asset must still run and report."""
    result = _defs().resolve_job_def("cet_drift_job").execute_in_process()

    assert result.success
    output = result.output_for_node("ml__validated_cet_drift_detection")
    assert output["ok"] is True
    assert output["reason"] == "no_input"

    report_path = workspace / "reports/benchmarks/cet_drift_report.json"
    assert report_path.exists()
    assert json.loads(report_path.read_text())["reason"] == "no_input"


def test_job_writes_a_baseline_candidate_on_first_real_input(workspace):
    """With classifications present but no stored baseline, it seeds a baseline candidate."""
    classifications = pd.DataFrame(
        [
            {"award_id": "A-1", "primary_cet": "quantum", "primary_score": 82.0},
            {"award_id": "A-2", "primary_cet": "ai", "primary_score": 45.0},
        ]
    )
    processed_dir = workspace / "data/processed"
    processed_dir.mkdir(parents=True)
    classifications.to_parquet(processed_dir / "cet_award_classifications.parquet", index=False)

    result = _defs().resolve_job_def("cet_drift_job").execute_in_process()

    assert result.success
    baseline_candidate = workspace / "reports/benchmarks/cet_baseline_distributions_current.json"
    assert baseline_candidate.exists()

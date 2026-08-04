import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/audit_sbir_solicitation_source_coverage.py"
SPEC = importlib.util.spec_from_file_location(
    "audit_sbir_solicitation_source_coverage",
    SCRIPT,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

FIXTURE = (
    Path(__file__).parents[2] / "fixtures/extractors/sbir_gov_solicitations/documented_shape.json"
)

pytestmark = pytest.mark.fast


def _complete_sample(size: int) -> list[dict]:
    template = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
    records = []
    for index in range(size):
        record = json.loads(json.dumps(template))
        record["solicitation_number"] = f"TEST-2026-{index:03d}"
        record["solicitation_topics"][0]["topic_number"] = f"TEST-2026-{index:03d}-T01"
        record["solicitation_topics"][0]["subtopics"][0]["subtopic_number"] = (
            f"TEST-2026-{index:03d}-T01-S01"
        )
        records.append(record)
    return records


def test_load_records_accepts_results_wrapper(tmp_path):
    path = tmp_path / "response.json"
    path.write_text(json.dumps({"results": _complete_sample(1)}), encoding="utf-8")

    assert len(MODULE.load_records(path)) == 1


def test_manifest_passes_only_with_complete_unique_minimum_sample(tmp_path):
    records = _complete_sample(50)
    path = tmp_path / "response.json"
    path.write_text(json.dumps(records), encoding="utf-8")

    manifest = MODULE.build_coverage_manifest(
        records,
        input_path=path,
        analysis_date="2026-08-04",
        source_url="https://api.www.sbir.gov/public/api/solicitations?rows=50",
    )

    assert manifest["adapter_decision"] == {
        "adapter": "sbir_gov_solicitations",
        "status": "go",
        "blockers": [],
    }
    assert manifest["input"]["record_count"] == 50
    assert len(manifest["input"]["sha256"]) == 64
    assert manifest["quality"]["solicitation_version_ids_unique"] is True
    assert manifest["quality"]["topic_ids_unique"] is True


def test_documentation_fixture_cannot_pass_live_sample_gate():
    records = MODULE.load_records(FIXTURE)
    manifest = MODULE.build_coverage_manifest(
        records,
        input_path=FIXTURE,
        analysis_date="2026-08-04",
    )

    assert manifest["adapter_decision"]["status"] == "no_go"
    assert "requires at least 50" in manifest["adapter_decision"]["blockers"][0]

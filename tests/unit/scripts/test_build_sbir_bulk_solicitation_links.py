import importlib.util
import hashlib
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_sbir_bulk_solicitation_links.py"
SPEC = importlib.util.spec_from_file_location("build_sbir_bulk_solicitation_links", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

FIXTURE = Path(__file__).parents[2] / "fixtures/extractors/sbir_bulk_awards/linkage_shape.csv"
SCHEMA = Path(__file__).parents[3] / "docs/data/sbir_awards_columns.json"

pytestmark = pytest.mark.fast


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_with_metadata(tmp_path: Path, *, metadata_hash: str | None = None) -> Path:
    source = tmp_path / "award_data.csv"
    shutil.copyfile(FIXTURE, source)
    metadata = {
        "source_url": "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
        "sha256": metadata_hash or _sha256(source),
        "downloaded_at": "2026-08-03T23:21:42+00:00",
        "size": source.stat().st_size,
    }
    source.with_suffix(".meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    return source


def _build(tmp_path: Path, source: Path) -> dict:
    return MODULE.build_bulk_linkage_artifacts(
        source=source,
        expected_schema=SCHEMA,
        links_output=tmp_path / "links.parquet",
        manifest_output=tmp_path / "manifest.json",
        summary_output=tmp_path / "summary.md",
        analysis_date=MODULE.date(2026, 8, 4),
        minimum_rows=1,
    )


def test_builds_exact_links_without_relabeling_award_text(tmp_path):
    source = _source_with_metadata(tmp_path)

    manifest = _build(tmp_path, source)
    links = pd.read_parquet(tmp_path / "links.parquet")

    assert manifest["adapter_decision"]["status"] == "go"
    assert manifest["coverage"]["overall"]["award_rows"] == 4
    assert manifest["coverage"]["overall"]["solicitation_reference_rows"] == 3
    assert manifest["coverage"]["overall"]["exact_solicitation_topic_rows"] == 2
    assert manifest["link_assertions"]["rows"] == 3
    assert links["link_assertion_id"].is_unique
    assert set(links["link_class"]) == {"exact_source_identifier"}
    assert set(links["link_target_grain"]) == {"solicitation", "solicitation_topic"}
    assert "award_title" in links.columns
    assert "award_abstract" in links.columns
    assert "solicitation_title" not in links.columns
    assert "topic_description" not in links.columns


def test_topic_only_award_is_measured_but_not_emitted_as_exact_link(tmp_path):
    source = _source_with_metadata(tmp_path)

    manifest = _build(tmp_path, source)
    links = pd.read_parquet(tmp_path / "links.parquet")

    assert manifest["coverage"]["overall"]["topic_only_rows"] == 1
    assert "NSF-2" not in set(links["source_award_id"])


def test_nsf_recent_and_historical_coverage_remain_separate(tmp_path):
    source = _source_with_metadata(tmp_path)

    manifest = _build(tmp_path, source)

    assert manifest["coverage"]["nsf"]["award_rows"] == 2
    assert manifest["coverage"]["nsf"]["solicitation_reference_rate"] == 0.5
    assert manifest["coverage"]["nsf_award_year_2022_plus"]["award_rows"] == 1
    assert manifest["coverage"]["nsf_award_year_2022_plus"]["solicitation_reference_rate"] == 1.0


def test_exact_duplicate_source_assertion_is_deduplicated_and_reported(tmp_path):
    source = _source_with_metadata(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    pd.concat([frame, frame.iloc[[0]]], ignore_index=True).to_csv(source, index=False)
    metadata_path = source.with_suffix(".meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({"sha256": _sha256(source), "size": source.stat().st_size})
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    manifest = _build(tmp_path, source)

    assert manifest["adapter_decision"]["status"] == "go"
    assert manifest["link_assertions"]["raw_rows_with_solicitation_number"] == 4
    assert manifest["link_assertions"]["rows"] == 3
    assert manifest["link_assertions"]["duplicate_source_assertion_rows"] == 1


def test_metadata_hash_mismatch_fails_closed(tmp_path):
    source = _source_with_metadata(tmp_path, metadata_hash="0" * 64)

    manifest = _build(tmp_path, source)

    assert manifest["adapter_decision"]["status"] == "no_go"
    assert "metadata sidecar" in manifest["adapter_decision"]["blockers"][0]
    assert manifest["link_assertions"]["materialized"] is False
    assert not (tmp_path / "links.parquet").exists()


def test_missing_required_source_column_raises_before_materialization(tmp_path):
    source = _source_with_metadata(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False).drop(
        columns=["Solicitation Number"]
    )
    frame.to_csv(source, index=False)

    with pytest.raises(ValueError, match="Solicitation Number"):
        _build(tmp_path, source)


def test_summary_states_the_award_text_boundary(tmp_path):
    source = _source_with_metadata(tmp_path)

    _build(tmp_path, source)
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert "Award titles and abstracts remain award text" in summary
    assert "not solicitation titles" in summary

"""Tests for the public SBA structural-comparison renderer."""

from __future__ import annotations

import copy
import csv
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.ci import check_study_artifact_roundtrip as roundtrip
from scripts.data import render_sba_structural_comparison as renderer
from sbir_etl.quality.study_manifest import load_study_manifest


ROOT = Path(__file__).resolve().parents[3]
COMPARISON = ROOT / renderer.COMPARISON_REFERENCE
SIDECAR = ROOT / renderer.SIDECAR_REFERENCE
MARKDOWN = ROOT / renderer.MARKDOWN_REFERENCE


def _write_mutated_comparison(destination: Path, mutate: Callable[[dict[str, str]], None]) -> None:
    with COMPARISON.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    assert fieldnames is not None
    mutate(rows[0])
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_committed_public_artifacts_regenerate_byte_for_byte() -> None:
    payload = renderer.build_payload(ROOT)

    assert renderer.serialize_payload(payload) == SIDECAR.read_text(encoding="utf-8")
    assert renderer.render_markdown(payload) == MARKDOWN.read_text(encoding="utf-8")
    assert payload["schema_version"] == 2
    assert payload["content"]["release_status"] == "Validated, not citable"
    assert payload["content"]["comparison"]["aggregate_summary"] == {
        "signed_difference": 333,
        "absolute_difference": 869,
        "positive_difference_cells": 208,
        "negative_difference_cells": 148,
        "zero_vs_zero_cells": 57,
        "nonzero_union_cells": 575,
        "nonzero_union_exact_cells": 219,
    }
    assert payload["content"]["export_row_handling"] == {
        "retained_rows_before_blank_state_exclusion": 20836,
        "blank_state_rows_excluded": 1,
        "counted_rows": 20835,
        "zero_filled_eligible_groups": 60,
        "countable_unit": "one parsed export row",
        "artifact_path": renderer.RUN_DIAGNOSTICS_REFERENCE,
        "artifact_sha256": "bf8c932dd8725f2f3e66309c0318987d4a1eed485e6651d064f2037e9f68dbb8",
    }
    assert payload["content"]["reproduction"] == {
        "setup_command": "make install-core",
        "one_command": "make reproduce-sba-structural",
        "renderer_command": "uv run python scripts/data/render_sba_structural_comparison.py",
    }
    markdown = MARKDOWN.read_text(encoding="utf-8")
    for disclosure in (
        "absolute cell differences sum to 869",
        "208 positive cells against 148 negative cells",
        "57 are zero versus zero",
        "575 cells where either source reports a nonzero count",
        "1 had blank `State` and was excluded",
        "60 eligible jurisdiction/program/phase groups",
        "case and whitespace preserved",
        "study-only code MH",
    ):
        assert disclosure in markdown


def test_registered_pair_rejects_a_manual_markdown_edit(tmp_path: Path) -> None:
    sidecar = tmp_path / "public-result.json"
    markdown = tmp_path / "first-citable-study.md"
    script = tmp_path / "scripts/data/render_sba_structural_comparison.py"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    script.parent.mkdir(parents=True)
    sidecar.write_bytes(SIDECAR.read_bytes())
    markdown.write_text(MARKDOWN.read_text(encoding="utf-8") + "Manual edit.\n", encoding="utf-8")
    script.write_bytes((ROOT / "scripts/data/render_sba_structural_comparison.py").read_bytes())
    pair = roundtrip.RoundTripPair(
        markdown=markdown.relative_to(tmp_path).as_posix(),
        sidecar=sidecar.relative_to(tmp_path).as_posix(),
        renderer=script.relative_to(tmp_path).as_posix() + ":render_markdown",
    )

    violations = roundtrip.validate_pair(pair, root=tmp_path)

    assert len(violations) == 1
    assert "does not reproduce" in violations[0].message


def test_render_rejects_a_manual_sidecar_edit() -> None:
    payload = json.loads(SIDECAR.read_text(encoding="utf-8"))
    payload["content"]["comparison"]["cells"][0]["published_count"] += 1

    with pytest.raises(renderer.PublicResultError, match="content hash differs"):
        renderer.render_markdown(payload)


def test_comparison_reader_rejects_changed_arithmetic(tmp_path: Path) -> None:
    comparison = tmp_path / "changed-arithmetic.csv"

    def mutate(row: dict[str, str]) -> None:
        row["signed_difference"] = "1"
        row["absolute_difference"] = "1"
        row["comparison_status"] = "unresolved"

    _write_mutated_comparison(comparison, mutate)

    with pytest.raises(renderer.PublicResultError, match="incorrect signed arithmetic"):
        renderer.load_comparison_cells(comparison)


def test_payload_rejects_a_coherent_changed_count_by_frozen_hash(tmp_path: Path) -> None:
    comparison = tmp_path / "changed-count.csv"

    def mutate(row: dict[str, str]) -> None:
        row["published_count"] = "4"
        row["recomputed_count"] = "4"

    _write_mutated_comparison(comparison, mutate)

    with pytest.raises(renderer.PublicResultError, match="count comparison hash differs"):
        renderer.build_payload(ROOT, comparison_path=comparison)


def test_render_rejects_internally_drifted_summary_even_when_rehashed() -> None:
    payload = copy.deepcopy(renderer.build_payload(ROOT))
    payload["content"]["comparison"]["yearly_summaries"][0]["published_total"] += 1
    payload["content_sha256"] = renderer._canonical_sha256(payload["content"])

    with pytest.raises(renderer.PublicResultError, match="yearly summaries do not match"):
        renderer.render_markdown(payload)


def test_render_rejects_drifted_aggregate_even_when_rehashed() -> None:
    payload = copy.deepcopy(renderer.build_payload(ROOT))
    payload["content"]["comparison"]["aggregate_summary"]["absolute_difference"] = 333
    payload["content_sha256"] = renderer._canonical_sha256(payload["content"])

    with pytest.raises(renderer.PublicResultError, match="aggregate summary does not match"):
        renderer.render_markdown(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("blank_state_rows_excluded", 40), ("zero_filled_eligible_groups", 59)],
)
def test_render_rejects_drifted_export_diagnostics_even_when_rehashed(
    field: str, value: int
) -> None:
    payload = copy.deepcopy(renderer.build_payload(ROOT))
    payload["content"]["export_row_handling"][field] = value
    payload["content_sha256"] = renderer._canonical_sha256(payload["content"])

    with pytest.raises(renderer.PublicResultError, match="diagnostics differ from the frozen run"):
        renderer.render_markdown(payload)


def test_summary_claim_cannot_revert_to_signed_only_framing() -> None:
    manifest = load_study_manifest(ROOT / renderer.STUDY_MANIFEST_REFERENCE)
    signed_only = manifest.model_copy(
        update={
            "permitted_claims": [
                manifest.permitted_claims[0],
                (
                    "The comparison contains 632 count cells: 276 are exact and 356 are "
                    "unresolved. Across the same cells, recomputed minus published counts "
                    "sum to +333. This total is not an omitted-award estimate, a "
                    "source-correctness verdict, or a causal explanation."
                ),
            ]
        }
    )

    with pytest.raises(renderer.PublicResultError, match="summary claim is missing"):
        renderer._summary_claim(signed_only)


def test_registry_names_the_public_result_pair() -> None:
    matching = [
        pair
        for pair in roundtrip.REGISTERED_PAIRS
        if pair.renderer_path == "scripts/data/render_sba_structural_comparison.py"
    ]

    assert matching == [
        roundtrip.RoundTripPair(
            markdown=renderer.MARKDOWN_REFERENCE,
            sidecar=renderer.SIDECAR_REFERENCE,
            renderer="scripts/data/render_sba_structural_comparison.py:render_markdown",
        )
    ]

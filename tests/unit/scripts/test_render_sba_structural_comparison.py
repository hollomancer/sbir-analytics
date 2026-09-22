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
    assert payload["content"]["release_status"] == "Validated, not citable"


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

#!/usr/bin/env python3
"""Build the frozen SBA annual-report structural-comparison sidecar.

Epistemic tier: evidence. The command reads only paths and identities that the
study and source manifests declare. It does not select sources or tolerances.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from sbir_analytics.assets.sba_annual_report_structural_comparison.producer import (
    ANNUAL_REPORT_SOURCE_IDS,
    AWARD_EXPORT_SOURCE_ID,
    CAPTURED_TABLE_SOURCE_IDS,
    REPORT_TABLES,
    AnnualReportSource,
    CapturedTableSource,
    PinnedFile,
    ProductionInputs,
    produce_count_sidecar,
)
from sbir_etl.quality.study_manifest import StudyManifest, load_study_manifest


EPISTEMIC_TIER = "evidence"
STUDY_DIRECTORY = Path("studies/sba-annual-report-structural-comparison")
SOURCE_MANIFEST = STUDY_DIRECTORY / "source-manifest.json"
STUDY_MANIFEST = STUDY_DIRECTORY / "study.yaml"
VALIDATION_DESIGN = STUDY_DIRECTORY / "validation-design-v1.md"
VALIDATION_POPULATION = STUDY_DIRECTORY / "validation-population-v1.csv"
PRODUCER = Path(
    "packages/sbir-analytics/sbir_analytics/assets/"
    "sba_annual_report_structural_comparison/producer.py"
)


class ReproductionError(ValueError):
    """Raised when the checked-in reproduction contract is incomplete."""


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReproductionError(f"cannot read JSON manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReproductionError(f"JSON manifest must contain an object: {path}")
    return value


def _index(records: object, *, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list):
        raise ReproductionError(f"{label} must be an array")
    indexed: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            raise ReproductionError(f"{label} entries must be objects")
        source_id = raw.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ReproductionError(f"{label} entries require source_id")
        if source_id in indexed:
            raise ReproductionError(f"{label} repeats source_id {source_id!r}")
        indexed[source_id] = raw
    return indexed


def _frozen_sha256(manifest: StudyManifest, reference: str) -> str:
    frozen = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}
    try:
        return frozen[reference]
    except KeyError as exc:
        raise ReproductionError(f"study manifest does not freeze {reference}") from exc


def _repository_pin(root: Path, manifest: StudyManifest, reference: str) -> PinnedFile:
    path = root / reference
    if not path.is_file():
        raise ReproductionError(f"required repository file is missing: {path}")
    return PinnedFile(
        reference=reference,
        path=path,
        sha256=_frozen_sha256(manifest, reference),
        size_bytes=path.stat().st_size,
    )


def _source_pin(source_root: Path, record: Mapping[str, Any]) -> PinnedFile:
    reference = record.get("local_path")
    if not isinstance(reference, str) or not reference:
        raise ReproductionError("source record requires local_path")
    sha256 = record.get("sha256")
    size_bytes = record.get("size_bytes")
    if not isinstance(sha256, str) or type(size_bytes) is not int:
        raise ReproductionError(f"source record has invalid identity: {reference}")
    return PinnedFile(
        reference=reference,
        path=source_root / reference,
        sha256=sha256,
        size_bytes=size_bytes,
    )


def _pdf_page_count(path: Path) -> int:
    return len(PdfReader(path).pages)


def build_production_inputs(repository_root: Path, source_root: Path) -> ProductionInputs:
    """Construct production inputs from the two checked-in manifests."""

    study_manifest_path = repository_root / STUDY_MANIFEST
    study_manifest = load_study_manifest(study_manifest_path)
    source_manifest_path = repository_root / SOURCE_MANIFEST
    source_manifest = _load_json(source_manifest_path)
    sources = _index(source_manifest.get("sources"), label="source manifest sources")
    captured = _index(
        source_manifest.get("captured_tables"),
        label="source manifest captured_tables",
    )

    export_record = sources[AWARD_EXPORT_SOURCE_ID]
    metadata_reference = export_record.get("metadata_path")
    if not isinstance(metadata_reference, str) or not metadata_reference:
        raise ReproductionError("award-export source requires metadata_path")

    annual_reports = tuple(
        AnnualReportSource(
            report_year=year,
            table_number=REPORT_TABLES[year],
            file=_source_pin(source_root, sources[source_id]),
        )
        for year, source_id in ANNUAL_REPORT_SOURCE_IDS.items()
    )
    captured_tables = tuple(
        CapturedTableSource(
            report_year=year,
            table_number=REPORT_TABLES[year],
            file=_repository_pin(
                repository_root,
                study_manifest,
                str(captured[source_id]["path"]),
            ),
            row_count=int(captured[source_id]["row_count"]),
        )
        for year, source_id in CAPTURED_TABLE_SOURCE_IDS.items()
    )
    return ProductionInputs(
        source_manifest=_repository_pin(
            repository_root,
            study_manifest,
            SOURCE_MANIFEST.as_posix(),
        ),
        award_export=_source_pin(source_root, export_record),
        award_export_metadata=_repository_pin(
            repository_root,
            study_manifest,
            metadata_reference,
        ),
        annual_reports=annual_reports,
        captured_tables=captured_tables,
        validation_design=_repository_pin(
            repository_root,
            study_manifest,
            VALIDATION_DESIGN.as_posix(),
        ),
        validation_population=_repository_pin(
            repository_root,
            study_manifest,
            VALIDATION_POPULATION.as_posix(),
        ),
        implementation=_repository_pin(
            repository_root,
            study_manifest,
            PRODUCER.as_posix(),
        ),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Root containing the manifest-declared downloaded source paths.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Verify every frozen input and write the deterministic count sidecar."""

    args = _parse_args()
    repository_root = args.repository_root.resolve()
    source_root = (args.source_root or repository_root).resolve()
    inputs = build_production_inputs(repository_root, source_root)
    product = produce_count_sidecar(
        inputs,
        args.output,
        pdf_page_counter=_pdf_page_count,
    )
    print(
        f"Wrote {len(product.frame)} frozen count cells to {args.output}. "
        f"Dropped {product.dropped_blank_state_rows} retained rows with blank State."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

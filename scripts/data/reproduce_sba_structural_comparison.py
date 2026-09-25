#!/usr/bin/env python3
"""Reproduce and verify the public SBA structural-comparison packet.

Epistemic tier: evidence. This command acquires only manifest-declared source
bytes. It verifies the released count sidecar and any recorded confirmatory
submission without changing committed artifacts.
"""

from __future__ import annotations

import argparse
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from sbir_analytics.assets.sba_annual_report_structural_comparison.producer import (
    EXPECTED_CELL_COUNT,
    EXPECTED_VALIDATION_VALUE_COUNT,
    produce_count_sidecar,
    verify_validation_values,
)
from sbir_etl.quality.study_manifest import load_study_manifest
from sbir_etl.utils.data.file_io import file_sha256
from scripts.data.acquire_sba_structural_sources import acquire_sources
from scripts.data.render_sba_structural_comparison import (
    MARKDOWN_REFERENCE,
    SIDECAR_REFERENCE,
    build_payload,
    render_markdown,
    serialize_payload,
)
from scripts.data.run_sba_structural_comparison import (
    SOURCE_MANIFEST,
    STUDY_MANIFEST,
    build_production_inputs,
)


EPISTEMIC_TIER = "evidence"
COMMITTED_COMPARISON = Path(
    "studies/sba-annual-report-structural-comparison/results/count-comparison.csv"
)
CONFIRMATORY_VALUES = Path(
    "studies/sba-annual-report-structural-comparison/validation/confirmatory/validation-values.csv"
)
CONFIRMATORY_DIRECTORY = CONFIRMATORY_VALUES.parent
CONFIRMATORY_SEAL = CONFIRMATORY_DIRECTORY / "sealed-components.sha256"
_SEALED_ARCHIVE_RENAMES = {"extract_validation.py": "extract_validation.py.txt"}
_SHA256_LINE = re.compile(r"(?P<sha256>[0-9a-f]{64})  (?P<path>[^\r\n]+)")


class ReproductionFailure(RuntimeError):
    """Raised when a released artifact cannot be reproduced exactly."""


@dataclass(frozen=True)
class ReproductionRecord:
    """The verified public quantities from one reproduction."""

    comparison_cells: int
    comparison_sha256: str
    validation_values: int | None
    validation_sha256: str | None
    sealed_components: int | None
    public_sidecar_sha256: str
    public_markdown_sha256: str


def _pdf_page_count(path: Path) -> int:
    return len(PdfReader(path).pages)


def _frozen_sha256(manifest_path: Path, reference: str) -> str:
    manifest = load_study_manifest(manifest_path)
    frozen = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}
    try:
        return frozen[reference]
    except KeyError as exc:
        raise ReproductionFailure(f"study manifest does not freeze {reference}") from exc


def verify_confirmatory_seal(repository_root: Path, manifest_path: Path) -> int:
    """Verify the sealed submission, including its archived extractor rename."""

    seal = repository_root / CONFIRMATORY_SEAL
    if not seal.is_file():
        raise ReproductionFailure(f"confirmatory component seal is missing: {seal}")
    if file_sha256(seal) != _frozen_sha256(manifest_path, CONFIRMATORY_SEAL.as_posix()):
        raise ReproductionFailure("confirmatory component seal does not match its frozen digest")

    confirmatory_root = (repository_root / CONFIRMATORY_DIRECTORY).resolve()
    seen: set[str] = set()
    count = 0
    for line_number, line in enumerate(seal.read_text(encoding="utf-8").splitlines(), start=1):
        match = _SHA256_LINE.fullmatch(line)
        if match is None:
            raise ReproductionFailure(
                f"confirmatory component seal line {line_number} is malformed"
            )
        sealed_path = match.group("path")
        if sealed_path in seen:
            raise ReproductionFailure(f"confirmatory component seal repeats path: {sealed_path}")
        seen.add(sealed_path)
        archived_path = _SEALED_ARCHIVE_RENAMES.get(sealed_path, sealed_path)
        candidate = (confirmatory_root / archived_path).resolve()
        if not candidate.is_relative_to(confirmatory_root):
            raise ReproductionFailure(
                f"confirmatory component seal path escapes its directory: {sealed_path}"
            )
        if not candidate.is_file():
            raise ReproductionFailure(f"sealed confirmatory component is missing: {sealed_path}")
        if file_sha256(candidate) != match.group("sha256"):
            raise ReproductionFailure(f"sealed confirmatory component hash differs: {sealed_path}")
        count += 1
    if count == 0:
        raise ReproductionFailure("confirmatory component seal is empty")
    return count


def reproduce(
    repository_root: Path,
    source_root: Path,
    *,
    acquire: bool,
) -> ReproductionRecord:
    """Acquire sources when requested and verify every released count value."""

    repository_root = repository_root.resolve()
    source_root = source_root.resolve()
    source_manifest = repository_root / SOURCE_MANIFEST
    study_manifest_path = repository_root / STUDY_MANIFEST
    if acquire:
        acquire_sources(source_manifest, source_root)

    inputs = build_production_inputs(repository_root, source_root)
    committed_comparison = repository_root / COMMITTED_COMPARISON
    if not committed_comparison.is_file():
        raise ReproductionFailure(f"released count sidecar is missing: {committed_comparison}")

    with tempfile.TemporaryDirectory(prefix="sba-structural-reproduction-") as temporary:
        generated = Path(temporary) / "count-comparison.csv"
        product = produce_count_sidecar(
            inputs,
            generated,
            pdf_page_counter=_pdf_page_count,
        )
        if generated.read_bytes() != committed_comparison.read_bytes():
            raise ReproductionFailure(
                "generated count sidecar is not byte-identical to the released artifact"
            )

    if len(product.frame) != EXPECTED_CELL_COUNT:
        raise ReproductionFailure(
            f"generated {len(product.frame)} cells; expected {EXPECTED_CELL_COUNT}"
        )
    comparison_reference = COMMITTED_COMPARISON.as_posix()
    comparison_sha256 = file_sha256(committed_comparison)
    if comparison_sha256 != _frozen_sha256(study_manifest_path, comparison_reference):
        raise ReproductionFailure("released count sidecar does not match its frozen digest")

    manifest = load_study_manifest(study_manifest_path)
    validation_count: int | None = None
    validation_sha256: str | None = None
    sealed_components: int | None = None
    if manifest.validation_result is not None:
        sealed_components = verify_confirmatory_seal(repository_root, study_manifest_path)
        validation_path = repository_root / CONFIRMATORY_VALUES
        if not validation_path.is_file():
            raise ReproductionFailure(
                f"confirmatory validation submission is missing: {validation_path}"
            )
        validation_sha256 = file_sha256(validation_path)
        if validation_sha256 != _frozen_sha256(
            study_manifest_path,
            CONFIRMATORY_VALUES.as_posix(),
        ):
            raise ReproductionFailure(
                "confirmatory validation submission does not match its frozen digest"
            )
        validation_count = verify_validation_values(validation_path, product.frame)
        result = manifest.validation_result
        if (
            validation_count != EXPECTED_VALIDATION_VALUE_COUNT
            or result.numerator != validation_count
            or result.denominator != EXPECTED_VALIDATION_VALUE_COUNT
            or not result.confirmatory
            or not result.threshold_met
        ):
            raise ReproductionFailure(
                "study validation result does not match the reconciled confirmatory submission"
            )

    public_sidecar = repository_root / SIDECAR_REFERENCE
    public_markdown = repository_root / MARKDOWN_REFERENCE
    for label, path in (
        ("public result sidecar", public_sidecar),
        ("public result Markdown", public_markdown),
    ):
        if not path.is_file():
            raise ReproductionFailure(f"{label} is missing: {path}")
    payload = build_payload(repository_root)
    if serialize_payload(payload).encode("utf-8") != public_sidecar.read_bytes():
        raise ReproductionFailure("public result sidecar does not reproduce byte-for-byte")
    if render_markdown(payload).encode("utf-8") != public_markdown.read_bytes():
        raise ReproductionFailure("public result Markdown does not reproduce byte-for-byte")
    public_sidecar_sha256 = file_sha256(public_sidecar)
    public_markdown_sha256 = file_sha256(public_markdown)
    if public_sidecar_sha256 != _frozen_sha256(study_manifest_path, SIDECAR_REFERENCE):
        raise ReproductionFailure("public result sidecar does not match its frozen digest")
    if public_markdown_sha256 != _frozen_sha256(study_manifest_path, MARKDOWN_REFERENCE):
        raise ReproductionFailure("public result Markdown does not match its frozen digest")

    return ReproductionRecord(
        comparison_cells=len(product.frame),
        comparison_sha256=comparison_sha256,
        validation_values=validation_count,
        validation_sha256=validation_sha256,
        sealed_components=sealed_components,
        public_sidecar_sha256=public_sidecar_sha256,
        public_markdown_sha256=public_markdown_sha256,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument(
        "--skip-acquire",
        action="store_true",
        help="Use an already acquired source root. Every source is still verified.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the public exact-byte reproduction command."""

    args = _parse_args()
    repository_root = args.repository_root.resolve()
    source_root = (args.source_root or repository_root).resolve()
    result = reproduce(
        repository_root,
        source_root,
        acquire=not args.skip_acquire,
    )
    message = f"Verified {result.comparison_cells} comparison cells ({result.comparison_sha256})."
    if result.validation_values is None:
        message += " No confirmatory validation result is recorded; the study is non-citable."
    else:
        message += (
            f" Verified {result.validation_values} confirmatory values "
            f"({result.validation_sha256}) and {result.sealed_components} sealed components."
        )
    message += (
        f" Verified public sidecar ({result.public_sidecar_sha256}) and Markdown "
        f"({result.public_markdown_sha256})."
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

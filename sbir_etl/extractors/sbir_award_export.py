"""Lossless reader for the SBIR.gov public award export.

Epistemic tier: pipelines. The reader returns one ``EXPORT_ROW_V1`` record per
physical CSV data record without normalization, deduplication, or award-ID
construction.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from sbir_etl.models.award_export import AwardExportSourceMetadata
from sbir_etl.utils.data.file_io import file_sha256


EPISTEMIC_TIER = "pipelines"

SBIR_GOV_SOURCE_COLUMNS: tuple[str, ...] = (
    "Company",
    "Award Title",
    "Agency",
    "Branch",
    "Phase",
    "Program",
    "Agency Tracking Number",
    "Contract",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Number",
    "Solicitation Year",
    "Solicitation Close Date",
    "Proposal Receipt Date",
    "Date of Notification",
    "Topic Code",
    "Award Year",
    "Award Amount",
    "UEI",
    "Duns",
    "HUBZone Owned",
    "Socially and Economically Disadvantaged",
    "Woman Owned",
    "Number Employees",
    "Company Website",
    "Address1",
    "Address2",
    "City",
    "State",
    "Zip",
    "Abstract",
    "Contact Name",
    "Contact Title",
    "Contact Phone",
    "Contact Email",
    "PI Name",
    "PI Title",
    "PI Phone",
    "PI Email",
    "RI Name",
    "RI POC Name",
    "RI POC Phone",
)


class SbirGovSourceError(ValueError):
    """Raised when an SBIR.gov source row violates the exact export contract."""


@dataclass(frozen=True)
class VerifiedAwardExport:
    """One verified source frame and the metadata that pinned it."""

    frame: pd.DataFrame
    metadata: AwardExportSourceMetadata
    source_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class AwardExportInspection:
    """Mechanical shape facts observed while streaming an exact export."""

    row_count: int
    column_count: int
    ordered_schema_sha256: str


def ordered_columns_sha256(columns: tuple[str, ...] | list[str]) -> str:
    """Return the deterministic fingerprint of an ordered column sequence."""

    payload = json.dumps(list(columns), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iter_sbir_gov_rows(path: Path) -> Iterator[list[str]]:
    """Yield exact source rows after validating the ordered CSV contract."""

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SbirGovSourceError("SBIR.gov CSV is empty") from exc
        if tuple(header) != SBIR_GOV_SOURCE_COLUMNS:
            raise SbirGovSourceError(
                "SBIR.gov CSV header does not match the required ordered 42-column schema"
            )
        for record_number, row in enumerate(reader, start=2):
            if len(row) != len(SBIR_GOV_SOURCE_COLUMNS):
                raise SbirGovSourceError(
                    f"SBIR.gov CSV record {record_number} has {len(row)} fields; "
                    f"expected {len(SBIR_GOV_SOURCE_COLUMNS)}"
                )
            yield row


def inspect_sbir_gov_csv(path: Path) -> AwardExportInspection:
    """Validate an export by streaming it without retaining source rows."""

    row_count = sum(1 for _ in iter_sbir_gov_rows(path))
    return AwardExportInspection(
        row_count=row_count,
        column_count=len(SBIR_GOV_SOURCE_COLUMNS),
        ordered_schema_sha256=ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
    )


def read_sbir_gov_csv(path: Path) -> pd.DataFrame:
    """Read the exact 42-field SBIR.gov CSV as strings in declared order."""

    rows = list(iter_sbir_gov_rows(path))
    return pd.DataFrame(rows, columns=SBIR_GOV_SOURCE_COLUMNS, dtype="object")


def read_award_export_metadata(path: Path) -> AwardExportSourceMetadata:
    """Load one source sidecar and reject incomplete or invalid metadata."""

    if not path.is_file():
        raise SbirGovSourceError(f"SBIR.gov source metadata is missing: {path}")
    try:
        return AwardExportSourceMetadata.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, PydanticValidationError, ValueError) as exc:
        raise SbirGovSourceError(f"SBIR.gov source metadata is invalid: {path}: {exc}") from exc


def load_verified_award_export(
    source_path: Path,
    metadata_path: Path,
) -> VerifiedAwardExport:
    """Verify the pinned source sidecar before returning exact export rows."""

    source_path = Path(source_path)
    metadata_path = Path(metadata_path)
    if not source_path.is_file():
        raise SbirGovSourceError(f"SBIR.gov award export is missing: {source_path}")
    metadata = read_award_export_metadata(metadata_path)

    observed_bytes = source_path.stat().st_size
    if observed_bytes != metadata.size_bytes:
        raise SbirGovSourceError(
            "SBIR.gov award export byte count does not match the pinned sidecar: "
            f"expected {metadata.size_bytes}, observed {observed_bytes}"
        )
    observed_sha256 = file_sha256(source_path)
    if observed_sha256 != metadata.sha256:
        raise SbirGovSourceError(
            "SBIR.gov award export SHA-256 does not match the pinned sidecar: "
            f"expected {metadata.sha256}, observed {observed_sha256}"
        )

    expected_schema_sha256 = ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS)
    if metadata.column_count != len(SBIR_GOV_SOURCE_COLUMNS):
        raise SbirGovSourceError(
            "SBIR.gov sidecar column count does not match the canonical schema: "
            f"expected {len(SBIR_GOV_SOURCE_COLUMNS)}, observed {metadata.column_count}"
        )
    if metadata.ordered_schema_sha256 != expected_schema_sha256:
        raise SbirGovSourceError(
            "SBIR.gov sidecar schema fingerprint does not match the canonical schema: "
            f"expected {expected_schema_sha256}, observed {metadata.ordered_schema_sha256}"
        )

    frame = read_sbir_gov_csv(source_path)
    if len(frame) != metadata.row_count:
        raise SbirGovSourceError(
            "SBIR.gov award export row count does not match the pinned sidecar: "
            f"expected {metadata.row_count}, observed {len(frame)}"
        )
    return VerifiedAwardExport(
        frame=frame,
        metadata=metadata,
        source_path=source_path,
        metadata_path=metadata_path,
    )


__all__ = [
    "AwardExportInspection",
    "EPISTEMIC_TIER",
    "SBIR_GOV_SOURCE_COLUMNS",
    "SbirGovSourceError",
    "VerifiedAwardExport",
    "inspect_sbir_gov_csv",
    "iter_sbir_gov_rows",
    "load_verified_award_export",
    "ordered_columns_sha256",
    "read_award_export_metadata",
    "read_sbir_gov_csv",
]

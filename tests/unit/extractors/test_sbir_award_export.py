import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sbir_etl.extractors.sbir_award_export import (
    SBIR_GOV_SOURCE_COLUMNS,
    SbirGovSourceError,
    inspect_sbir_gov_csv,
    load_verified_award_export,
    ordered_columns_sha256,
    read_sbir_gov_csv,
)
from sbir_etl.models.award_export import AwardExportSourceMetadata
from sbir_etl.utils.data.file_io import file_sha256


pytestmark = pytest.mark.fast


def _write_rows(
    path: Path, rows: list[list[str]], *, columns: tuple[str, ...] | None = None
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns or SBIR_GOV_SOURCE_COLUMNS)
        writer.writerows(rows)


def _row(**overrides: str) -> list[str]:
    values = dict.fromkeys(SBIR_GOV_SOURCE_COLUMNS, "")
    values.update(overrides)
    return [values[column] for column in SBIR_GOV_SOURCE_COLUMNS]


def test_exact_reader_preserves_values_newlines_empty_strings_duplicates_and_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "award_data.csv"
    first = _row(
        Company="  Example Corp  ",
        **{"Agency Tracking Number": "000123", "Abstract": "first line\nsecond line"},
    )
    second = first.copy()
    third = _row(Company="Later Corp", **{"Agency Tracking Number": "TRACK-2"})
    _write_rows(path, [first, second, third])

    frame = read_sbir_gov_csv(path)

    assert len(SBIR_GOV_SOURCE_COLUMNS) == 42
    assert tuple(frame.columns) == SBIR_GOV_SOURCE_COLUMNS
    assert frame.values.tolist() == [first, second, third]
    assert frame.loc[0, "Company"] == "  Example Corp  "
    assert frame.loc[0, "Abstract"] == "first line\nsecond line"
    assert frame.loc[0, "Award Year"] == ""
    assert frame.loc[1].tolist() == frame.loc[0].tolist()

    inspection = inspect_sbir_gov_csv(path)
    assert inspection.row_count == 3
    assert inspection.column_count == 42
    assert inspection.ordered_schema_sha256 == ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS)


def test_exact_reader_rejects_header_reordering(tmp_path: Path) -> None:
    path = tmp_path / "award_data.csv"
    reordered = list(SBIR_GOV_SOURCE_COLUMNS)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    _write_rows(path, [_row()], columns=tuple(reordered))

    with pytest.raises(SbirGovSourceError, match="ordered 42-column schema"):
        read_sbir_gov_csv(path)


def test_exact_reader_reports_logical_csv_record_for_wrong_field_count(tmp_path: Path) -> None:
    path = tmp_path / "award_data.csv"
    _write_rows(path, [_row()[:-1]])

    with pytest.raises(SbirGovSourceError, match=r"record 2 has 41 fields; expected 42"):
        read_sbir_gov_csv(path)


def test_phase_ii_module_reexports_the_shared_schema_and_parser() -> None:
    from sbir_analytics.assets.phase_transition import sbir_gov_source

    assert sbir_gov_source.SBIR_GOV_SOURCE_COLUMNS is SBIR_GOV_SOURCE_COLUMNS
    assert sbir_gov_source.SbirGovSourceError is SbirGovSourceError
    assert sbir_gov_source.read_sbir_gov_csv is read_sbir_gov_csv


def _write_metadata(path: Path, source: Path, *, row_count: int = 1, **overrides: object) -> None:
    values: dict[str, object] = {
        "source_url": "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
        "retrieved_at": datetime(2026, 9, 17, 1, 32, tzinfo=UTC),
        "upstream_date_unknown_reason": "Upstream date was not returned by the test fixture.",
        "sha256": file_sha256(source),
        "size_bytes": source.stat().st_size,
        "row_count": row_count,
        "column_count": len(SBIR_GOV_SOURCE_COLUMNS),
        "ordered_schema_sha256": ordered_columns_sha256(SBIR_GOV_SOURCE_COLUMNS),
        "retrieval_tool": "pytest",
        "retrieval_tool_version": pytest.__version__,
        "operator_identity": "automation:test",
        "access_license_note": "Synthetic test fixture.",
    }
    values.update(overrides)
    metadata = AwardExportSourceMetadata.model_validate(values)
    path.write_text(metadata.to_json(), encoding="utf-8")


def test_verified_loader_accepts_exact_source_and_complete_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    row = _row(Company="Verified Corp")
    _write_rows(source, [row])
    _write_metadata(sidecar, source)

    verified = load_verified_award_export(source, sidecar)

    assert verified.frame.values.tolist() == [row]
    assert verified.metadata.row_count == 1
    assert verified.source_path == source


@pytest.mark.parametrize("missing", ["source", "sidecar"])
def test_verified_loader_rejects_missing_inputs(tmp_path: Path, missing: str) -> None:
    source = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    _write_rows(source, [_row()])
    _write_metadata(sidecar, source)
    (source if missing == "source" else sidecar).unlink()

    with pytest.raises(SbirGovSourceError, match="missing"):
        load_verified_award_export(source, sidecar)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sha256", "0" * 64, "SHA-256"),
        ("size_bytes", 1, "byte count"),
        ("row_count", 2, "row count"),
        ("column_count", 41, "column count"),
        ("ordered_schema_sha256", "0" * 64, "schema fingerprint"),
    ],
)
def test_verified_loader_rejects_tampered_sidecar(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    source = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    _write_rows(source, [_row()])
    _write_metadata(sidecar, source, **{field: value})

    with pytest.raises(SbirGovSourceError, match=message):
        load_verified_award_export(source, sidecar)


def test_verified_loader_rejects_source_byte_tamper(tmp_path: Path) -> None:
    source = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    _write_rows(source, [_row()])
    _write_metadata(sidecar, source)
    source.write_bytes(source.read_bytes() + b"\n")

    with pytest.raises(SbirGovSourceError, match="byte count"):
        load_verified_award_export(source, sidecar)


def test_verified_loader_rejects_incomplete_metadata(tmp_path: Path) -> None:
    source = tmp_path / "award_data.csv"
    sidecar = tmp_path / "award_data.meta.json"
    _write_rows(source, [_row()])
    sidecar.write_text(json.dumps({"sha256": file_sha256(source)}), encoding="utf-8")

    with pytest.raises(SbirGovSourceError, match="metadata is invalid"):
        load_verified_award_export(source, sidecar)

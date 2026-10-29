import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sbir_etl.extractors.sbir_award_export import (
    DIRECT_TO_PHASE_II_LABELS,
    SBIR_GOV_SOURCE_COLUMNS,
    SBIR_PHASE_VOCABULARY,
    SbirGovSourceError,
    inspect_sbir_gov_csv,
    load_verified_award_export,
    normalize_sbir_phase,
    ordered_columns_sha256,
    read_sbir_gov_csv,
    sbir_phase_for_counting,
    unknown_sbir_phase_values,
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


DIRECT_TO_PHASE_II_EN_DASH = "Phase II \u2013 Direct to Phase II"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Phase I", "I"),
        ("  phase ii ", "II"),
        ("PHASE III", "III"),
        ("II", "II"),
        (None, None),
        ("", None),
        ("<NA>", None),
        (float("nan"), None),
        # Adversarial: a looser rule would map each of these to a base phase.
        (DIRECT_TO_PHASE_II_EN_DASH, None),
        ("Phase II - Direct to Phase II", None),
        ("Phase II Sequential", None),
        ("Phase IIB", None),
        ("Phase I/II", None),
        ("Phase 2", None),
        ("Phase IV", None),
        ("Phase", None),
    ],
)
def test_normalize_sbir_phase_accepts_exact_labels_only(
    value: object, expected: str | None
) -> None:
    assert normalize_sbir_phase(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Phase I", "I"),
        ("Phase II", "II"),
        ("PHASE III", "III"),
        ("II", "II"),
        # Program policy: a direct-to-Phase-II award counts as Phase II.
        (DIRECT_TO_PHASE_II_EN_DASH, "II"),
        ("Phase II - Direct to Phase II", "II"),
        ("  phase ii  \u2013  direct to phase ii ", "II"),
        (None, None),
        ("", None),
        ("<NA>", None),
        (float("nan"), None),
        # Still unclassified: these must not be guessed into a phase.
        ("Phase IIB", None),
        ("Phase I/II", None),
        ("Phase 2", None),
    ],
)
def test_sbir_phase_for_counting_applies_the_program_policy(
    value: object, expected: str | None
) -> None:
    assert sbir_phase_for_counting(value) == expected


def test_counting_and_exact_rules_differ_only_on_direct_to_phase_ii() -> None:
    """Pin the one intentional divergence between the two phase rules."""

    for label in DIRECT_TO_PHASE_II_LABELS:
        assert normalize_sbir_phase(label) is None
        assert sbir_phase_for_counting(label) == "II"
    for label in ("Phase I", "Phase II", "Phase III", "I", "II", "III"):
        assert normalize_sbir_phase(label) == sbir_phase_for_counting(label)
    for label in ("Phase IIB", "Phase I/II", "Phase 2", "Phase IV", "II-B"):
        assert normalize_sbir_phase(label) is None
        assert sbir_phase_for_counting(label) is None


def test_the_live_export_spelling_uses_an_en_dash() -> None:
    """The export emits U+2013; the ASCII hyphen is accepted as a fallback."""

    assert "\u2013" in DIRECT_TO_PHASE_II_EN_DASH
    assert DIRECT_TO_PHASE_II_EN_DASH in DIRECT_TO_PHASE_II_LABELS
    assert "Phase II - Direct to Phase II" in DIRECT_TO_PHASE_II_LABELS
    assert set(DIRECT_TO_PHASE_II_LABELS) <= set(SBIR_PHASE_VOCABULARY)


@pytest.mark.parametrize("label", ["Phase\tII", "Phase\u00a0II", " phase   ii "])
def test_both_phase_rules_fold_whitespace_the_same_way(label: str) -> None:
    assert normalize_sbir_phase(label) == "II"
    assert sbir_phase_for_counting(label) == "II"


def test_every_vocabulary_entry_resolves_to_a_counted_phase() -> None:
    for label, phase in SBIR_PHASE_VOCABULARY.items():
        assert phase in {"I", "II", "III"}
        assert sbir_phase_for_counting(label) == phase


def test_unknown_sbir_phase_values_reports_only_unclassified_labels() -> None:
    observed = [
        "Phase I",
        "Phase II",
        DIRECT_TO_PHASE_II_EN_DASH,
        "",
        None,
        "<NA>",
        "Phase IIB",
        "phase iib",
        "Phase I/II",
    ]

    # Blank and sentinel values are not reported; case/whitespace variants collapse.
    assert unknown_sbir_phase_values(observed) == ["PHASE I/II", "PHASE IIB"]
    assert unknown_sbir_phase_values(["Phase I", "Phase II"]) == []

"""Count-only producer and materialization gate for the SBA comparison.

Epistemic tier: evidence. Callers supply every path and frozen digest. This
module does not discover inputs, select tolerances, run validation, or publish.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.identity.geography import (
    SBA_ANNUAL_REPORT_JURISDICTIONS_V1,
    USJurisdictionProfile,
    normalize_us_jurisdiction,
)
from sbir_etl.extractors.sbir_award_export import (
    SBIR_GOV_SOURCE_COLUMNS,
    load_verified_award_export,
    ordered_columns_sha256,
)
from sbir_etl.models.award_export import AwardGrain, FiscalYearBasis
from sbir_etl.quality.study_manifest import (
    EvidenceStatus,
    StudyManifest,
    ThresholdBasis,
    load_study_manifest,
)
from sbir_etl.utils.data.file_io import file_sha256


EPISTEMIC_TIER = "evidence"
STUDY_ID = "sba-annual-report-structural-comparison"
REPORT_TABLES = {2020: "Table 18", 2021: "Table 18", 2022: "Table 20"}
TABLE_NUMBERS = {2020: 18, 2021: 18, 2022: 20}
PROGRAMS = ("SBIR", "STTR")
PHASES = ("Phase I", "Phase II")
EXPECTED_CELL_COUNT = 632
EXPECTED_VALIDATION_VALUE_COUNT = EXPECTED_CELL_COUNT * 2
EXACT_INTERVAL_METHOD = "exact complete-population point interval; no sampling"
HEADER_FINGERPRINT_PROCEDURE = (
    "SHA-256 of compact UTF-8 JSON for the ordered string array, with "
    "ensure_ascii=false and separators comma/colon"
)
AWARD_EXPORT_SOURCE_ID = "sbir-gov-award-export-2026-09-17"
ANNUAL_REPORT_SOURCE_IDS = {
    2020: "sba-annual-report-fy2020",
    2021: "sba-annual-report-fy2021",
    2022: "sba-annual-report-fy2022",
}
CAPTURED_TABLE_SOURCE_IDS = {
    2020: "fy2020-table-18-capture",
    2021: "fy2021-table-18-capture",
    2022: "fy2022-table-20-capture",
}

POPULATION_COLUMNS = (
    "unit_id",
    "target",
    "report_year",
    "jurisdiction",
    "program",
    "phase",
)
KEY_COLUMNS = ("report_year", "jurisdiction", "program", "phase")
COUNT_SIDECAR_COLUMNS = (
    "report_year",
    "table_number",
    "jurisdiction",
    "program",
    "phase",
    "published_count",
    "recomputed_count",
    "signed_difference",
    "absolute_difference",
    "comparison_status",
)
VALIDATION_VALUE_COLUMNS = (
    "unit_id",
    "target",
    "report_year",
    "table_number",
    "jurisdiction",
    "program",
    "phase",
    "value",
    "status",
    "source_page",
    "source_locator",
    "missing_reason",
)
CAPTURED_TABLE_COLUMNS = (
    "state",
    "sbir_p1_n",
    "sbir_p1_usd",
    "sttr_p1_n",
    "sttr_p1_usd",
    "sbir_p2_n",
    "sbir_p2_usd",
    "sttr_p2_n",
    "sttr_p2_usd",
    "sbir_tot_n",
    "sbir_tot_usd",
    "sttr_tot_n",
    "sttr_tot_usd",
    "all_tot_n",
    "all_tot_usd",
)
COUNT_COLUMNS = (
    "sbir_p1_n",
    "sttr_p1_n",
    "sbir_p2_n",
    "sttr_p2_n",
    "sbir_tot_n",
    "sttr_tot_n",
    "all_tot_n",
)
LEAF_COUNT_COLUMNS = {
    ("SBIR", "Phase I"): "sbir_p1_n",
    ("STTR", "Phase I"): "sttr_p1_n",
    ("SBIR", "Phase II"): "sbir_p2_n",
    ("STTR", "Phase II"): "sttr_p2_n",
}

# Exact mapping frozen by validation-design-v1.md. The versioned shared profile
# intentionally remains narrower than the general jurisdiction normalizer.
JURISDICTION_BY_NAME = SBA_ANNUAL_REPORT_JURISDICTIONS_V1


class StructuralComparisonError(ValueError):
    """Raised when a frozen structural-comparison contract is not satisfied."""


@dataclass(frozen=True)
class PinnedFile:
    """One explicitly located file with its portable reference and identity."""

    reference: str
    path: Path
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("pinned file reference must not be blank")
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError(f"invalid SHA-256 for {self.reference}: {self.sha256!r}")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError(f"invalid byte count for {self.reference}: {self.size_bytes!r}")


@dataclass(frozen=True)
class AnnualReportSource:
    """One annual-report PDF used by the comparison."""

    report_year: int
    table_number: str
    file: PinnedFile


@dataclass(frozen=True)
class CapturedTableSource:
    """One pinned count-table transcription derived from an annual-report PDF."""

    report_year: int
    table_number: str
    file: PinnedFile
    row_count: int

    def __post_init__(self) -> None:
        if type(self.row_count) is not int or self.row_count < 1:
            raise ValueError(
                f"invalid captured-table row count for FY{self.report_year}: {self.row_count!r}"
            )


@dataclass(frozen=True)
class ProductionInputs:
    """Every frozen input required to build the pre-validation count sidecar."""

    source_manifest: PinnedFile
    award_export: PinnedFile
    award_export_metadata: PinnedFile
    annual_reports: tuple[AnnualReportSource, ...]
    captured_tables: tuple[CapturedTableSource, ...]
    validation_design: PinnedFile
    validation_population: PinnedFile
    implementation: PinnedFile


@dataclass(frozen=True)
class CountComparisonProduct:
    """The count-only comparison and one non-decision diagnostic."""

    frame: pd.DataFrame
    dropped_blank_state_rows: int


@dataclass(frozen=True)
class MaterializationInputs:
    """Frozen artifacts checked after confirmatory validation has been recorded."""

    study_manifest: PinnedFile
    production_sidecar: PinnedFile
    validation_values: PinnedFile
    rendered_output: PinnedFile


@dataclass(frozen=True)
class MaterializationGateRecord:
    """Typed proof that the approved materialization boundary passed."""

    study_id: str
    cell_count: int
    validation_value_count: int
    production_sidecar_sha256: str
    validation_values_sha256: str
    rendered_output_sha256: str


Renderer = Callable[[pd.DataFrame], bytes]
PdfPageCounter = Callable[[Path], int]


def _verify_pin(pin: PinnedFile, *, label: str) -> None:
    if not pin.path.is_file():
        raise StructuralComparisonError(f"{label} is missing: {pin.path}")
    observed_bytes = pin.path.stat().st_size
    if observed_bytes != pin.size_bytes:
        raise StructuralComparisonError(
            f"{label} byte count mismatch: expected {pin.size_bytes}, observed {observed_bytes}"
        )
    observed_sha256 = file_sha256(pin.path)
    if observed_sha256 != pin.sha256:
        raise StructuralComparisonError(
            f"{label} SHA-256 mismatch: expected {pin.sha256}, observed {observed_sha256}"
        )


def _require_source_set(inputs: ProductionInputs) -> None:
    pdf_tables = {source.report_year: source.table_number for source in inputs.annual_reports}
    captured_tables = {source.report_year: source.table_number for source in inputs.captured_tables}
    if len(pdf_tables) != len(inputs.annual_reports) or pdf_tables != REPORT_TABLES:
        raise StructuralComparisonError(
            f"annual-report source set must be exactly {REPORT_TABLES}; observed {pdf_tables}"
        )
    if len(captured_tables) != len(inputs.captured_tables) or captured_tables != REPORT_TABLES:
        raise StructuralComparisonError(
            f"captured-table source set must be exactly {REPORT_TABLES}; observed {captured_tables}"
        )


def _production_pins(inputs: ProductionInputs) -> tuple[tuple[str, PinnedFile], ...]:
    return (
        ("source manifest", inputs.source_manifest),
        ("award export", inputs.award_export),
        ("award-export metadata sidecar", inputs.award_export_metadata),
        *(
            (f"FY{source.report_year} annual-report PDF", source.file)
            for source in inputs.annual_reports
        ),
        *(
            (f"FY{source.report_year} captured table", source.file)
            for source in inputs.captured_tables
        ),
        ("validation design", inputs.validation_design),
        ("validation population", inputs.validation_population),
        ("producer implementation", inputs.implementation),
    )


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StructuralComparisonError(f"{label} must be a JSON object")
    return value


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    observed = set(value)
    if observed != expected:
        raise StructuralComparisonError(
            f"{label} fields mismatch: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _load_source_manifest(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StructuralComparisonError(f"source manifest is invalid JSON: {exc}") from exc
    manifest = _require_mapping(raw, label="source manifest")
    _require_exact_fields(
        manifest,
        {
            "schema_version",
            "capture_gate",
            "sources",
            "captured_tables",
            "award_export_ordered_header",
            "captured_table_header",
            "header_fingerprint_procedure",
        },
        label="source manifest",
    )
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise StructuralComparisonError("source manifest schema_version must be 1")
    if manifest["header_fingerprint_procedure"] != HEADER_FINGERPRINT_PROCEDURE:
        raise StructuralComparisonError(
            "source manifest has the wrong header fingerprint procedure"
        )
    if manifest["award_export_ordered_header"] != list(SBIR_GOV_SOURCE_COLUMNS):
        raise StructuralComparisonError("source manifest has the wrong ordered award-export header")
    if manifest["captured_table_header"] != list(CAPTURED_TABLE_COLUMNS):
        raise StructuralComparisonError(
            "source manifest has the wrong ordered captured-table header"
        )

    gate = _require_mapping(manifest["capture_gate"], label="source manifest capture_gate")
    _require_exact_fields(
        gate,
        {"allowed", "blockers", "verified_on", "verification_note"},
        label="source manifest capture_gate",
    )
    if not isinstance(gate["allowed"], bool):
        raise StructuralComparisonError("source manifest capture_gate.allowed must be boolean")
    blockers = gate["blockers"]
    if not isinstance(blockers, list) or any(
        not isinstance(blocker, str) or not blocker.strip() for blocker in blockers
    ):
        raise StructuralComparisonError(
            "source manifest capture_gate.blockers must be a list of nonblank strings"
        )
    if (
        not isinstance(gate["verified_on"], str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", gate["verified_on"]) is None
    ):
        raise StructuralComparisonError(
            "source manifest capture_gate.verified_on must be an ISO date"
        )
    if not isinstance(gate["verification_note"], str) or not gate["verification_note"].strip():
        raise StructuralComparisonError(
            "source manifest capture_gate.verification_note must be nonblank"
        )
    if gate["allowed"] and blockers:
        raise StructuralComparisonError("open source capture gate cannot retain blockers")
    if not gate["allowed"]:
        if not blockers:
            raise StructuralComparisonError("closed source capture gate must name a blocker")
        raise StructuralComparisonError(f"source capture gate is closed: {'; '.join(blockers)}")
    return manifest


def _indexed_records(
    value: object, *, expected_ids: set[str], label: str
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise StructuralComparisonError(f"{label} must be a JSON array")
    records: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(value):
        record = _require_mapping(raw, label=f"{label}[{index}]")
        source_id = record.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise StructuralComparisonError(f"{label}[{index}].source_id must be nonblank")
        if source_id in records:
            raise StructuralComparisonError(f"{label} contains duplicate source_id {source_id!r}")
        records[source_id] = record
    if set(records) != expected_ids:
        raise StructuralComparisonError(
            f"{label} source IDs mismatch: expected={sorted(expected_ids)}, "
            f"observed={sorted(records)}"
        )
    return records


def _require_manifest_pin(
    record: Mapping[str, Any], pin: PinnedFile, *, path_field: str, label: str
) -> None:
    if record.get(path_field) != pin.reference:
        raise StructuralComparisonError(
            f"{label} path mismatch: expected {pin.reference!r}, observed {record.get(path_field)!r}"
        )
    if record.get("sha256") != pin.sha256 or record.get("size_bytes") != pin.size_bytes:
        raise StructuralComparisonError(f"{label} identity disagrees with its pinned file")


def _validate_source_manifest(
    manifest: Mapping[str, Any],
    inputs: ProductionInputs,
    *,
    pdf_page_counter: PdfPageCounter,
) -> None:
    source_records = _indexed_records(
        manifest["sources"],
        expected_ids={AWARD_EXPORT_SOURCE_ID, *ANNUAL_REPORT_SOURCE_IDS.values()},
        label="source manifest sources",
    )
    export_record = source_records[AWARD_EXPORT_SOURCE_ID]
    _require_manifest_pin(
        export_record,
        inputs.award_export,
        path_field="local_path",
        label="award-export source manifest entry",
    )
    if export_record.get("metadata_path") != inputs.award_export_metadata.reference:
        raise StructuralComparisonError(
            "award-export metadata sidecar path disagrees with the source manifest"
        )
    if export_record.get("column_count") != len(SBIR_GOV_SOURCE_COLUMNS):
        raise StructuralComparisonError("source manifest award-export column count is not 42")
    if export_record.get("ordered_header_sha256") != ordered_columns_sha256(
        SBIR_GOV_SOURCE_COLUMNS
    ):
        raise StructuralComparisonError("source manifest award-export header fingerprint mismatch")
    if type(export_record.get("row_count")) is not int or export_record["row_count"] < 0:
        raise StructuralComparisonError("source manifest award-export row_count is invalid")
    if (
        not isinstance(export_record.get("durable_uri"), str)
        or not export_record["durable_uri"].strip()
    ):
        raise StructuralComparisonError("award-export source lacks a durable URI")

    report_by_year = {source.report_year: source for source in inputs.annual_reports}
    for year, source_id in ANNUAL_REPORT_SOURCE_IDS.items():
        record = source_records[source_id]
        source = report_by_year[year]
        _require_manifest_pin(
            record,
            source.file,
            path_field="local_path",
            label=f"FY{year} annual-report source manifest entry",
        )
        if not isinstance(record.get("durable_uri"), str) or not record["durable_uri"].strip():
            raise StructuralComparisonError(f"FY{year} annual-report source lacks a durable URI")
        expected_page_count = record.get("page_count")
        if type(expected_page_count) is not int or expected_page_count < 1:
            raise StructuralComparisonError(f"FY{year} annual-report page_count is invalid")
        try:
            observed_page_count = pdf_page_counter(source.file.path)
        except Exception as exc:
            raise StructuralComparisonError(
                f"FY{year} annual-report page count could not be read: {exc}"
            ) from exc
        if type(observed_page_count) is not int or observed_page_count < 1:
            raise StructuralComparisonError(
                f"FY{year} annual-report page counter returned an invalid value: "
                f"{observed_page_count!r}"
            )
        if observed_page_count != expected_page_count:
            raise StructuralComparisonError(
                f"FY{year} annual-report page-count mismatch: expected {expected_page_count}, "
                f"observed {observed_page_count}"
            )

    captured_records = _indexed_records(
        manifest["captured_tables"],
        expected_ids=set(CAPTURED_TABLE_SOURCE_IDS.values()),
        label="source manifest captured_tables",
    )
    capture_by_year = {source.report_year: source for source in inputs.captured_tables}
    captured_header_sha256 = ordered_columns_sha256(CAPTURED_TABLE_COLUMNS)
    for year, source_id in CAPTURED_TABLE_SOURCE_IDS.items():
        record = captured_records[source_id]
        captured_source = capture_by_year[year]
        _require_manifest_pin(
            record,
            captured_source.file,
            path_field="path",
            label=f"FY{year} captured-table source manifest entry",
        )
        if record.get("row_count") != captured_source.row_count:
            raise StructuralComparisonError(
                f"FY{year} captured-table row count disagrees with the source manifest"
            )
        if record.get("column_count") != len(CAPTURED_TABLE_COLUMNS):
            raise StructuralComparisonError(
                f"FY{year} captured-table column count disagrees with the schema"
            )
        if record.get("ordered_header_sha256") != captured_header_sha256:
            raise StructuralComparisonError(f"FY{year} captured-table header fingerprint mismatch")


def verify_production_inputs(
    inputs: ProductionInputs, *, pdf_page_counter: PdfPageCounter
) -> Mapping[str, Any]:
    """Verify every source and contract artifact before any source is parsed."""

    _require_source_set(inputs)
    _verify_pin(inputs.source_manifest, label="source manifest")
    manifest = _load_source_manifest(inputs.source_manifest.path)
    for label, pin in _production_pins(inputs)[1:]:
        _verify_pin(pin, label=label)
    _validate_source_manifest(manifest, inputs, pdf_page_counter=pdf_page_counter)
    return manifest


def _read_csv(path: Path, *, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise StructuralComparisonError(f"{label} is not a readable CSV: {exc}") from exc


def _unit_id(target: str, row: pd.Series) -> str:
    phase = str(row["phase"]).replace(" ", "_")
    return ":".join(
        (
            target,
            str(row["report_year"]),
            str(row["jurisdiction"]),
            str(row["program"]),
            phase,
        )
    )


def load_validation_population(path: Path) -> pd.DataFrame:
    """Load and validate the frozen blank 1,264-value population."""

    population = _read_csv(path, label="validation population")
    if tuple(population.columns) != POPULATION_COLUMNS:
        raise StructuralComparisonError(
            "validation population schema mismatch: "
            f"expected {list(POPULATION_COLUMNS)}, observed {list(population.columns)}"
        )
    if len(population) != EXPECTED_VALIDATION_VALUE_COUNT:
        raise StructuralComparisonError(
            "validation population row-count mismatch: "
            f"expected {EXPECTED_VALIDATION_VALUE_COUNT}, observed {len(population)}"
        )
    if population["unit_id"].duplicated().any():
        raise StructuralComparisonError("validation population unit_id values must be unique")
    if not population["report_year"].str.fullmatch(r"[0-9]{4}").all():
        raise StructuralComparisonError("validation population contains an invalid report_year")
    population["report_year"] = population["report_year"].astype("int64")
    if set(population["report_year"]) != set(REPORT_TABLES):
        raise StructuralComparisonError("validation population has the wrong report-year set")
    if not population["jurisdiction"].str.fullmatch(r"[A-Z]{2}").all():
        raise StructuralComparisonError("validation population contains an invalid jurisdiction")
    if not set(population["program"]).issubset(PROGRAMS):
        raise StructuralComparisonError("validation population contains an invalid program")
    if not set(population["phase"]).issubset(PHASES):
        raise StructuralComparisonError("validation population contains an invalid phase")
    if set(population["target"]) != {"published_count", "recomputed_count"}:
        raise StructuralComparisonError("validation population has the wrong target set")
    expected_ids = population.apply(lambda row: _unit_id(str(row["target"]), row), axis=1)
    if not expected_ids.equals(population["unit_id"]):
        raise StructuralComparisonError("validation population unit_id does not match its key")
    target_counts = population.groupby(list(KEY_COLUMNS), dropna=False)["target"].agg(set)
    required_targets = {"published_count", "recomputed_count"}
    if (
        len(target_counts) != EXPECTED_CELL_COUNT
        or not target_counts.map(lambda values: values == required_targets).all()
    ):
        raise StructuralComparisonError(
            "validation population must contain both targets for exactly 632 cell keys"
        )
    return population.sort_values([*KEY_COLUMNS, "target"], kind="stable").reset_index(drop=True)


def _parse_count_column(frame: pd.DataFrame, column: str, *, label: str) -> None:
    values = frame[column]
    if not values.str.fullmatch(r"(?:0|[1-9][0-9]*)").all():
        raise StructuralComparisonError(f"{label}.{column} must contain nonnegative integers")
    frame[column] = values.astype("int64")


def _load_captured_counts(source: CapturedTableSource) -> pd.DataFrame:
    label = f"FY{source.report_year} captured table"
    frame = _read_csv(source.file.path, label=label)
    if tuple(frame.columns) != CAPTURED_TABLE_COLUMNS:
        raise StructuralComparisonError(
            f"{label} schema mismatch: expected {list(CAPTURED_TABLE_COLUMNS)}, "
            f"observed {list(frame.columns)}"
        )
    if len(frame) != source.row_count:
        raise StructuralComparisonError(
            f"{label} row-count mismatch: expected {source.row_count}, observed {len(frame)}"
        )
    if frame["state"].duplicated().any() or not frame["state"].str.fullmatch(r"[A-Z]{2}").all():
        raise StructuralComparisonError(f"{label} state keys must be unique two-letter codes")
    for column in COUNT_COLUMNS:
        _parse_count_column(frame, column, label=label)
    identities = {
        "sbir_tot_n": frame["sbir_p1_n"] + frame["sbir_p2_n"],
        "sttr_tot_n": frame["sttr_p1_n"] + frame["sttr_p2_n"],
        "all_tot_n": frame["sbir_tot_n"] + frame["sttr_tot_n"],
    }
    for total, expected in identities.items():
        mismatched = frame[total].ne(expected)
        if bool(mismatched.any()):
            states = frame.loc[mismatched, "state"].tolist()
            raise StructuralComparisonError(
                f"{label} fails the blocking {total} count identity for states {states}"
            )

    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        for (program, phase), column in LEAF_COUNT_COLUMNS.items():
            rows.append(
                {
                    "report_year": source.report_year,
                    "table_number": TABLE_NUMBERS[source.report_year],
                    "jurisdiction": record["state"],
                    "program": program,
                    "phase": phase,
                    "published_count": int(record[column]),
                }
            )
    return pd.DataFrame(rows)


def _cell_keys(population: pd.DataFrame) -> pd.DataFrame:
    return (
        population.loc[:, list(KEY_COLUMNS)]
        .drop_duplicates()
        .sort_values(list(KEY_COLUMNS), kind="stable")
        .reset_index(drop=True)
    )


def _require_exact_keys(frame: pd.DataFrame, expected: pd.DataFrame, *, label: str) -> None:
    observed = frame.loc[:, list(KEY_COLUMNS)].sort_values(list(KEY_COLUMNS), kind="stable")
    observed = observed.reset_index(drop=True)
    if frame.duplicated(list(KEY_COLUMNS)).any():
        raise StructuralComparisonError(f"{label} contains duplicate cell keys")
    if not observed.equals(expected):
        observed_keys = set(map(tuple, observed.itertuples(index=False, name=None)))
        expected_keys = set(map(tuple, expected.itertuples(index=False, name=None)))
        missing = sorted(expected_keys - observed_keys)[:5]
        extra = sorted(observed_keys - expected_keys)[:5]
        raise StructuralComparisonError(
            f"{label} key-set mismatch: missing={missing}, extra={extra}"
        )


def _published_counts(
    sources: tuple[CapturedTableSource, ...], population: pd.DataFrame
) -> pd.DataFrame:
    frame = pd.concat([_load_captured_counts(source) for source in sources], ignore_index=True)
    _require_exact_keys(frame, _cell_keys(population), label="captured published counts")
    return frame


def _recomputed_counts(
    inputs: ProductionInputs,
    population: pd.DataFrame,
    source_manifest: Mapping[str, Any],
) -> tuple[pd.DataFrame, int]:
    verified = load_verified_award_export(
        inputs.award_export.path,
        inputs.award_export_metadata.path,
    )
    metadata = verified.metadata
    if (
        metadata.sha256 != inputs.award_export.sha256
        or metadata.size_bytes != inputs.award_export.size_bytes
    ):
        raise StructuralComparisonError(
            "award-export metadata sidecar disagrees with the frozen source identity"
        )
    if metadata.award_grain is not AwardGrain.EXPORT_ROW_V1:
        raise StructuralComparisonError("award-export sidecar declares the wrong award grain")
    source_records = _indexed_records(
        source_manifest["sources"],
        expected_ids={AWARD_EXPORT_SOURCE_ID, *ANNUAL_REPORT_SOURCE_IDS.values()},
        label="source manifest sources",
    )
    if metadata.row_count != source_records[AWARD_EXPORT_SOURCE_ID]["row_count"]:
        raise StructuralComparisonError(
            "award-export parsed row count disagrees with the source manifest"
        )

    frame = verified.frame.loc[:, ["Award Year", "Program", "Phase", "State"]].copy()
    basis = FiscalYearBasis.AWARD_YEAR_FIELD_V1
    frame["report_year"] = [
        basis.parse(value, row_location=f"CSV record {index + 2}")
        for index, value in enumerate(frame["Award Year"])
    ]
    frame = frame[frame["report_year"].isin(REPORT_TABLES)].copy()
    invalid_programs = sorted(set(frame.loc[~frame["Program"].isin(PROGRAMS), "Program"]))
    if invalid_programs:
        raise StructuralComparisonError(
            f"retained award-export rows contain unexpected Program values: {invalid_programs}"
        )
    invalid_phases = sorted(set(frame.loc[~frame["Phase"].isin(PHASES), "Phase"]))
    if invalid_phases:
        raise StructuralComparisonError(
            f"retained award-export rows contain unexpected Phase values: {invalid_phases}"
        )
    frame["report_year"] = frame["report_year"].astype("int64")
    blank_state = frame["State"].astype(str).str.strip().eq("")
    dropped_blank = int(blank_state.sum())
    frame = frame.loc[~blank_state].copy()
    frame["jurisdiction"] = frame["State"].map(
        lambda value: normalize_us_jurisdiction(
            value,
            profile=USJurisdictionProfile.SBA_ANNUAL_REPORT_TABLE_V1,
        )
    )
    unmapped = sorted(set(frame.loc[frame["jurisdiction"].isna(), "State"]))
    if unmapped:
        raise StructuralComparisonError(
            f"award export contains unmapped nonblank State values: {unmapped}"
        )
    grouped = (
        frame.groupby(["report_year", "jurisdiction", "Program", "Phase"], dropna=False)
        .size()
        .rename("recomputed_count")
        .reset_index()
        .rename(columns={"Program": "program", "Phase": "phase"})
    )
    keys = _cell_keys(population)
    observed_keys = set(
        map(tuple, grouped.loc[:, list(KEY_COLUMNS)].itertuples(index=False, name=None))
    )
    expected_keys = set(map(tuple, keys.itertuples(index=False, name=None)))
    extra = sorted(observed_keys - expected_keys)
    if extra:
        raise StructuralComparisonError(
            f"award-export counts contain keys outside the frozen population: {extra[:5]}"
        )
    result = keys.merge(grouped, on=list(KEY_COLUMNS), how="left", validate="one_to_one")
    result["recomputed_count"] = result["recomputed_count"].fillna(0).astype("int64")
    return result, dropped_blank


def validate_count_sidecar(frame: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    """Validate exact schema, keys, arithmetic, and non-inferential status values."""

    if tuple(frame.columns) != COUNT_SIDECAR_COLUMNS:
        raise StructuralComparisonError(
            "production count sidecar schema mismatch: "
            f"expected {list(COUNT_SIDECAR_COLUMNS)}, observed {list(frame.columns)}"
        )
    if len(frame) != EXPECTED_CELL_COUNT:
        raise StructuralComparisonError(
            f"production count sidecar row-count mismatch: expected 632, observed {len(frame)}"
        )
    _require_exact_keys(frame, _cell_keys(population), label="production count sidecar")
    if not pd.api.types.is_integer_dtype(frame["table_number"]):
        raise StructuralComparisonError(
            "production count sidecar table_number must contain integers"
        )
    expected_tables = frame["report_year"].map(TABLE_NUMBERS)
    if not frame["table_number"].equals(expected_tables):
        raise StructuralComparisonError(
            "production count sidecar table_number does not match report_year"
        )
    for column in ("published_count", "recomputed_count", "absolute_difference"):
        if not pd.api.types.is_integer_dtype(frame[column]) or bool(frame[column].lt(0).any()):
            raise StructuralComparisonError(
                f"production count sidecar {column} must contain nonnegative integers"
            )
    if not pd.api.types.is_integer_dtype(frame["signed_difference"]):
        raise StructuralComparisonError(
            "production count sidecar signed_difference must contain integers"
        )
    expected_signed = frame["recomputed_count"] - frame["published_count"]
    if not frame["signed_difference"].equals(expected_signed):
        raise StructuralComparisonError(
            "production count sidecar has an incorrect signed difference"
        )
    if not frame["absolute_difference"].equals(expected_signed.abs()):
        raise StructuralComparisonError(
            "production count sidecar has an incorrect absolute difference"
        )
    expected_status = expected_signed.map(lambda value: "exact" if value == 0 else "unresolved")
    if not frame["comparison_status"].equals(expected_status):
        raise StructuralComparisonError(
            "production count sidecar must label unequal cells unresolved and equal cells exact"
        )
    return frame.sort_values(list(KEY_COLUMNS), kind="stable").reset_index(drop=True)


def build_count_comparison(
    inputs: ProductionInputs, *, pdf_page_counter: PdfPageCounter
) -> CountComparisonProduct:
    """Build the 632-row count-only product after all pre-use checks pass."""

    source_manifest = verify_production_inputs(inputs, pdf_page_counter=pdf_page_counter)
    population = load_validation_population(inputs.validation_population.path)
    published = _published_counts(inputs.captured_tables, population)
    recomputed, dropped_blank = _recomputed_counts(inputs, population, source_manifest)
    result = published.merge(
        recomputed,
        on=list(KEY_COLUMNS),
        how="inner",
        validate="one_to_one",
    )
    result["signed_difference"] = result["recomputed_count"] - result["published_count"]
    result["absolute_difference"] = result["signed_difference"].abs()
    result["comparison_status"] = result["signed_difference"].map(
        lambda value: "exact" if value == 0 else "unresolved"
    )
    result = result.loc[:, list(COUNT_SIDECAR_COLUMNS)]
    return CountComparisonProduct(
        frame=validate_count_sidecar(result, population),
        dropped_blank_state_rows=dropped_blank,
    )


def count_sidecar_bytes(frame: pd.DataFrame, population: pd.DataFrame) -> bytes:
    """Serialize a validated count product deterministically."""

    validated = validate_count_sidecar(frame.copy(), population)
    return validated.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as file:
        temporary = Path(file.name)
        file.write(payload)
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def produce_count_sidecar(
    inputs: ProductionInputs,
    output_path: Path,
    *,
    pdf_page_counter: PdfPageCounter,
) -> CountComparisonProduct:
    """Write the deterministic pre-validation production sidecar."""

    product = build_count_comparison(inputs, pdf_page_counter=pdf_page_counter)
    population = load_validation_population(inputs.validation_population.path)
    _write_atomic(output_path, count_sidecar_bytes(product.frame, population))
    return product


def _read_count_sidecar(pin: PinnedFile, population: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(pin.path, label="production count sidecar")
    for column in (
        "report_year",
        "table_number",
        "published_count",
        "recomputed_count",
        "signed_difference",
        "absolute_difference",
    ):
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
        except (KeyError, TypeError, ValueError) as exc:
            raise StructuralComparisonError(
                f"production count sidecar {column} must contain integers"
            ) from exc
    return validate_count_sidecar(frame, population)


def _production_validation_values(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        for target in ("published_count", "recomputed_count"):
            row = {column: record[column] for column in KEY_COLUMNS}
            row["target"] = target
            row["unit_id"] = _unit_id(target, pd.Series(row))
            row["value"] = record[target]
            rows.append(row)
    return (
        pd.DataFrame(rows, columns=(*POPULATION_COLUMNS, "value"))
        .sort_values("unit_id", kind="stable")
        .reset_index(drop=True)
    )


def verify_validation_values(path: Path, production: pd.DataFrame) -> int:
    """Require one equal independent value for every frozen validation unit."""

    observed = _read_csv(path, label="validation values")
    if tuple(observed.columns) != VALIDATION_VALUE_COLUMNS:
        raise StructuralComparisonError(
            "validation values schema mismatch: "
            f"expected {list(VALIDATION_VALUE_COLUMNS)}, observed {list(observed.columns)}"
        )
    if len(observed) != EXPECTED_VALIDATION_VALUE_COUNT or observed["unit_id"].duplicated().any():
        raise StructuralComparisonError(
            "validation values must contain one row for each of the 1,264 frozen units"
        )
    try:
        observed["report_year"] = pd.to_numeric(observed["report_year"], errors="raise").astype(
            "int64"
        )
    except (TypeError, ValueError) as exc:
        raise StructuralComparisonError("validation values report_year must be integers") from exc
    invalid_statuses = sorted(set(observed["status"]) - {"observed", "missing"})
    if invalid_statuses:
        raise StructuralComparisonError(
            f"validation values contain invalid status values: {invalid_statuses}"
        )
    missing = observed["status"].eq("missing")
    observed_status = observed["status"].eq("observed")
    if not observed.loc[observed_status, "value"].str.fullmatch(r"(?:0|[1-9][0-9]*)").all():
        raise StructuralComparisonError("observed validation values must be nonnegative integers")
    if not observed.loc[missing, "value"].eq("").all():
        raise StructuralComparisonError("missing validation values must have an empty value")
    if not observed.loc[missing, "missing_reason"].str.strip().ne("").all():
        raise StructuralComparisonError("missing validation values must name a missing_reason")
    if not observed.loc[observed_status, "missing_reason"].eq("").all():
        raise StructuralComparisonError("observed validation values cannot name a missing_reason")
    published = observed["target"].eq("published_count")
    recomputed = observed["target"].eq("recomputed_count")
    expected_tables = observed["report_year"].map(TABLE_NUMBERS).astype("Int64").astype(str)
    if not observed.loc[published, "table_number"].equals(expected_tables.loc[published]):
        raise StructuralComparisonError("published validation values have the wrong table_number")
    if not observed.loc[recomputed, "table_number"].eq("").all():
        raise StructuralComparisonError(
            "recomputed validation values must leave table_number empty"
        )
    if not observed.loc[published, "source_page"].str.strip().ne("").all():
        raise StructuralComparisonError("published validation values require source_page")
    if not observed.loc[recomputed, "source_page"].eq("").all():
        raise StructuralComparisonError("recomputed validation values must leave source_page empty")
    if not observed["source_locator"].str.strip().ne("").all():
        raise StructuralComparisonError("every validation value requires source_locator")
    expected = _production_validation_values(production)
    observed = observed.sort_values("unit_id", kind="stable").reset_index(drop=True)
    if not observed.loc[:, list(POPULATION_COLUMNS)].equals(
        expected.loc[:, list(POPULATION_COLUMNS)]
    ):
        raise StructuralComparisonError("validation values key set does not match production")
    if bool(missing.any()):
        units = observed.loc[observed["status"].eq("missing"), "unit_id"].tolist()[:5]
        raise StructuralComparisonError(f"validation values are missing for units {units}")
    observed["value"] = observed["value"].astype("int64")
    unequal = observed["value"].ne(expected["value"])
    if bool(unequal.any()):
        units = observed.loc[unequal, "unit_id"].tolist()[:5]
        raise StructuralComparisonError(f"validation values disagree for units {units}")
    return len(observed)


def _require_frozen_pins(manifest: StudyManifest, pins: Iterable[PinnedFile]) -> None:
    frozen = {artifact.path: artifact.sha256 for artifact in manifest.frozen_artifacts}
    for pin in pins:
        observed = frozen.get(pin.reference)
        if observed != pin.sha256:
            raise StructuralComparisonError(
                f"study manifest frozen artifact mismatch for {pin.reference}: "
                f"expected {pin.sha256}, observed {observed}"
            )


def _verify_manifest(
    manifest: StudyManifest,
    production_inputs: ProductionInputs,
    *,
    validation_value_count: int,
) -> None:
    if manifest.study_id != STUDY_ID:
        raise StructuralComparisonError(
            f"study manifest has wrong study_id: expected {STUDY_ID}, observed {manifest.study_id}"
        )
    if manifest.evidence_status is not EvidenceStatus.APPROVED:
        raise StructuralComparisonError(
            "approved materialization requires evidence_status approved"
        )
    if not manifest.materialization.allowed:
        blockers = "; ".join(manifest.materialization.blockers)
        raise StructuralComparisonError(f"approved materialization is blocked: {blockers}")
    design = manifest.validation_design
    result = manifest.validation_result
    if design is None or design.threshold_basis is not ThresholdBasis.COUNT_ON_FROZEN_POPULATION:
        raise StructuralComparisonError(
            "approved materialization requires a count-on-frozen-population validation design"
        )
    if design.threshold_value != EXPECTED_VALIDATION_VALUE_COUNT:
        raise StructuralComparisonError(
            "validation design threshold must require all 1,264 frozen values"
        )
    if design.frozen_population_artifact != production_inputs.validation_population.reference:
        raise StructuralComparisonError(
            "validation design does not name the producer's frozen population"
        )
    if result is None or not result.threshold_met:
        raise StructuralComparisonError(
            "approved materialization requires validation_result.threshold_met true"
        )
    if (
        result.design_path != production_inputs.validation_design.reference
        or result.design_sha256 != production_inputs.validation_design.sha256
    ):
        raise StructuralComparisonError(
            "validation result does not name the producer's frozen design"
        )
    if result.numerator != validation_value_count or result.denominator != validation_value_count:
        raise StructuralComparisonError(
            "validation result count does not match the reconciled validation values"
        )
    if (
        result.interval_low != 1.0
        or result.interval_high != 1.0
        or result.interval_method != EXACT_INTERVAL_METHOD
    ):
        raise StructuralComparisonError(
            "validation result must record the exact complete-population point interval"
        )
    implementation_refs = {
        (implementation.path, implementation.symbol) for implementation in manifest.implementation
    }
    if (
        production_inputs.implementation.reference,
        "produce_count_sidecar",
    ) not in implementation_refs:
        raise StructuralComparisonError(
            "study manifest does not name the frozen producer implementation"
        )


def verify_approved_materialization(
    production_inputs: ProductionInputs,
    materialization_inputs: MaterializationInputs,
    *,
    pdf_page_counter: PdfPageCounter,
    renderer: Renderer,
) -> MaterializationGateRecord:
    """Fail closed unless the frozen, validated, rendered product is exact."""

    for label, pin in (
        ("study manifest", materialization_inputs.study_manifest),
        ("production count sidecar", materialization_inputs.production_sidecar),
        ("validation values", materialization_inputs.validation_values),
        ("rendered output", materialization_inputs.rendered_output),
    ):
        _verify_pin(pin, label=label)
    try:
        manifest = load_study_manifest(materialization_inputs.study_manifest.path)
    except Exception as exc:
        raise StructuralComparisonError(f"study manifest is invalid: {exc}") from exc

    product = build_count_comparison(
        production_inputs,
        pdf_page_counter=pdf_page_counter,
    )
    population = load_validation_population(production_inputs.validation_population.path)
    persisted = _read_count_sidecar(materialization_inputs.production_sidecar, population)
    if count_sidecar_bytes(product.frame, population) != count_sidecar_bytes(persisted, population):
        raise StructuralComparisonError(
            "frozen production count sidecar does not match the current producer output"
        )
    validation_value_count = verify_validation_values(
        materialization_inputs.validation_values.path,
        persisted,
    )
    _verify_manifest(
        manifest,
        production_inputs,
        validation_value_count=validation_value_count,
    )
    _require_frozen_pins(
        manifest,
        (
            *(pin for _, pin in _production_pins(production_inputs)),
            materialization_inputs.production_sidecar,
            materialization_inputs.validation_values,
            materialization_inputs.rendered_output,
        ),
    )
    regenerated = renderer(persisted.copy())
    if not isinstance(regenerated, bytes):
        raise StructuralComparisonError("renderer must return bytes")
    if regenerated != materialization_inputs.rendered_output.path.read_bytes():
        raise StructuralComparisonError("renderer round-trip mismatch")
    return MaterializationGateRecord(
        study_id=manifest.study_id,
        cell_count=len(persisted),
        validation_value_count=validation_value_count,
        production_sidecar_sha256=materialization_inputs.production_sidecar.sha256,
        validation_values_sha256=materialization_inputs.validation_values.sha256,
        rendered_output_sha256=materialization_inputs.rendered_output.sha256,
    )


__all__ = [
    "CAPTURED_TABLE_COLUMNS",
    "COUNT_SIDECAR_COLUMNS",
    "EXPECTED_CELL_COUNT",
    "EXPECTED_VALIDATION_VALUE_COUNT",
    "AnnualReportSource",
    "CapturedTableSource",
    "CountComparisonProduct",
    "MaterializationGateRecord",
    "MaterializationInputs",
    "PdfPageCounter",
    "PinnedFile",
    "ProductionInputs",
    "STUDY_ID",
    "StructuralComparisonError",
    "build_count_comparison",
    "count_sidecar_bytes",
    "load_validation_population",
    "produce_count_sidecar",
    "validate_count_sidecar",
    "verify_approved_materialization",
    "verify_production_inputs",
    "verify_validation_values",
]

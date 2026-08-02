"""Dagster surface for the deterministic Phase III census.

NOTE: do NOT add ``from __future__ import annotations`` — it breaks Dagster runtime
context validation in this repository.
"""

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from sbir_analytics.assets.phase_iii_candidates.pairing import build_uei_pairs
from sbir_analytics.assets.phase_transition.sbir_gov_source import (
    SbirGovSourceError,
    sha256_file,
    verify_sbir_gov_materialization,
)

from .criteria import (
    CensusInputError,
    build_dropoff_ladder,
    build_sensitivity_diagnostics,
    build_sensitivity_grid,
    ordered_clause_metadata,
    validate_source_columns,
)


try:
    from dagster import (
        AssetCheckResult,
        AssetCheckSeverity,
        MetadataValue,
        Output,
        asset,
        asset_check,
    )
except Exception:  # pragma: no cover - test-only shim

    def asset(*_args: Any, **_kwargs: Any):  # type: ignore[no-redef]
        def _wrap(fn):
            return fn

        return _wrap

    def asset_check(*_args: Any, **_kwargs: Any):  # type: ignore[no-redef]
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore[no-redef]
        def __init__(self, value: Any, metadata: dict | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore[no-redef]
        @staticmethod
        def json(value: Any) -> Any:
            return value

    class AssetCheckSeverity:  # type: ignore[no-redef]
        ERROR = "ERROR"

    class AssetCheckResult:  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            passed: bool,
            severity: Any,
            description: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            self.passed = passed
            self.severity = severity
            self.description = description
            self.metadata = metadata or {}


DROP_OFF_OUTPUT_PATH = Path("data/processed/phase_iii_census_dropoff.parquet")
SENSITIVITY_OUTPUT_PATH = Path("data/processed/phase_iii_census_sensitivity.parquet")
CONTRACTS_PRIMARY_PATH = Path("data/transition/contracts_ingestion.parquet")
CONTRACTS_FALLBACK_PATH = Path("data/processed/contracts_ingestion.parquet")
CENSUS_SBIR_AWARDS_PATH = Path("data/processed/phase_iii_census_sbir_awards.parquet")
PHASE_II_AWARDS_PATH = Path("data/processed/phase_ii_awards.parquet")
DATA_CUT_ENV = "SBIR_ETL__PHASE_III_CENSUS__DATA_CUT_DATE"
SBIR_AWARDS_ENV = "SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH"
PHASE_II_OUTPUT_ENV = "SBIR_ETL__PHASE_TRANSITION__PHASE_II_OUTPUT_PATH"
FROZEN_SPEC_REVISION = "phase-0-r7"
FROZEN_SPEC_RELATIVE_PATH = Path("specs/phase-iii-census/design.md")
AMENDMENTS_LOG_RELATIVE_PATH = Path("specs/phase-iii-census/amendments.md")


def _find_resource_root() -> Path:
    """Find the checkout or container root that holds the frozen census inputs."""

    for root in Path(__file__).resolve().parents:
        if all(
            (root / relative_path).is_file()
            for relative_path in (FROZEN_SPEC_RELATIVE_PATH, AMENDMENTS_LOG_RELATIVE_PATH)
        ):
            return root
    raise RuntimeError("Phase III census frozen specification files are not installed")


_REPOSITORY_ROOT = _find_resource_root()
FROZEN_SPEC_PATH = _REPOSITORY_ROOT / FROZEN_SPEC_RELATIVE_PATH
AMENDMENTS_LOG_PATH = _REPOSITORY_ROOT / AMENDMENTS_LOG_RELATIVE_PATH
FROZEN_SPEC_SHA256 = "33b5918026fe2f98e3fa693afbe498653a328274adec03a5c827bf2ac0df6df9"
AMENDMENTS_LOG_SHA256 = "24ead99679a4e6948b3704e1375a2f9f7ba1e2b426273d490d87156efd21e5ab"


def _verified_raw_digest(path: Path, expected_sha256: str, *, label: str) -> str:
    """Hash exact file bytes and fail closed on absence or mismatch."""

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise CensusInputError(f"{label} is missing or unreadable at {path}: {exc}") from exc
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise CensusInputError(
            f"{label} SHA-256 mismatch at {path}: expected {expected_sha256}, found {actual_sha256}"
        )
    return actual_sha256


def verify_frozen_spec() -> dict[str, str]:
    """Verify the executable Phase 0 freeze before any census input is read."""

    spec_sha256 = _verified_raw_digest(
        FROZEN_SPEC_PATH,
        FROZEN_SPEC_SHA256,
        label="Frozen Phase III census design",
    )
    amendments_sha256 = _verified_raw_digest(
        AMENDMENTS_LOG_PATH,
        AMENDMENTS_LOG_SHA256,
        label="Phase III census amendment log",
    )
    return {
        "revision": FROZEN_SPEC_REVISION,
        "spec_path": FROZEN_SPEC_RELATIVE_PATH.as_posix(),
        "spec_sha256": spec_sha256,
        "amendments_path": AMENDMENTS_LOG_RELATIVE_PATH.as_posix(),
        "amendments_sha256": amendments_sha256,
    }


def parse_census_data_cut_date(raw: str | None = None) -> date:
    """Parse the required snapshot cutoff without a wall-clock fallback."""

    value = raw if raw is not None else os.getenv(DATA_CUT_ENV)
    if value is None or not value.strip():
        raise CensusInputError(
            f"Set {DATA_CUT_ENV} to the source snapshot cutoff in ISO YYYY-MM-DD format"
        )
    normalized = value.strip()
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError as exc:
        raise CensusInputError(f"{DATA_CUT_ENV} must be an ISO YYYY-MM-DD date") from exc
    if parsed.isoformat() != normalized:
        raise CensusInputError(f"{DATA_CUT_ENV} must be an ISO YYYY-MM-DD date")
    return parsed


def _load_contracts() -> tuple[pd.DataFrame, Path]:
    """Read the same contract parquet path used by the retrospective candidate asset."""

    path = CONTRACTS_PRIMARY_PATH
    if not path.exists():
        path = CONTRACTS_FALLBACK_PATH
    if not path.exists():
        return pd.DataFrame(), path
    checks_path = path.with_suffix(".checks.json")
    if not checks_path.is_file():
        raise CensusInputError(
            f"Contract source at {path} has no provenance manifest at {checks_path}"
        )
    try:
        checks = json.loads(checks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusInputError(f"Contract provenance manifest is unreadable: {exc}") from exc
    if not isinstance(checks, Mapping):
        raise CensusInputError("Contract provenance manifest must be a JSON object")
    source = checks.get("source_provenance")
    if not isinstance(source, Mapping):
        raise CensusInputError("Contract provenance manifest has no source_provenance record")
    required = {
        "canonical_table",
        "physical_table",
        "member",
        "ordered_columns_sha256",
        "column_count",
        "toc_sha256",
        "vendor_filter_sha256",
        "output_sha256",
        "provenance_version",
    }
    missing = sorted(required - set(source))
    if missing:
        raise CensusInputError(
            f"Contract provenance manifest is missing required fields: {missing}"
        )
    if source.get("canonical_table") != "rpt.transaction_search":
        raise CensusInputError("Contract source is not the canonical transaction_search table")
    if source.get("physical_table") not in {
        "rpt.transaction_search",
        "rpt.transaction_search_fpds",
    }:
        raise CensusInputError("Contract source is not the verified FPDS transaction relation")
    if (
        not isinstance(source.get("provenance_version"), int)
        or isinstance(source["provenance_version"], bool)
        or source["provenance_version"] != 1
    ):
        raise CensusInputError("Contract provenance manifest uses an unsupported version")
    member = source.get("member")
    if not isinstance(member, str) or not member.endswith(".dat.gz"):
        raise CensusInputError("Contract provenance manifest has an invalid archive member")
    column_count = source.get("column_count")
    if not isinstance(column_count, int) or isinstance(column_count, bool) or column_count <= 0:
        raise CensusInputError("Contract provenance manifest has an invalid column count")
    for key in (
        "ordered_columns_sha256",
        "toc_sha256",
        "vendor_filter_sha256",
        "output_sha256",
    ):
        value = source.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value.lower())
        ):
            raise CensusInputError(f"Contract provenance manifest has an invalid {key} fingerprint")
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    if source.get("output_sha256") != digest.hexdigest():
        raise CensusInputError("Contract parquet checksum does not match its provenance manifest")
    try:
        return pd.read_parquet(path), path
    except Exception as exc:  # pragma: no cover - defensive I/O boundary
        raise CensusInputError(f"Failed to read contract source at {path}: {exc}") from exc


def _assert_prior_frames_equal(persisted: pd.DataFrame, in_memory: pd.DataFrame) -> None:
    """Compare exact values after canonicalizing only dtype-specific missing values."""

    persisted_comparable = persisted.astype(object).where(persisted.notna(), None)
    in_memory_comparable = in_memory.astype(object).where(in_memory.notna(), None)
    pd.testing.assert_frame_equal(
        persisted_comparable.reset_index(drop=True),
        in_memory_comparable.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )


def _verify_phase_ii_provenance(priors: pd.DataFrame, contracts_path: Path) -> tuple[Path, Path]:
    """Require the census-dedicated v2 source and its exact persisted prior frame."""

    selected_sbir = Path(os.getenv(SBIR_AWARDS_ENV) or CENSUS_SBIR_AWARDS_PATH)
    if not selected_sbir.is_file():
        raise CensusInputError(
            "The Phase III census requires the dedicated v2 SBIR.gov source at "
            f"{selected_sbir}; set {SBIR_AWARDS_ENV} to an equivalent v2 artifact"
        )
    try:
        sbir_frame = pd.read_parquet(selected_sbir)
        sbir_manifest = verify_sbir_gov_materialization(selected_sbir, sbir_frame)
    except (OSError, SbirGovSourceError) as exc:
        raise CensusInputError(f"SBIR.gov census-source provenance failed: {exc}") from exc

    phase_ii_path = Path(os.getenv(PHASE_II_OUTPUT_ENV) or PHASE_II_AWARDS_PATH)
    phase_ii_checks_path = phase_ii_path.with_suffix(".checks.json")
    if not phase_ii_checks_path.is_file():
        raise CensusInputError(
            f"Phase II prior frame has no provenance manifest: {phase_ii_checks_path}"
        )
    try:
        phase_ii_checks = json.loads(phase_ii_checks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusInputError(f"Phase II provenance manifest is unreadable: {exc}") from exc
    if not isinstance(phase_ii_checks, Mapping):
        raise CensusInputError("Phase II provenance manifest must be a JSON object")

    inputs = phase_ii_checks.get("inputs")
    output = phase_ii_checks.get("output")
    if (
        phase_ii_checks.get("schema_version") != "phase-ii-awards-v2"
        or phase_ii_checks.get("ok") is not True
        or not isinstance(inputs, Mapping)
        or not isinstance(output, Mapping)
    ):
        raise CensusInputError("Phase II provenance manifest has an unsupported schema")
    if inputs.get("sbir_awards_v2_verified") is not True:
        raise CensusInputError("Phase II priors were not built from a verified v2 SBIR.gov source")
    recorded_contracts = inputs.get("contracts_path")
    if (
        inputs.get("contracts_exists") is not True
        or not isinstance(recorded_contracts, str)
        or Path(recorded_contracts).resolve() != contracts_path.resolve()
        or inputs.get("contracts_sha256") != sha256_file(contracts_path)
    ):
        raise CensusInputError("Phase II priors were built from a different contract source")
    recorded_input = inputs.get("sbir_awards_path")
    if (
        not isinstance(recorded_input, str)
        or Path(recorded_input).resolve() != selected_sbir.resolve()
    ):
        raise CensusInputError("Phase II priors were built from a different SBIR.gov source")
    recorded_sbir = inputs.get("sbir_awards_v2")
    if not isinstance(recorded_sbir, Mapping):
        raise CensusInputError("Phase II provenance does not embed the v2 SBIR.gov manifest")
    recorded_sbir_output = recorded_sbir.get("output")
    if (
        not isinstance(recorded_sbir_output, Mapping)
        or recorded_sbir_output.get("sha256") != sbir_manifest["output"]["sha256"]
    ):
        raise CensusInputError("Phase II priors record a different SBIR.gov source checksum")

    if not phase_ii_path.is_file() or output.get("sha256") != sha256_file(phase_ii_path):
        raise CensusInputError("Phase II parquet checksum does not match its provenance manifest")
    if output.get("rows") != len(priors) or output.get("ordered_columns") != list(priors.columns):
        raise CensusInputError("Phase II prior frame shape does not match its manifest")
    try:
        persisted_priors = pd.read_parquet(phase_ii_path)
        # Parquet round-trips object-backed missing values as dtype-specific nulls.
        # Canonicalize only missing representations; all nonmissing values, row order,
        # and column order must still match exactly.
        _assert_prior_frames_equal(persisted_priors, priors)
    except (OSError, AssertionError) as exc:
        raise CensusInputError("Phase II prior frame differs from its persisted artifact") from exc
    return selected_sbir, phase_ii_path


@asset(
    name="phase_iii_census",
    group_name="phase_iii_census",
    compute_kind="pandas",
    description=(
        "Deterministic label-free census of exact-UEI Phase II × contract pairs. "
        "Writes the frozen cumulative drop-off ladder and all six sensitivity cells; "
        "does not call the Phase III scorer or select a headline cell."
    ),
)
def phase_iii_census(
    context=None,
    validated_phase_ii_awards: pd.DataFrame | None = None,
):
    """Build and persist the two frozen Phase 1 audit tables."""

    freeze_record = verify_frozen_spec()
    priors = validated_phase_ii_awards
    if priors is None:
        priors = pd.DataFrame()
    contracts, contracts_path = _load_contracts()
    sbir_awards_path, phase_ii_awards_path = _verify_phase_ii_provenance(priors, contracts_path)
    data_cut = parse_census_data_cut_date()
    log = getattr(context, "log", logger) if context is not None else logger

    validate_source_columns(priors, contracts)
    pairs = build_uei_pairs(priors, contracts)
    dropoff = build_dropoff_ladder(pairs, data_cut)
    sensitivity = build_sensitivity_grid(pairs, data_cut)

    DROP_OFF_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dropoff.to_parquet(DROP_OFF_OUTPUT_PATH, index=False)
    sensitivity.to_parquet(SENSITIVITY_OUTPUT_PATH, index=False)

    metadata: dict[str, Any] = {
        "dropoff_path": str(DROP_OFF_OUTPUT_PATH),
        "sensitivity_path": str(SENSITIVITY_OUTPUT_PATH),
        "contracts_path": str(contracts_path),
        "sbir_awards_path": str(sbir_awards_path),
        "phase_ii_awards_path": str(phase_ii_awards_path),
        "census_data_cut_date": data_cut.isoformat(),
        "frozen_spec_path": freeze_record["spec_path"],
        "frozen_spec_sha256": freeze_record["spec_sha256"],
        "frozen_spec_revision": freeze_record["revision"],
        "amendments_log_path": freeze_record["amendments_path"],
        "amendments_log_sha256": freeze_record["amendments_sha256"],
        "ordered_clauses": MetadataValue.json(ordered_clause_metadata()),
        "reproducibility": MetadataValue.json(
            {"stochastic": False, "seed": None, "data_cut_date": data_cut.isoformat()}
        ),
    }
    log.info(
        "phase_iii_census wrote both audit tables",
        extra={
            "dropoff_path": str(DROP_OFF_OUTPUT_PATH),
            "sensitivity_path": str(SENSITIVITY_OUTPUT_PATH),
            "data_cut_date": data_cut.isoformat(),
        },
    )
    return Output({"dropoff": dropoff, "sensitivity": sensitivity}, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset=phase_iii_census,
    name="phase_iii_census_one_factor_sensitivity",
    description=(
        "Report all seven adjacent one-factor sensitivity contrasts and flag only "
        "window effects that dominate the core-clause ladder."
    ),
    blocking=True,
)
def phase_iii_census_one_factor_sensitivity() -> AssetCheckResult:
    """Read both persisted audit tables and evaluate the approved diagnostic."""

    try:
        dropoff = pd.read_parquet(DROP_OFF_OUTPUT_PATH)
        sensitivity = pd.read_parquet(SENSITIVITY_OUTPUT_PATH)
        diagnostics, reasons = build_sensitivity_diagnostics(dropoff, sensitivity)
    except (OSError, CensusInputError, ValueError) as exc:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="Phase III census one-factor diagnostics could not be evaluated",
            metadata={
                "dropoff_path": str(DROP_OFF_OUTPUT_PATH),
                "sensitivity_path": str(SENSITIVITY_OUTPUT_PATH),
                "error": str(exc),
            },
        )

    # JSON round-tripping converts pandas/numpy scalars to plain JSON values and
    # preserves the explicit null used to represent an infinite count fold.
    diagnostic_records = json.loads(diagnostics.to_json(orient="records"))
    passed = not reasons
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR,
        description=(
            "All seven one-factor contrasts are reported; no review condition triggered"
            if passed
            else "One or more adjacent window effects require review; artifacts remain persisted"
        ),
        metadata={
            "dropoff_path": str(DROP_OFF_OUTPUT_PATH),
            "sensitivity_path": str(SENSITIVITY_OUTPUT_PATH),
            "comparison_count": len(diagnostic_records),
            "one_factor_diagnostics": MetadataValue.json(diagnostic_records),
            "checkpoint_reasons": MetadataValue.json(reasons),
        },
    )


__all__ = [
    "AMENDMENTS_LOG_PATH",
    "AMENDMENTS_LOG_SHA256",
    "DATA_CUT_ENV",
    "CENSUS_SBIR_AWARDS_PATH",
    "DROP_OFF_OUTPUT_PATH",
    "FROZEN_SPEC_PATH",
    "FROZEN_SPEC_REVISION",
    "FROZEN_SPEC_SHA256",
    "SENSITIVITY_OUTPUT_PATH",
    "SBIR_AWARDS_ENV",
    "parse_census_data_cut_date",
    "phase_iii_census",
    "phase_iii_census_one_factor_sensitivity",
    "verify_frozen_spec",
]

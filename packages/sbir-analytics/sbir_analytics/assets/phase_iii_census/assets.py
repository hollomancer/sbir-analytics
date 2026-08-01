"""Dagster surface for the deterministic Phase III census.

NOTE: do NOT add ``from __future__ import annotations`` — it breaks Dagster runtime
context validation in this repository.
"""

import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from sbir_analytics.assets.phase_iii_candidates.pairing import build_uei_pairs

from .criteria import (
    CensusInputError,
    SensitivityReviewRequired,
    build_dropoff_ladder,
    build_sensitivity_grid,
    enforce_sensitivity_checkpoint,
    ordered_clause_metadata,
    validate_source_columns,
)


try:
    from dagster import MetadataValue, Output, asset
except Exception:  # pragma: no cover - test-only shim

    def asset(*_args: Any, **_kwargs: Any):  # type: ignore[no-redef]
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


DROP_OFF_OUTPUT_PATH = Path("data/processed/phase_iii_census_dropoff.parquet")
SENSITIVITY_OUTPUT_PATH = Path("data/processed/phase_iii_census_sensitivity.parquet")
CONTRACTS_PRIMARY_PATH = Path("data/transition/contracts_ingestion.parquet")
CONTRACTS_FALLBACK_PATH = Path("data/processed/contracts_ingestion.parquet")
DATA_CUT_ENV = "SBIR_ETL__PHASE_III_CENSUS__DATA_CUT_DATE"
FROZEN_SPEC_COMMIT = "989d9155c60e227ff2f921d3495e251a4246dda3"


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
    try:
        return pd.read_parquet(path), path
    except Exception as exc:  # pragma: no cover - defensive I/O boundary
        raise CensusInputError(f"Failed to read contract source at {path}: {exc}") from exc


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

    priors = validated_phase_ii_awards
    if priors is None:
        priors = pd.DataFrame()
    contracts, contracts_path = _load_contracts()
    data_cut = parse_census_data_cut_date()
    log = getattr(context, "log", logger) if context is not None else logger

    validate_source_columns(priors, contracts)
    pairs = build_uei_pairs(priors, contracts)
    dropoff = build_dropoff_ladder(pairs, data_cut)
    sensitivity = build_sensitivity_grid(pairs, data_cut)

    try:
        enforce_sensitivity_checkpoint(sensitivity)
    except SensitivityReviewRequired:
        log.error(
            "Phase III census sensitivity checkpoint triggered; artifacts were not "
            f"published. Full grid: {sensitivity.to_dict(orient='records')}"
        )
        raise

    DROP_OFF_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dropoff.to_parquet(DROP_OFF_OUTPUT_PATH, index=False)
    sensitivity.to_parquet(SENSITIVITY_OUTPUT_PATH, index=False)

    metadata: dict[str, Any] = {
        "dropoff_path": str(DROP_OFF_OUTPUT_PATH),
        "sensitivity_path": str(SENSITIVITY_OUTPUT_PATH),
        "contracts_path": str(contracts_path),
        "census_data_cut_date": data_cut.isoformat(),
        "frozen_spec_commit": FROZEN_SPEC_COMMIT,
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


__all__ = [
    "DATA_CUT_ENV",
    "DROP_OFF_OUTPUT_PATH",
    "FROZEN_SPEC_COMMIT",
    "SENSITIVITY_OUTPUT_PATH",
    "parse_census_data_cut_date",
    "phase_iii_census",
]

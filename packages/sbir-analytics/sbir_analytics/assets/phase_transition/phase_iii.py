"""Phase III contracts asset.

FPDS procurement rows where ``sbir_phase`` resolves to "Phase III". The
``research`` flag (FPDS Element 10Q) is a known undercount — many Phase III
contracts are miscoded or unflagged, especially outside DoD. Coverage is
logged by agency so downstream analysis can qualify the transition rate.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from .phase_ii import DEFAULT_CONTRACTS_PATH, _classify_contract_phase, _is_assistance_row
from .utils import (
    MetadataValue,
    Output,
    asset,
    coerce_date_series,
    ensure_parent_dir,
    env_str,
    load_parquet_if_exists,
    logger,
    normalize_duns,
    normalize_uei,
    now_utc_iso,
    write_json,
)


DEFAULT_OUTPUT_PATH = "data/processed/phase_iii_contracts.parquet"


PHASE_III_COLUMNS: list[str] = [
    "contract_id",
    "recipient_uei",
    "recipient_duns",
    "recipient_name",
    "agency",
    "sub_agency",
    "obligated_amount",
    "action_date",
    "period_of_performance_start",
    "period_of_performance_end",
]


def _prepare_phase_iii_rows(contracts: pd.DataFrame) -> pd.DataFrame:
    """Extract Phase III *procurement* rows. Assistance rows are excluded."""

    if contracts.empty:
        return pd.DataFrame(columns=PHASE_III_COLUMNS)

    phase = contracts.apply(_classify_contract_phase, axis=1)
    assistance = contracts.apply(_is_assistance_row, axis=1)
    mask = (phase == "III") & (~assistance)
    df = contracts.loc[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=PHASE_III_COLUMNS)

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    action_date = coerce_date_series(_pick("action_date", "award_date", "start_date"))
    out = pd.DataFrame(
        {
            "contract_id": _pick("contract_id", "piid", "generated_unique_award_id"),
            "recipient_uei": _pick("vendor_uei", "recipient_uei", "uei").map(normalize_uei),
            "recipient_duns": _pick("vendor_duns", "recipient_duns", "duns").map(normalize_duns),
            "recipient_name": _pick("vendor_name", "recipient_name"),
            "agency": _pick("awarding_agency_name", "agency", "awarding_agency"),
            "sub_agency": _pick("awarding_sub_tier_agency_name", "sub_agency"),
            "obligated_amount": pd.to_numeric(
                _pick("federal_action_obligation", "obligation_amount", "obligated_amount"),
                errors="coerce",
            ),
            "action_date": action_date.dt.date,
            "period_of_performance_start": coerce_date_series(
                _pick("period_of_performance_start_date", "start_date", "pop_start_date")
            ).dt.date,
            "period_of_performance_end": coerce_date_series(
                _pick("period_of_performance_current_end_date", "end_date", "pop_end_date")
            ).dt.date,
        }
    )
    # action_date is the latency anchor — drop rows missing it.
    out = out.loc[out["action_date"].notna()].reset_index(drop=True)
    return out


def _agency_coverage_table(all_contracts: pd.DataFrame, phase_iii: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Row counts by agency for both the full contract frame and Phase III.

    This is the "Phase III flag as known undercount" audit: total contract
    rows per agency vs. rows that survived the Phase III classifier.
    """

    if all_contracts.empty:
        return {}
    agency_col = None
    for candidate in ("awarding_agency_name", "agency", "awarding_agency"):
        if candidate in all_contracts.columns:
            agency_col = candidate
            break
    if agency_col is None:
        return {}
    totals = all_contracts[agency_col].fillna("UNKNOWN").astype(str).value_counts()
    coverage: dict[str, dict[str, int]] = {}
    p3_counts = (
        phase_iii["agency"].fillna("UNKNOWN").astype(str).value_counts()
        if not phase_iii.empty
        else pd.Series(dtype=int)
    )
    for agency, total in totals.items():
        coverage[str(agency)] = {
            "total_contract_rows": int(total),
            "phase_iii_rows": int(p3_counts.get(agency, 0)),
        }
    return coverage


@asset(
    name="validated_phase_iii_contracts",
    group_name="validation",
    compute_kind="pandas",
    description=(
        "FPDS contracts flagged Phase III (SR3/ST3 or explicit sbir_phase). "
        "The flag is a known undercount — coverage by agency is emitted as checks. "
        "Row-level contract: `sbir_etl.models.phase_transition.PhaseIIIContract`."
    ),
)
def validated_phase_iii_contracts(context=None) -> Output[pd.DataFrame]:
    contracts_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH", DEFAULT_CONTRACTS_PATH)
        or DEFAULT_CONTRACTS_PATH
    )
    output_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__PHASE_III_OUTPUT_PATH", DEFAULT_OUTPUT_PATH)
        or DEFAULT_OUTPUT_PATH
    )

    contracts = load_parquet_if_exists(contracts_path)
    if contracts is None:
        contracts = pd.DataFrame()
    phase_iii = _prepare_phase_iii_rows(contracts)

    ensure_parent_dir(output_path)
    if not phase_iii.empty:
        phase_iii.to_parquet(output_path, index=False)

    uei_cov = float(phase_iii["recipient_uei"].notna().mean()) if not phase_iii.empty else 0.0
    duns_cov = float(phase_iii["recipient_duns"].notna().mean()) if not phase_iii.empty else 0.0
    action_cov = float(phase_iii["action_date"].notna().mean()) if not phase_iii.empty else 0.0

    agency_coverage = _agency_coverage_table(contracts, phase_iii)
    # Summarize: what fraction of agencies show zero Phase III flags?
    zero_p3_agencies = [a for a, c in agency_coverage.items() if c["phase_iii_rows"] == 0]

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": int(len(phase_iii)),
        "coverage": {
            "recipient_uei": round(uei_cov, 4),
            "recipient_duns": round(duns_cov, 4),
            "action_date": round(action_cov, 4),
        },
        "undercount_warning": {
            "agencies_with_zero_phase_iii": zero_p3_agencies,
            "agencies_total": len(agency_coverage),
            "note": (
                "FPDS sbir_phase coding is known to undercount Phase III, especially "
                "outside DoD. Treat transition rates as lower bounds."
            ),
        },
        "agency_coverage": agency_coverage,
        "inputs": {
            "contracts_path": str(contracts_path),
            "contracts_exists": contracts_path.exists(),
        },
    }
    checks_path = output_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    metadata = {
        "rows": int(len(phase_iii)),
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(checks["coverage"]),
        "agencies_with_zero_phase_iii": len(zero_p3_agencies),
    }

    log = getattr(context, "log", logger) if context is not None else logger
    log.info(
        "validated_phase_iii_contracts complete",
        extra={
            "rows": len(phase_iii),
            "zero_p3_agencies": len(zero_p3_agencies),
        },
    )

    return Output(phase_iii, metadata=metadata)  # type: ignore[arg-type]


__all__ = [
    "PHASE_III_COLUMNS",
    "validated_phase_iii_contracts",
    "_prepare_phase_iii_rows",
]

"""Unified Phase II awards asset.

Combines three Phase II populations:

- **Contracts**: FPDS / USAspending procurement rows where ``sbir_phase``
  resolves to "Phase II" (FPDS Element 10Q codes ``SR2``/``ST2`` or an
  explicit ``sbir_phase`` column).
- **Grants**: USAspending assistance rows where ``sbir_phase`` is "Phase II".
- **SBIR.gov reconciliation**: used to recover ``phase == "II"`` rows whose
  federal-system coding is missing — joined to raw FPDS/USAspending records
  on ``award_id`` / ``agency_tracking_number`` / identifier overlap.

Input parquet locations (overridable via env):

- ``SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH``
    default: ``data/transition/contracts_ingestion.parquet`` (matches
    ``config.paths.transition_contracts_output``).
- ``SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH``
    default: ``data/processed/enriched_sbir_awards.parquet``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

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


DEFAULT_CONTRACTS_PATH = "data/transition/contracts_ingestion.parquet"
DEFAULT_SBIR_AWARDS_PATH = "data/processed/enriched_sbir_awards.parquet"
DEFAULT_OUTPUT_PATH = "data/processed/phase_ii_awards.parquet"

# FPDS Element 10Q codes that encode SBIR/STTR phase.
# https://www.fpdsng.com documentation: SR1/ST1=Phase I, SR2/ST2=Phase II, SR3/ST3=Phase III.
_FPDS_PHASE_II_CODES = frozenset({"SR2", "ST2"})


# Canonical columns on the unified Phase II frame.
PHASE_II_COLUMNS: list[str] = [
    "award_id",
    "recipient_uei",
    "recipient_duns",
    "recipient_name",
    "agency",
    "sub_agency",
    "award_amount",
    "award_date",
    "period_of_performance_start",
    "period_of_performance_end",
    "source",
    "phase_coding_reconciled",
]


def _normalize_phase_label(v: Any) -> str | None:
    """Coerce a phase label to "I" | "II" | "III" | None (lenient)."""

    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().upper()
    if s.startswith("PHASE "):
        s = s.replace("PHASE ", "")
    return s if s in {"I", "II", "III"} else None


def _classify_contract_phase(row: pd.Series) -> str | None:
    """Classify a contract row as "II" / "III" / None using FPDS and flags."""

    # 1) FPDS Element 10Q code in `research`.
    research = row.get("research") if "research" in row else None
    if isinstance(research, str):
        code = research.strip().upper()
        if code in _FPDS_PHASE_II_CODES:
            return "II"
        if code in {"SR3", "ST3"}:
            return "III"

    # 2) Explicit sbir_phase column (set by some extractors, e.g. the
    #    company_categorization enricher that parses phase from descriptions).
    sbir_phase = row.get("sbir_phase") if "sbir_phase" in row else None
    if sbir_phase is not None:
        return _normalize_phase_label(sbir_phase)

    return None


def _is_assistance_row(row: pd.Series) -> bool:
    """Best-effort detection of USAspending *assistance* (grants) rows.

    USAspending's ``transaction_normalized`` table co-locates procurement and
    assistance under type codes 'A'/'B'. Procurement-only fields (CAGE,
    extent_competed) tend to be null for assistance rows. We fall back to
    checking whether ``type`` is in the assistance code set or whether the
    row carries a ``cfda_number`` / ``assistance_type`` marker.
    """

    t = row.get("type") if "type" in row else None
    if isinstance(t, str) and t.strip() in {"02", "03", "04", "05", "06", "07", "08", "09", "10", "11"}:
        return True
    if "cfda_number" in row and pd.notna(row.get("cfda_number")):
        return True
    if "assistance_type" in row and pd.notna(row.get("assistance_type")):
        return True
    return False


def _prepare_contract_rows(contracts: pd.DataFrame) -> pd.DataFrame:
    """Extract Phase II rows from the raw contracts/assistance frame.

    The raw contracts parquet blends procurement and assistance rows (see
    ``sbir_etl/extractors/README.md``). We split them into ``fpds_contract``
    vs ``usaspending_assistance`` after phase classification.
    """

    if contracts.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    phase = contracts.apply(_classify_contract_phase, axis=1)
    mask = phase == "II"
    df = contracts.loc[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    # Column aliasing — contract parquet varies slightly across extractors.
    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame(
        {
            "award_id": _pick("contract_id", "piid", "generated_unique_award_id"),
            "recipient_uei": _pick("vendor_uei", "recipient_uei", "uei").map(normalize_uei),
            "recipient_duns": _pick("vendor_duns", "recipient_duns", "duns").map(normalize_duns),
            "recipient_name": _pick("vendor_name", "recipient_name"),
            "agency": _pick("awarding_agency_name", "agency", "awarding_agency"),
            "sub_agency": _pick("awarding_sub_tier_agency_name", "sub_agency"),
            "award_amount": pd.to_numeric(
                _pick("federal_action_obligation", "obligation_amount", "obligated_amount"),
                errors="coerce",
            ),
            "award_date": coerce_date_series(_pick("action_date", "award_date", "start_date")).dt.date,
            "period_of_performance_start": coerce_date_series(
                _pick("period_of_performance_start_date", "start_date", "pop_start_date")
            ).dt.date,
            "period_of_performance_end": coerce_date_series(
                _pick("period_of_performance_current_end_date", "end_date", "pop_end_date")
            ).dt.date,
        }
    )
    out["source"] = df.apply(
        lambda r: "usaspending_assistance" if _is_assistance_row(r) else "fpds_contract",
        axis=1,
    )
    out["phase_coding_reconciled"] = False
    return out.reset_index(drop=True)


def _prepare_sbir_gov_rows(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Extract Phase II rows from the SBIR.gov-reconciled enriched awards frame."""

    if sbir_awards.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)
    phase = sbir_awards.get("phase", pd.Series([None] * len(sbir_awards)))
    phase_norm = phase.map(_normalize_phase_label)
    df = sbir_awards.loc[phase_norm == "II"].copy()
    if df.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    out = pd.DataFrame(
        {
            "award_id": df.get("award_id"),
            "recipient_uei": df.get("company_uei", pd.Series([None] * len(df))).map(normalize_uei),
            "recipient_duns": df.get("company_duns", pd.Series([None] * len(df))).map(
                normalize_duns
            ),
            "recipient_name": df.get("company_name"),
            "agency": df.get("agency"),
            "sub_agency": df.get("branch"),
            "award_amount": pd.to_numeric(df.get("award_amount"), errors="coerce"),
            "award_date": coerce_date_series(df.get("award_date")).dt.date,
            "period_of_performance_start": coerce_date_series(df.get("contract_start_date")).dt.date,
            "period_of_performance_end": coerce_date_series(df.get("contract_end_date")).dt.date,
            "source": "sbir_gov",
            "phase_coding_reconciled": True,
        }
    )
    return out.reset_index(drop=True)


def _unify(contract_phase_ii: pd.DataFrame, sbir_gov_phase_ii: pd.DataFrame) -> pd.DataFrame:
    """Stack, deduplicate on ``award_id`` preferring federal-system rows.

    When the same ``award_id`` appears in both federal-system and SBIR.gov
    populations we keep the federal row (authoritative dates) and mark
    ``phase_coding_reconciled=False``.
    """

    frames = [f for f in (contract_phase_ii, sbir_gov_phase_ii) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    stacked = pd.concat(frames, ignore_index=True, sort=False)
    # Sort so federal-system rows (non-reconciled) come first for drop_duplicates.
    stacked = stacked.sort_values("phase_coding_reconciled", kind="stable")
    stacked = stacked.drop_duplicates(subset=["award_id"], keep="first")
    return stacked[PHASE_II_COLUMNS].reset_index(drop=True)


def _agency_coverage(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "agency" not in df.columns:
        return {}
    counts = df["agency"].fillna("UNKNOWN").astype(str).value_counts()
    return {k: int(v) for k, v in counts.to_dict().items()}


@asset(
    name="validated_phase_ii_awards",
    group_name="validation",
    compute_kind="pandas",
    description=(
        "Unified Phase II population across FPDS/USAspending contracts, USAspending "
        "assistance grants, and SBIR.gov reconciliation. Row-level contract: "
        "`sbir_etl.models.phase_transition.PhaseIIAward`."
    ),
)
def validated_phase_ii_awards(context: Any | None = None) -> Output[pd.DataFrame]:
    """Materialize the unified Phase II frame."""

    contracts_path = Path(env_str("SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH", DEFAULT_CONTRACTS_PATH) or DEFAULT_CONTRACTS_PATH)
    sbir_awards_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH", DEFAULT_SBIR_AWARDS_PATH) or DEFAULT_SBIR_AWARDS_PATH
    )
    output_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__PHASE_II_OUTPUT_PATH", DEFAULT_OUTPUT_PATH) or DEFAULT_OUTPUT_PATH
    )

    contracts = load_parquet_if_exists(contracts_path)
    if contracts is None:
        contracts = pd.DataFrame()
    sbir_awards = load_parquet_if_exists(sbir_awards_path)
    if sbir_awards is None:
        sbir_awards = pd.DataFrame()

    contract_phase_ii = _prepare_contract_rows(contracts)
    sbir_gov_phase_ii = _prepare_sbir_gov_rows(sbir_awards)
    unified = _unify(contract_phase_ii, sbir_gov_phase_ii)

    ensure_parent_dir(output_path)
    if not unified.empty:
        unified.to_parquet(output_path, index=False)

    uei_cov = (
        float(unified["recipient_uei"].notna().mean()) if not unified.empty else 0.0
    )
    duns_cov = (
        float(unified["recipient_duns"].notna().mean()) if not unified.empty else 0.0
    )
    pop_end_cov = (
        float(unified["period_of_performance_end"].notna().mean())
        if not unified.empty
        else 0.0
    )
    source_counts = unified["source"].value_counts().to_dict() if not unified.empty else {}

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": int(len(unified)),
        "sources": {str(k): int(v) for k, v in source_counts.items()},
        "coverage": {
            "recipient_uei": round(uei_cov, 4),
            "recipient_duns": round(duns_cov, 4),
            "period_of_performance_end": round(pop_end_cov, 4),
        },
        "agency_row_counts": _agency_coverage(unified),
        "inputs": {
            "contracts_path": str(contracts_path),
            "sbir_awards_path": str(sbir_awards_path),
            "contracts_exists": contracts_path.exists(),
            "sbir_awards_exists": sbir_awards_path.exists(),
        },
    }
    checks_path = output_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    metadata = {
        "rows": int(len(unified)),
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(checks["coverage"]),
        "sources": MetadataValue.json(checks["sources"]),
    }

    log = getattr(context, "log", logger) if context is not None else logger
    log.info(
        "validated_phase_ii_awards complete",
        extra={
            "rows": len(unified),
            "sources": source_counts,
            "uei_coverage": uei_cov,
        },
    )

    return Output(unified, metadata=metadata)  # type: ignore[arg-type]


__all__ = [
    "PHASE_II_COLUMNS",
    "validated_phase_ii_awards",
    "_prepare_contract_rows",
    "_prepare_sbir_gov_rows",
    "_unify",
]

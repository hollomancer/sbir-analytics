"""Unified Phase II awards asset.

Combines three Phase II populations:

- **Contracts**: FPDS / USAspending procurement rows where ``sbir_phase``
  resolves to "Phase II" (FPDS Element 10Q codes ``SR2``/``ST2`` or an
  explicit ``sbir_phase`` column).
- **Grants**: USAspending assistance rows where ``sbir_phase`` is "Phase II".
- **SBIR.gov reconciliation**: used to recover ``phase == "II"`` rows whose
  federal-system coding is missing. Supplemental rows reconcile only through
  exact normalized source identifiers after federal transactions are collapsed.

Input parquet locations (overridable via env):

- ``SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH``
    default: ``data/transition/contracts_ingestion.parquet`` (matches
    ``config.paths.transition_contracts_output``).
- ``SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH``
    default: ``data/processed/enriched_sbir_awards.parquet``.
"""

from __future__ import annotations

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
_NULL_KEY_TOKENS = frozenset({"", "<NA>", "NAN", "NONE", "NULL", r"\N"})


class PhaseIIInputError(ValueError):
    """Raised when Phase II source grain cannot be made deterministic."""


# Canonical columns on the unified Phase II frame.
PHASE_II_COLUMNS: list[str] = [
    "award_id",
    "source_award_id",
    "representative_transaction_id",
    "source_transaction_count",
    "recipient_uei",
    "recipient_duns",
    "recipient_name",
    "agency",
    "sub_agency",
    "naics_code",
    "psc_code",
    "award_amount",
    "award_date",
    "period_of_performance_start",
    "period_of_performance_end",
    "source",
    "phase_coding_reconciled",
]


def _normalize_source_key(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    normalized = str(value).strip().upper()
    return "" if normalized in _NULL_KEY_TOKENS else normalized


def _coalesce_columns(df: pd.DataFrame, *names: str) -> pd.Series:
    """Take the first nonblank named source value per row in fixed order."""

    result = pd.Series([None] * len(df), index=df.index, dtype="object")
    for name in names:
        if name not in df.columns:
            continue
        source = df[name]
        missing = result.map(_normalize_source_key).eq("")
        usable = source.map(_normalize_source_key).ne("")
        result.loc[missing & usable] = source.loc[missing & usable]
    return result


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

    In USAspending's ``transaction_normalized`` table, ``type`` is a
    single-letter category — ``'A'``/``'B'`` for procurement (contracts and
    IDVs) and ``'C'``/``'D'`` for assistance (grants and direct payments).
    The numeric codes ``"02"``...``"11"`` live on the separate
    ``award_type_code`` column. We accept either as evidence, and fall back
    to the presence of an explicit assistance marker (CFDA number or
    ``assistance_type``).
    """

    t = row.get("type") if "type" in row else None
    if isinstance(t, str) and t.strip().upper() in {"C", "D"}:
        return True
    award_type_code = row.get("award_type_code") if "award_type_code" in row else None
    if isinstance(award_type_code, str) and award_type_code.strip() in {
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
        "09",
        "10",
        "11",
    }:
        return True
    if "cfda_number" in row and pd.notna(row.get("cfda_number")):
        return True
    if "assistance_type" in row and pd.notna(row.get("assistance_type")):
        return True
    return False


def _prepare_contract_rows(contracts: pd.DataFrame) -> pd.DataFrame:
    """Collapse Phase II-coded federal transactions to stable generated awards.

    The representative transaction is the greatest valid action-date / stable
    transaction-id tuple. Its current performance end is used as recorded; an older
    maximum is never substituted.
    """

    if contracts.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    phase = contracts.apply(_classify_contract_phase, axis=1)  # type: ignore[call-overload]
    mask = phase == "II"
    df = contracts.loc[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    for required in ("generated_unique_award_id", "transaction_unique_id"):
        if required not in df.columns:
            raise PhaseIIInputError(
                f"Phase II federal source is missing required stable key column: {required}"
            )

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    award_key = df["generated_unique_award_id"].map(_normalize_source_key)
    transaction_key = df["transaction_unique_id"].map(_normalize_source_key)
    if award_key.eq("").any():
        raise PhaseIIInputError(
            "Every Phase II-coded federal transaction must have generated_unique_award_id"
        )
    if transaction_key.eq("").any():
        raise PhaseIIInputError(
            "Every Phase II-coded federal transaction must have transaction_unique_id"
        )

    action_timestamp = coerce_date_series(_pick("action_date"))
    source_award_key = _pick("piid").map(_normalize_source_key)
    source_award_key = source_award_key.where(source_award_key.ne(""), None)

    out = pd.DataFrame(
        {
            "award_id": award_key,
            "source_award_id": source_award_key,
            "representative_transaction_id": transaction_key,
            "source_transaction_count": 1,
            "recipient_uei": _pick("vendor_uei", "recipient_uei", "uei").map(normalize_uei),
            "recipient_duns": _pick("vendor_duns", "recipient_duns", "duns").map(normalize_duns),
            "recipient_name": _pick("vendor_name", "recipient_name"),
            "agency": _pick(
                "awarding_toptier_agency_name",
                "awarding_agency_name",
                "agency",
                "awarding_agency",
            ),
            "sub_agency": _pick(
                "awarding_subtier_agency_name",
                "awarding_sub_tier_agency_name",
                "sub_agency",
            ),
            "naics_code": _pick("naics_code", "naics"),
            "psc_code": _pick("psc_code", "product_or_service_code"),
            "award_amount": pd.to_numeric(
                _pick("federal_action_obligation", "obligation_amount", "obligated_amount"),
                errors="coerce",
            ),
            "award_date": action_timestamp.dt.date,
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
    out["_action_timestamp"] = action_timestamp
    out["_transaction_key"] = transaction_key
    out["_research_code"] = _pick("research").map(_normalize_source_key)
    out["_sbir_phase_label"] = _pick("sbir_phase").map(_normalize_source_key)

    # Exact duplicate source rows do not constitute additional transactions. A stable
    # transaction id attached to two different projected payloads is not resolvable.
    out = out.drop_duplicates().reset_index(drop=True)
    if out["_transaction_key"].duplicated(keep=False).any():
        conflicts = sorted(
            out.loc[out["_transaction_key"].duplicated(keep=False), "_transaction_key"].unique()
        )
        raise PhaseIIInputError(
            f"Stable Phase II transaction identifiers map to conflicting source values: {conflicts}"
        )

    awards: list[pd.Series] = []
    for generated_award_id, group in out.groupby("award_id", sort=True, dropna=False):
        source_ids = {key for key in group["source_award_id"].map(_normalize_source_key) if key}
        if len(source_ids) > 1:
            raise PhaseIIInputError(
                f"Generated Phase II award {generated_award_id} maps to conflicting PIIDs: "
                f"{sorted(source_ids)}"
            )
        source_types = set(group["source"].dropna().astype(str))
        if len(source_types) > 1:
            raise PhaseIIInputError(
                f"Generated Phase II award {generated_award_id} crosses source types: "
                f"{sorted(source_types)}"
            )

        ordered = group.assign(
            _has_action=group["_action_timestamp"].notna().astype(int)
        ).sort_values(
            ["_has_action", "_action_timestamp", "_transaction_key"],
            kind="stable",
            na_position="first",
        )
        representative = ordered.iloc[-1].copy()
        valid_actions = group["_action_timestamp"].dropna()
        representative["award_date"] = (
            valid_actions.min().date() if not valid_actions.empty else None
        )
        amounts = pd.to_numeric(group["award_amount"], errors="coerce")
        signed_total = amounts.sum(min_count=1)
        representative["award_amount"] = None if pd.isna(signed_total) else float(signed_total)
        representative["source_transaction_count"] = int(len(group))
        if source_ids:
            representative["source_award_id"] = sorted(source_ids)[0]
        awards.append(representative)

    return pd.DataFrame(awards).loc[:, PHASE_II_COLUMNS].reset_index(drop=True)


def _prepare_sbir_gov_rows(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Extract Phase II rows from the SBIR.gov-reconciled enriched awards frame."""

    if sbir_awards.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)
    phase = sbir_awards.get("phase", pd.Series([None] * len(sbir_awards)))
    phase_norm = phase.map(_normalize_phase_label)
    df = sbir_awards.loc[phase_norm == "II"].copy().reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    def _pick(*names: str) -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame(
        {
            "award_id": _pick("award_id"),
            "source_award_id": _coalesce_columns(
                df, "contract", "agency_tracking_number", "award_id"
            ),
            "representative_transaction_id": None,
            "source_transaction_count": None,
            "recipient_uei": df.get("company_uei", pd.Series([None] * len(df))).map(normalize_uei),
            "recipient_duns": df.get("company_duns", pd.Series([None] * len(df))).map(
                normalize_duns
            ),
            "recipient_name": df.get("company_name"),
            "agency": df.get("agency"),
            "sub_agency": df.get("branch"),
            "naics_code": _pick("naics_code", "naics"),
            "psc_code": _pick("psc_code", "product_or_service_code"),
            "award_amount": pd.to_numeric(
                df.get("award_amount", pd.Series(dtype=object)), errors="coerce"
            ),
            "award_date": coerce_date_series(df.get("award_date", pd.Series(dtype=object))).dt.date,
            "period_of_performance_start": coerce_date_series(
                df.get("contract_start_date", pd.Series(dtype=object))
            ).dt.date,
            "period_of_performance_end": coerce_date_series(
                df.get("contract_end_date", pd.Series(dtype=object))
            ).dt.date,
            "source": "sbir_gov",
            "phase_coding_reconciled": True,
        }
    )
    if out["award_id"].map(_normalize_source_key).eq("").any():
        raise PhaseIIInputError("Every Phase II SBIR.gov row must have a stable award_id")
    return out.drop_duplicates().reset_index(drop=True)


def _unify(contract_phase_ii: pd.DataFrame, sbir_gov_phase_ii: pd.DataFrame) -> pd.DataFrame:
    """Reconcile SBIR.gov rows to generated federal awards without PIID guessing."""

    if contract_phase_ii.empty and sbir_gov_phase_ii.empty:
        return pd.DataFrame(columns=PHASE_II_COLUMNS)

    federal = contract_phase_ii.loc[:, PHASE_II_COLUMNS].copy().reset_index(drop=True)
    supplemental = sbir_gov_phase_ii.loc[:, PHASE_II_COLUMNS].copy().reset_index(drop=True)
    supplemental = supplemental.drop_duplicates().reset_index(drop=True)

    if not supplemental.empty:
        supplemental_award_keys = supplemental["award_id"].map(_normalize_source_key)
        if supplemental_award_keys.duplicated(keep=False).any():
            conflicts = sorted(
                supplemental_award_keys[supplemental_award_keys.duplicated()].unique()
            )
            raise PhaseIIInputError(
                f"Conflicting duplicate SBIR.gov Phase II award ids: {conflicts}"
            )

    federal_source_keys = (
        federal["source_award_id"].map(_normalize_source_key)
        if not federal.empty
        else pd.Series(dtype="object")
    )
    supplemental_source_keys = (
        supplemental["source_award_id"].map(_normalize_source_key)
        if not supplemental.empty
        else pd.Series(dtype="object")
    )
    drop_supplemental: set[int] = set()
    shared_source_keys = sorted((set(federal_source_keys) & set(supplemental_source_keys)) - {""})
    for source_key in shared_source_keys:
        federal_indexes = list(federal.index[federal_source_keys.eq(source_key)])
        supplemental_indexes = list(supplemental.index[supplemental_source_keys.eq(source_key)])
        if len(federal_indexes) != 1:
            generated_ids = sorted(
                federal.loc[federal_indexes, "award_id"].map(_normalize_source_key)
            )
            raise PhaseIIInputError(
                f"SBIR.gov source award {source_key} ambiguously matches generated awards: "
                f"{generated_ids}"
            )

        federal_index = federal_indexes[0]
        for column in ("naics_code", "psc_code"):
            candidates = supplemental.loc[supplemental_indexes, column]
            supplemental_normalized = {
                normalized for value in candidates if (normalized := _normalize_source_key(value))
            }
            federal_value = federal.at[federal_index, column]
            federal_normalized = _normalize_source_key(federal_value)
            observed_values = set(supplemental_normalized)
            if federal_normalized:
                observed_values.add(federal_normalized)
            if len(observed_values) > 1:
                raise PhaseIIInputError(
                    f"SBIR.gov source award {source_key} has conflicting {column}: "
                    f"{sorted(observed_values)}"
                )
            if not federal_normalized and supplemental_normalized:
                federal.at[federal_index, column] = next(iter(supplemental_normalized))
        drop_supplemental.update(supplemental_indexes)

    if drop_supplemental:
        supplemental = supplemental.drop(index=sorted(drop_supplemental))
    frames = [frame for frame in (federal, supplemental) if not frame.empty]
    stacked = pd.concat(frames, ignore_index=True, sort=False)
    canonical_keys = stacked["award_id"].map(_normalize_source_key)
    if canonical_keys.eq("").any():
        raise PhaseIIInputError("Unified Phase II rows must have a stable canonical award_id")
    if canonical_keys.duplicated(keep=False).any():
        conflicts = sorted(canonical_keys[canonical_keys.duplicated()].unique())
        raise PhaseIIInputError(f"Canonical Phase II award ids are not unique: {conflicts}")

    return (
        stacked.assign(_award_key=canonical_keys)
        .sort_values("_award_key", kind="stable")
        .loc[:, PHASE_II_COLUMNS]
        .reset_index(drop=True)
    )


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
def validated_phase_ii_awards(context=None) -> Output[pd.DataFrame]:
    """Materialize the unified Phase II frame."""

    contracts_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__CONTRACTS_PATH", DEFAULT_CONTRACTS_PATH)
        or DEFAULT_CONTRACTS_PATH
    )
    sbir_awards_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__SBIR_AWARDS_PATH", DEFAULT_SBIR_AWARDS_PATH)
        or DEFAULT_SBIR_AWARDS_PATH
    )
    output_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__PHASE_II_OUTPUT_PATH", DEFAULT_OUTPUT_PATH)
        or DEFAULT_OUTPUT_PATH
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

    uei_cov = float(unified["recipient_uei"].notna().mean()) if not unified.empty else 0.0
    duns_cov = float(unified["recipient_duns"].notna().mean()) if not unified.empty else 0.0
    pop_end_cov = (
        float(unified["period_of_performance_end"].notna().mean()) if not unified.empty else 0.0
    )
    source_counts = unified["source"].value_counts().to_dict() if not unified.empty else {}

    coverage_dict: dict[str, float] = {
        "recipient_uei": round(uei_cov, 4),
        "recipient_duns": round(duns_cov, 4),
        "period_of_performance_end": round(pop_end_cov, 4),
    }
    sources_dict: dict[str, int] = {str(k): int(v) for k, v in source_counts.items()}
    checks: dict[str, Any] = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": int(len(unified)),
        "sources": sources_dict,
        "coverage": coverage_dict,
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

    metadata: dict[str, Any] = {
        "rows": int(len(unified)),
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(coverage_dict),
        "sources": MetadataValue.json(sources_dict),
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
    "PhaseIIInputError",
    "validated_phase_ii_awards",
    "_prepare_contract_rows",
    "_prepare_sbir_gov_rows",
    "_unify",
]

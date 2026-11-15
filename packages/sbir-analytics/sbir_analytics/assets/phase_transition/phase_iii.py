"""Phase III contracts asset.

FPDS procurement rows where ``sbir_phase`` resolves to "Phase III". The
``research`` flag (FPDS Element 10Q) is a known undercount — many Phase III
contracts are miscoded or unflagged, especially outside DoD. Coverage is
logged by agency so downstream analysis can qualify the transition rate.

The ``research`` flag is also the only field here that states the *program*:
``SR3`` means SBIR and ``ST3`` means STTR. ``_classify_contract_phase`` maps
both to the phase ``"III"``, which is all it is asked for, so this asset reads
the program off the same field into ``program`` / ``program_evidence`` before
the distinction is gone. Every other identification path establishes the phase
and leaves ``program`` null; the null count and the resulting program coverage
are emitted in the checks file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.models.sbir_program import program_from_fpds_research_code

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
    nullable_str_series,
    write_json,
)


DEFAULT_OUTPUT_PATH = "data/processed/phase_iii_contracts.parquet"

_IDV_AWARD_TYPES = frozenset({"BPA", "BOA", "IDIQ"})
# FPDS Element 10Q codes that mean "SBIR/STTR Phase III". The pair is the only
# place in this asset where the program (SR = SBIR, ST = STTR) is stated.
_PHASE_III_PROGRAM_CODES = frozenset({"SR3", "ST3"})
_PHASE_III_PARENT_DESCRIPTION = re.compile(
    r"(?:\b(?:SBIR|STTR)\b|\bSMALL BUSINESS (?:INNOVATION|TECHNOLOGY TRANSFER) RESEARCH\b)"
    r".{0,120}\bPHASE[\s-]*(?:III|3)\b|"
    r"\bPHASE[\s-]*(?:III|3)\b.{0,120}"
    r"(?:\b(?:SBIR|STTR)\b|\bSMALL BUSINESS (?:INNOVATION|TECHNOLOGY TRANSFER) RESEARCH\b)",
    re.IGNORECASE,
)


PHASE_III_COLUMNS: list[str] = [
    "contract_id",
    "parent_contract_id",
    "phase_iii_evidence",
    "phase_iii_inherited",
    "program",
    "program_evidence",
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


def _normalized_identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return normalized or None


def _row_value(row: pd.Series, *names: str) -> str | None:
    for name in names:
        value = row.get(name) if name in row else None
        if isinstance(value, str) and value.strip():
            return value
    return None


def _is_idv_row(row: pd.Series) -> bool:
    award_type = _normalized_identifier(_row_value(row, "contract_award_type", "award_type"))
    return bool(award_type and (award_type.startswith("IDV") or award_type in _IDV_AWARD_TYPES))


def _parent_declares_phase_iii(row: pd.Series) -> bool:
    if _classify_contract_phase(row) == "III":
        return True
    description = _row_value(row, "description", "transaction_description")
    return bool(description and _PHASE_III_PARENT_DESCRIPTION.search(str(description)))


def _direct_evidence(row: pd.Series) -> str:
    research = _normalized_identifier(_row_value(row, "research"))
    if research in _PHASE_III_PROGRAM_CODES:
        return "direct_10q"
    if _row_value(row, "sbir_phase") is not None:
        return "direct_sbir_phase"
    return "direct_research"


def _direct_program(row: pd.Series) -> tuple[str | None, str | None]:
    """Return ``(program, program_evidence)`` for a directly identified row.

    The row's own FPDS Element 10Q Phase III code is the only thing that
    states the program: ``SR3`` -> SBIR, ``ST3`` -> STTR. This is the
    distinction that ``_classify_contract_phase`` collapses when it maps both
    codes to the phase ``"III"`` — the phase is all it is asked for, so the
    program has to be read from the same field separately rather than
    recovered downstream, where the code is gone.

    Every other identification path returns ``(None, None)``: an explicit
    ``sbir_phase`` value, a descriptive phase string, and a declared parent IDV
    each establish the phase and state nothing about the program. ``None`` is
    carried as unknown and is never filled from a correlate.
    """

    research = _normalized_identifier(_row_value(row, "research"))
    if research not in _PHASE_III_PROGRAM_CODES:
        return None, None
    program = program_from_fpds_research_code(research)
    if program is None:
        return None, None
    return program, "direct_10q"


def _phase_iii_parent_index(contracts: pd.DataFrame) -> tuple[dict[str, str], set[str]]:
    """Resolve unambiguous IDV identifiers and explicitly declared Phase III parents.

    Multiple transaction rows for one IDV share a canonical key. A PIID reused by
    different IDVs is deliberately omitted from the lookup, so bare-PIID collisions
    cannot cause Phase III inheritance.
    """

    identifiers_to_parents: dict[str, set[str]] = {}
    declared_parents: set[str] = set()

    for _, row in contracts.iterrows():
        if not _is_idv_row(row):
            continue

        generated_id = _normalized_identifier(
            _row_value(row, "generated_unique_award_id", "generated_internal_id")
        )
        piid = _normalized_identifier(_row_value(row, "piid", "contract_id"))
        agency = _normalized_identifier(
            _row_value(row, "awarding_agency_name", "agency", "awarding_agency")
        )
        canonical = generated_id or (f"{agency or 'UNKNOWN'}::{piid}" if piid else None)
        if canonical is None:
            continue

        for identifier in {generated_id, piid}:
            if identifier:
                identifiers_to_parents.setdefault(identifier, set()).add(canonical)
        if _parent_declares_phase_iii(row):
            declared_parents.add(canonical)

    unique_index = {
        identifier: next(iter(parents))
        for identifier, parents in identifiers_to_parents.items()
        if len(parents) == 1
    }
    return unique_index, declared_parents


def _prepare_phase_iii_rows(contracts: pd.DataFrame) -> pd.DataFrame:
    """Extract Phase III procurement rows, including declared-IDV descendants.

    Parent inheritance is fail-closed: only a task order linked to an unambiguous
    IDV that explicitly declares SBIR/STTR Phase III is included. General-purpose
    vehicles with an isolated Phase III order do not confer status on siblings.
    """

    if contracts.empty:
        return pd.DataFrame(columns=PHASE_III_COLUMNS)

    phase = contracts.apply(_classify_contract_phase, axis=1)  # type: ignore[call-overload]
    assistance = contracts.apply(_is_assistance_row, axis=1)  # type: ignore[call-overload]
    parent_index, declared_parents = _phase_iii_parent_index(contracts)
    parent_references = contracts.apply(
        lambda row: _normalized_identifier(
            _row_value(row, "parent_contract_id", "parent_award_id", "referenced_idv_piid")
        ),
        axis=1,
    ).astype(object)  # type: ignore[call-overload]
    # `apply` infers a string dtype and rewrites the missing values to NaN, which is
    # truthy. Restore None so a row without a parent reads as absent, like the other
    # optional string columns.
    parent_references = parent_references.where(parent_references.notna(), None)
    inherited = parent_references.map(
        lambda identifier: bool(
            identifier
            and parent_index.get(identifier)
            and parent_index[identifier] in declared_parents
        )
    )
    direct = phase == "III"
    mask = (direct | inherited) & (~assistance)
    df = contracts.loc[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=PHASE_III_COLUMNS)

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    selected_direct = direct.loc[mask]
    selected_inherited = inherited.loc[mask] & (~selected_direct)
    selected_parent_references = parent_references.loc[mask]
    action_date = coerce_date_series(_pick("action_date", "award_date", "start_date"))

    # One pass over the selected rows for both provenance axes. The phase
    # evidence and the program evidence are independent: a row can be
    # confidently Phase III with no program on record.
    phase_evidence: list[str] = []
    programs: list[str | None] = []
    program_evidence: list[str | None] = []
    for (_, row), is_direct in zip(df.iterrows(), selected_direct, strict=True):
        if not is_direct:
            # Inherited from a declared parent IDV. The parent confers the
            # phase and not the program — see `PhaseIIIContract` for why.
            phase_evidence.append("parent_declared")
            programs.append(None)
            program_evidence.append(None)
            continue
        phase_evidence.append(_direct_evidence(row))
        row_program, row_program_evidence = _direct_program(row)
        programs.append(row_program)
        program_evidence.append(row_program_evidence)

    out = pd.DataFrame(
        {
            "contract_id": _pick("contract_id", "piid", "generated_unique_award_id"),
            "parent_contract_id": selected_parent_references,
            "phase_iii_evidence": phase_evidence,
            "phase_iii_inherited": selected_inherited.astype(bool),
            "program": nullable_str_series(programs, df.index),
            "program_evidence": nullable_str_series(program_evidence, df.index),
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


def _agency_coverage_table(
    all_contracts: pd.DataFrame, phase_iii: pd.DataFrame
) -> dict[str, dict[str, int]]:
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


def _program_coverage_report(phase_iii: pd.DataFrame) -> dict[str, Any]:
    """Report program counts and the unknown-program stratum side by side.

    The unknown count is emitted as its own number rather than folded into a
    program, because a consumer filtering the mart to STTR has to know how much
    of the population it could not see. ``program_coverage`` is the share of
    Phase III rows whose program is on record; an STTR rate computed off this
    table is a rate over that share, not over the Phase III population.
    """

    if phase_iii.empty:
        return {
            "rows_by_program": {},
            "unknown_program_rows": 0,
            "program_coverage": 0.0,
            "unknown_program_by_phase_iii_evidence": {},
        }
    program = phase_iii["program"]
    known = program.notna()
    counts = program.loc[known].astype(str).value_counts().astype(int).to_dict()
    unknown_by_evidence = (
        phase_iii.loc[~known, "phase_iii_evidence"]
        .fillna("UNKNOWN")
        .astype(str)
        .value_counts()
        .astype(int)
        .to_dict()
    )
    return {
        "rows_by_program": {str(k): int(v) for k, v in counts.items()},
        "unknown_program_rows": int((~known).sum()),
        "program_coverage": round(float(known.mean()), 4),
        "unknown_program_by_phase_iii_evidence": unknown_by_evidence,
        "note": (
            "Program is recorded only from the row's own FPDS Element 10Q code "
            "(SR3=SBIR, ST3=STTR). Rows identified by any other path carry no "
            "program and are excluded from both numerator and denominator of a "
            "program-specific measure — never imputed, never redistributed."
        ),
    }


@asset(
    name="validated_phase_iii_contracts",
    group_name="validation",
    compute_kind="pandas",
    description=(
        "FPDS contracts flagged Phase III (SR3/ST3 or explicit sbir_phase), plus task "
        "orders under explicitly declared Phase III IDVs. "
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
    # Write unconditionally, including when empty. Skipping the write left the
    # previous parquet on disk while checks.json below is overwritten with
    # total_rows: 0, so a stale table read as a fresh zero-row result.
    phase_iii.to_parquet(output_path, index=False)

    uei_cov = float(phase_iii["recipient_uei"].notna().mean()) if not phase_iii.empty else 0.0
    duns_cov = float(phase_iii["recipient_duns"].notna().mean()) if not phase_iii.empty else 0.0
    action_cov = float(phase_iii["action_date"].notna().mean()) if not phase_iii.empty else 0.0

    agency_coverage = _agency_coverage_table(contracts, phase_iii)
    # Summarize: what fraction of agencies show zero Phase III flags?
    zero_p3_agencies = [a for a, c in agency_coverage.items() if c["phase_iii_rows"] == 0]
    evidence_counts = (
        phase_iii["phase_iii_evidence"].value_counts().astype(int).to_dict()
        if not phase_iii.empty
        else {}
    )
    inherited_rows = int(phase_iii["phase_iii_inherited"].sum()) if not phase_iii.empty else 0
    program_report = _program_coverage_report(phase_iii)

    coverage_dict: dict[str, float] = {
        "recipient_uei": round(uei_cov, 4),
        "recipient_duns": round(duns_cov, 4),
        "action_date": round(action_cov, 4),
    }
    checks: dict[str, Any] = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_rows": int(len(phase_iii)),
        "inherited_rows": inherited_rows,
        "phase_iii_evidence": evidence_counts,
        "program": program_report,
        "coverage": coverage_dict,
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

    metadata: dict[str, Any] = {
        "rows": int(len(phase_iii)),
        "inherited_rows": inherited_rows,
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "coverage": MetadataValue.json(coverage_dict),
        "phase_iii_evidence": MetadataValue.json(evidence_counts),
        "program": MetadataValue.json(program_report),
        "program_coverage": program_report["program_coverage"],
        "unknown_program_rows": program_report["unknown_program_rows"],
        "agencies_with_zero_phase_iii": len(zero_p3_agencies),
    }

    log = getattr(context, "log", logger) if context is not None else logger
    log.info(
        "validated_phase_iii_contracts complete",
        extra={
            "rows": len(phase_iii),
            "inherited_rows": inherited_rows,
            "zero_p3_agencies": len(zero_p3_agencies),
        },
    )

    return Output(phase_iii, metadata=metadata)  # type: ignore[arg-type]


__all__ = [
    "PHASE_III_COLUMNS",
    "validated_phase_iii_contracts",
    "_direct_program",
    "_prepare_phase_iii_rows",
]

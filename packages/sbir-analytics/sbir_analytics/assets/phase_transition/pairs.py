"""Phase II <-> Phase III pairing and survival frames.

``transformed_phase_ii_iii_pairs``
    All valid (Phase II, Phase III) candidate pairs for the same firm.
    Primary join key is ``recipient_uei``; when either side lacks UEI we fall
    back to ``recipient_duns`` (with an ``identifier_basis`` column recording
    which identifier resolved the join). Negative latencies are preserved.

``transformed_phase_transition_survival``
    One row per Phase II award with an event indicator and time-to-event-or-
    censor at the configured data-cut date. For observed events we use the
    earliest Phase III action_date per Phase II.

Both assets depend on the upstream ``validated_phase_ii_awards`` and
``validated_phase_iii_contracts`` frames (passed through as Dagster inputs).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import (
    MetadataValue,
    Output,
    asset,
    ensure_parent_dir,
    env_str,
    logger,
    now_utc_iso,
    parse_data_cut_date,
    write_json,
)


DEFAULT_PAIRS_OUTPUT = "data/processed/phase_ii_iii_pairs.parquet"
DEFAULT_SURVIVAL_OUTPUT = "data/processed/phase_transition_survival.parquet"


PAIR_COLUMNS: list[str] = [
    "recipient_uei",
    "recipient_duns",
    "identifier_basis",
    "phase_ii_award_id",
    "phase_ii_source",
    "phase_ii_agency",
    "phase_ii_end_date",
    "phase_iii_contract_id",
    "phase_iii_agency",
    "phase_iii_action_date",
    "latency_days",
    "same_agency",
]


SURVIVAL_COLUMNS: list[str] = [
    "phase_ii_award_id",
    "recipient_uei",
    "recipient_duns",
    "phase_ii_agency",
    "phase_ii_end_date",
    "event_observed",
    "event_date",
    "time_days",
]


def _join_on(
    phase_ii: pd.DataFrame,
    phase_iii: pd.DataFrame,
    key: str,
    basis: str,
) -> pd.DataFrame:
    """Inner join Phase II to Phase III on a single identifier column.

    Caller is responsible for pre-filtering to rows that actually carry the
    identifier. The output carries ``identifier_basis=basis`` and includes
    all valid pairs (no temporal filtering — we preserve negative latencies).
    """

    if phase_ii.empty or phase_iii.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Narrow each side to only the columns we need and rename up-front to
    # avoid pandas' merge-suffix gymnastics.
    ii = (
        phase_ii.loc[phase_ii[key].notna()]
        .loc[:, ["award_id", "source", "agency", "period_of_performance_end", "recipient_uei", "recipient_duns"]]
        .rename(
            columns={
                "award_id": "phase_ii_award_id",
                "source": "phase_ii_source",
                "agency": "phase_ii_agency",
                "period_of_performance_end": "phase_ii_end_date",
            }
        )
        .copy()
    )
    iii = (
        phase_iii.loc[phase_iii[key].notna()]
        .loc[:, ["contract_id", "agency", "action_date", "recipient_uei", "recipient_duns"]]
        .rename(
            columns={
                "contract_id": "phase_iii_contract_id",
                "agency": "phase_iii_agency",
                "action_date": "phase_iii_action_date",
            }
        )
        .copy()
    )
    if ii.empty or iii.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Drop the non-key identifier from whichever side to avoid a suffixed
    # collision (we carry the Phase II side below).
    other_id = "recipient_duns" if key == "recipient_uei" else "recipient_uei"
    if other_id in iii.columns:
        iii = iii.drop(columns=[other_id])

    merged = ii.merge(iii, on=key, how="inner")
    if merged.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    out = pd.DataFrame(
        {
            "recipient_uei": merged["recipient_uei"],
            "recipient_duns": merged["recipient_duns"],
            "identifier_basis": basis,
            "phase_ii_award_id": merged["phase_ii_award_id"],
            "phase_ii_source": merged["phase_ii_source"],
            "phase_ii_agency": merged["phase_ii_agency"],
            "phase_ii_end_date": merged["phase_ii_end_date"],
            "phase_iii_contract_id": merged["phase_iii_contract_id"],
            "phase_iii_agency": merged["phase_iii_agency"],
            "phase_iii_action_date": merged["phase_iii_action_date"],
        }
    )
    # Drop pairs where we can't compute latency.
    out = out.loc[out["phase_ii_end_date"].notna() & out["phase_iii_action_date"].notna()].copy()
    if out.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Compute latency in days, preserving sign.
    ii_end = pd.to_datetime(out["phase_ii_end_date"])
    iii_act = pd.to_datetime(out["phase_iii_action_date"])
    out["latency_days"] = (iii_act - ii_end).dt.days.astype("Int64")

    out["same_agency"] = (
        out["phase_ii_agency"].fillna("").astype(str).str.strip().str.upper()
        == out["phase_iii_agency"].fillna("").astype(str).str.strip().str.upper()
    ) & out["phase_ii_agency"].notna()

    return out[PAIR_COLUMNS].reset_index(drop=True)


def _build_pairs(phase_ii: pd.DataFrame, phase_iii: pd.DataFrame) -> pd.DataFrame:
    """Build the matched-pair table using UEI primary + DUNS fallback.

    A pair is emitted via DUNS fallback only if **at least one side** lacked
    the primary UEI identifier (pre-2022 records mostly). This avoids
    double-counting pairs that already joined on UEI.
    """

    by_uei = _join_on(phase_ii, phase_iii, "recipient_uei", "uei")

    # Rows not already captured by UEI join.
    matched_pii = set(by_uei["phase_ii_award_id"])
    matched_piii = set(by_uei["phase_iii_contract_id"])

    pii_remaining = phase_ii.loc[~phase_ii["award_id"].isin(matched_pii)].copy()
    piii_remaining = phase_iii.loc[~phase_iii["contract_id"].isin(matched_piii)].copy()
    by_duns = _join_on(pii_remaining, piii_remaining, "recipient_duns", "duns_crosswalk")

    frames = [f for f in (by_uei, by_duns) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    pairs = pd.concat(frames, ignore_index=True, sort=False)
    return pairs[PAIR_COLUMNS].reset_index(drop=True)


def _build_survival(
    phase_ii: pd.DataFrame,
    pairs: pd.DataFrame,
    data_cut: date,
) -> pd.DataFrame:
    """Build the KM-ready survival frame.

    - Observed events: earliest Phase III action_date per Phase II award.
    - Censored rows: event_date = data_cut, event_observed=False.
    - ``time_days`` can be negative for observed events where Phase III
      precedes Phase II end.
    """

    if phase_ii.empty:
        return pd.DataFrame(columns=SURVIVAL_COLUMNS)

    # Earliest event per Phase II award.
    if not pairs.empty:
        earliest = (
            pairs.sort_values("phase_iii_action_date", kind="stable")
            .groupby("phase_ii_award_id", as_index=False)
            .first()[["phase_ii_award_id", "phase_iii_action_date"]]
        )
    else:
        earliest = pd.DataFrame(columns=["phase_ii_award_id", "phase_iii_action_date"])

    base = phase_ii[
        [
            "award_id",
            "recipient_uei",
            "recipient_duns",
            "agency",
            "period_of_performance_end",
        ]
    ].rename(
        columns={
            "award_id": "phase_ii_award_id",
            "agency": "phase_ii_agency",
            "period_of_performance_end": "phase_ii_end_date",
        }
    )
    base = base.loc[base["phase_ii_end_date"].notna()].copy()

    merged = base.merge(earliest, on="phase_ii_award_id", how="left")
    merged["event_observed"] = merged["phase_iii_action_date"].notna()
    merged["event_date"] = merged["phase_iii_action_date"].where(
        merged["event_observed"], other=pd.Timestamp(data_cut).date()
    )
    ii_end = pd.to_datetime(merged["phase_ii_end_date"])
    ev = pd.to_datetime(merged["event_date"])
    merged["time_days"] = (ev - ii_end).dt.days.astype("Int64")

    out = merged[SURVIVAL_COLUMNS].reset_index(drop=True)
    return out


def _latency_summary(pairs: pd.DataFrame) -> dict[str, float | int | None]:
    if pairs.empty:
        return {"count": 0, "negative": 0, "p50_days": None, "p90_days": None, "mean_days": None}
    lat = pairs["latency_days"].astype("Int64").dropna().astype(int)
    if lat.empty:
        return {"count": 0, "negative": 0, "p50_days": None, "p90_days": None, "mean_days": None}
    return {
        "count": int(lat.size),
        "negative": int((lat < 0).sum()),
        "p50_days": int(lat.quantile(0.5)),
        "p90_days": int(lat.quantile(0.9)),
        "mean_days": float(round(lat.mean(), 2)),
    }


@asset(
    name="transformed_phase_ii_iii_pairs",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Matched Phase II <-> Phase III pairs joined on recipient_uei with DUNS "
        "crosswalk fallback. Multi-award firms emit all valid pairs; downstream "
        "views (earliest per Phase II, any within 5 years) are derived from this. "
        "Row-level contract: `sbir_etl.models.phase_transition.PhaseTransitionPair`."
    ),
)
def transformed_phase_ii_iii_pairs(
    context: Any | None = None,
    validated_phase_ii_awards: pd.DataFrame | None = None,
    validated_phase_iii_contracts: pd.DataFrame | None = None,
) -> Output[pd.DataFrame]:
    phase_ii = (
        validated_phase_ii_awards
        if validated_phase_ii_awards is not None
        else pd.DataFrame()
    )
    phase_iii = (
        validated_phase_iii_contracts
        if validated_phase_iii_contracts is not None
        else pd.DataFrame()
    )

    pairs = _build_pairs(phase_ii, phase_iii)

    output_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__PAIRS_OUTPUT_PATH", DEFAULT_PAIRS_OUTPUT)
        or DEFAULT_PAIRS_OUTPUT
    )
    ensure_parent_dir(output_path)
    if not pairs.empty:
        pairs.to_parquet(output_path, index=False)

    summary = _latency_summary(pairs)
    basis_counts = (
        pairs["identifier_basis"].value_counts().to_dict() if not pairs.empty else {}
    )

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "total_pairs": int(len(pairs)),
        "identifier_basis": {str(k): int(v) for k, v in basis_counts.items()},
        "latency_summary_days": summary,
        "inputs": {
            "phase_ii_rows": int(len(phase_ii)),
            "phase_iii_rows": int(len(phase_iii)),
        },
    }
    checks_path = output_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    metadata = {
        "rows": int(len(pairs)),
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "identifier_basis": MetadataValue.json(checks["identifier_basis"]),
        "latency_summary_days": MetadataValue.json(summary),
    }

    log = getattr(context, "log", logger) if context is not None else logger
    log.info("transformed_phase_ii_iii_pairs complete", extra={"rows": len(pairs), **summary})
    return Output(pairs, metadata=metadata)  # type: ignore[arg-type]


@asset(
    name="transformed_phase_transition_survival",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Per-Phase-II time-to-event frame: event_observed + time_days "
        "(days from phase_ii_end_date to earliest phase_iii_action_date, or to "
        "the data-cut date when censored). Suitable for Kaplan-Meier. "
        "Row-level contract: `sbir_etl.models.phase_transition.PhaseTransitionSurvival`."
    ),
)
def transformed_phase_transition_survival(
    context: Any | None = None,
    validated_phase_ii_awards: pd.DataFrame | None = None,
    transformed_phase_ii_iii_pairs: pd.DataFrame | None = None,
) -> Output[pd.DataFrame]:
    phase_ii = (
        validated_phase_ii_awards
        if validated_phase_ii_awards is not None
        else pd.DataFrame()
    )
    pairs = (
        transformed_phase_ii_iii_pairs
        if transformed_phase_ii_iii_pairs is not None
        else pd.DataFrame()
    )

    data_cut = parse_data_cut_date()
    survival = _build_survival(phase_ii, pairs, data_cut)

    output_path = Path(
        env_str("SBIR_ETL__PHASE_TRANSITION__SURVIVAL_OUTPUT_PATH", DEFAULT_SURVIVAL_OUTPUT)
        or DEFAULT_SURVIVAL_OUTPUT
    )
    ensure_parent_dir(output_path)
    if not survival.empty:
        survival.to_parquet(output_path, index=False)

    total = int(len(survival))
    observed = int(survival["event_observed"].sum()) if total else 0
    censored = total - observed
    match_rate = (observed / total) if total else 0.0

    # 5-year transition view: fraction of observed events where time_days <= 5*365.
    horizon_days = 5 * 365
    five_year_rate: float | None = None
    if total:
        within = survival.loc[survival["event_observed"] & (survival["time_days"] <= horizon_days)]
        five_year_rate = float(len(within) / total)

    checks = {
        "ok": True,
        "generated_at": now_utc_iso(),
        "data_cut_date": data_cut.isoformat(),
        "total_phase_ii": total,
        "observed_events": observed,
        "censored": censored,
        "match_rate": round(match_rate, 4),
        "within_5_year_rate": round(five_year_rate, 4) if five_year_rate is not None else None,
        "inputs": {
            "phase_ii_rows": int(len(phase_ii)),
            "pair_rows": int(len(pairs)),
        },
    }
    checks_path = output_path.with_suffix(".checks.json")
    write_json(checks_path, checks)

    metadata = {
        "rows": total,
        "output_path": str(output_path),
        "checks_path": str(checks_path),
        "match_rate": round(match_rate, 4),
        "data_cut_date": data_cut.isoformat(),
        "within_5_year_rate": round(five_year_rate, 4) if five_year_rate is not None else "n/a",
    }

    log = getattr(context, "log", logger) if context is not None else logger
    log.info(
        "transformed_phase_transition_survival complete",
        extra={
            "rows": total,
            "observed": observed,
            "censored": censored,
            "match_rate": match_rate,
        },
    )
    return Output(survival, metadata=metadata)  # type: ignore[arg-type]


__all__ = [
    "PAIR_COLUMNS",
    "SURVIVAL_COLUMNS",
    "transformed_phase_ii_iii_pairs",
    "transformed_phase_transition_survival",
    "_build_pairs",
    "_build_survival",
]

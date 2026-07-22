"""Reproducible DoD SBIR industrial-base concentration baseline.

This module measures observable award concentration.  It deliberately does
not claim to describe bills of material, sub-tier suppliers, or physical
supply-chain dependency.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.reporting.defense_taxonomy_crosswalk import (
    DefenseTaxonomyCrosswalk,
    load_defense_crosswalk,
)
from sbir_etl.utils.text_normalization import normalize_company_name


FACT_COLUMNS = [
    "award_id",
    "fiscal_year",
    "organization_id",
    "organization_name",
    "identity_method",
    "identity_confidence",
    "exact_identity",
    "cet_area",
    "cet_score",
    "taxonomy_version",
    "dod_cta14",
    "dod_sc8",
    "award_amount",
    "phase",
    "dod_component",
    "naics_code",
    "naics_2digit",
    "state",
    "congressional_district",
    "first_observed_fy",
    "first_observed_entrant",
]

CANONICAL_TAXONOMY_VERSION = "NSTC-2025Q1"


@dataclass(frozen=True)
class DoDSupplyChainBaseline:
    """The three public data interfaces plus run metadata."""

    award_facts: pd.DataFrame
    cet_metrics: pd.DataFrame
    firm_flags: pd.DataFrame
    metadata: dict[str, Any]


def latest_complete_fiscal_year(as_of: date) -> int:
    """Return the most recently completed US federal fiscal year."""

    current_fy = as_of.year + 1 if as_of.month >= 10 else as_of.year
    return current_fy - 1


def _first_column(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in df.columns:
            return df[name]
    return pd.Series([None] * len(df), index=df.index, dtype="object")


def _clean_identifier(value: object) -> str | None:
    if _is_missing_scalar(value):
        return None
    text = str(value).strip().upper()
    return text if text and text not in {"NAN", "NONE", "NULL"} else None


def _is_missing_scalar(value: object) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def _federal_fiscal_years(awards: pd.DataFrame) -> pd.Series:
    explicit = pd.to_numeric(
        _first_column(awards, ("fiscal_year", "award_fiscal_year", "fy")), errors="coerce"
    )
    dates = pd.to_datetime(
        _first_column(awards, ("award_date", "proposal_award_date", "Proposal Award Date")),
        errors="coerce",
    )
    derived = dates.dt.year + (dates.dt.month >= 10).astype("Int64")
    return explicit.fillna(derived).astype("Int64")


def _dod_mask(awards: pd.DataFrame) -> pd.Series:
    agency_code = (
        _first_column(awards, ("awarding_agency_code", "agency_code", "funding_agency_code"))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    code_match = agency_code.str.match(r"^(9700|97)$", na=False)
    agency = (
        _first_column(awards, ("agency", "awarding_agency_name", "funding_agency_name"))
        .fillna("")
        .astype(str)
        .str.upper()
    )
    name_match = agency.str.contains(
        r"\bDOD\b|\bDEPARTMENT OF DEFENSE\b|\bDEFENSE DEPARTMENT\b", regex=True, na=False
    )
    return code_match | name_match


def _identity_frame(awards: pd.DataFrame) -> pd.DataFrame:
    canonical = _first_column(
        awards, ("organization_id", "canonical_organization_id", "canonical_id", "company_id")
    ).map(_clean_identifier)
    uei = _first_column(awards, ("company_uei", "uei", "recipient_uei", "vendor_uei")).map(
        _clean_identifier
    )
    cage = _first_column(awards, ("company_cage", "cage", "cage_code", "vendor_cage")).map(
        _clean_identifier
    )
    duns = _first_column(awards, ("company_duns", "duns", "recipient_duns", "vendor_duns")).map(
        _clean_identifier
    )
    names = _first_column(awards, ("company_name", "company", "recipient_name", "vendor_name"))

    rows: list[dict[str, object]] = []
    for can, row_uei, row_cage, row_duns, raw_name in zip(
        canonical, uei, cage, duns, names, strict=False
    ):
        normalized_name = normalize_company_name(None if pd.isna(raw_name) else str(raw_name))
        candidates = (
            ("canonical", can),
            ("uei", row_uei),
            ("cage", row_cage),
            ("duns", row_duns),
            ("name", normalized_name.upper() if normalized_name else None),
        )
        method, identifier = next(
            ((m, v) for m, v in candidates if v is not None and not pd.isna(v) and str(v).strip()),
            ("unresolved", None),
        )
        rows.append(
            {
                "organization_id": f"{method}:{identifier}" if identifier else None,
                "organization_name": None if pd.isna(raw_name) else str(raw_name).strip(),
                "identity_method": method,
                "identity_confidence": 1.0
                if method != "name" and identifier
                else 0.5
                if identifier
                else 0.0,
                "exact_identity": method in {"canonical", "uei", "cage", "duns"},
            }
        )
    return pd.DataFrame(rows, index=awards.index)


def _normalize_phase(value: object) -> str | None:
    if _is_missing_scalar(value):
        return None
    text = str(value).strip().upper().removeprefix("PHASE ").strip()
    return {"1": "I", "I": "I", "2": "II", "II": "II", "3": "III", "III": "III"}.get(text)


def _parse_boolean(value: object) -> bool | None:
    if _is_missing_scalar(value):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    raise ValueError(f"unsupported event_observed value: {value!r}")


def build_award_facts(
    awards: pd.DataFrame,
    classifications: pd.DataFrame,
    *,
    as_of: date,
    min_fiscal_year: int = 2012,
    min_cet_score: float = 40.0,
    expected_taxonomy_version: str = CANONICAL_TAXONOMY_VERSION,
    defense_crosswalk: DefenseTaxonomyCrosswalk | None = None,
) -> pd.DataFrame:
    """Build one non-duplicated fact row per classified DoD award."""

    if awards.empty:
        raise ValueError("enriched awards are required and must not be empty")
    if classifications.empty:
        raise ValueError("CET classifications are required and must not be empty")
    if "award_id" not in awards.columns or "award_id" not in classifications.columns:
        raise ValueError("awards and classifications must contain award_id")

    cet_col = next(
        (name for name in ("primary_cet", "cet_area", "cet_primary") if name in classifications),
        None,
    )
    score_col = next(
        (name for name in ("primary_score", "cet_score", "confidence") if name in classifications),
        None,
    )
    if not cet_col or not score_col:
        raise ValueError("classifications must contain primary CET and score columns")
    crosswalk = defense_crosswalk or load_defense_crosswalk()
    if crosswalk.source_taxonomy != expected_taxonomy_version:
        raise ValueError(
            f"defense crosswalk expects {crosswalk.source_taxonomy!r}, not "
            f"{expected_taxonomy_version!r}"
        )

    cohort = awards.loc[_dod_mask(awards)].copy()
    cohort["fiscal_year"] = _federal_fiscal_years(cohort)
    last_fy = latest_complete_fiscal_year(as_of)
    cohort = cohort.loc[cohort["fiscal_year"].between(min_fiscal_year, last_fy)].copy()
    if cohort.empty:
        raise ValueError("no DoD awards remain after fiscal-year filtering")
    duplicate_awards = cohort.loc[cohort["award_id"].duplicated(keep=False), "award_id"]
    if not duplicate_awards.empty:
        sample = sorted(duplicate_awards.astype(str).unique())[:5]
        raise ValueError(f"duplicate DoD award_id rows would double-count dollars: {sample}")

    cls = classifications.copy()
    cls["_cet_score"] = pd.to_numeric(cls[score_col], errors="coerce")
    cls = cls.loc[cls[cet_col].notna() & (cls["_cet_score"] >= min_cet_score)].copy()
    if "taxonomy_version" not in cls.columns:
        raise ValueError("classifications must contain taxonomy_version")
    cls = cls.sort_values(["award_id", "_cet_score"], ascending=[True, False]).drop_duplicates(
        "award_id", keep="first"
    )
    cls = cls.loc[cls["award_id"].isin(cohort["award_id"])]
    versions = set(cls["taxonomy_version"].dropna().astype(str))
    if versions != {expected_taxonomy_version}:
        raise ValueError(
            f"expected taxonomy {expected_taxonomy_version!r}, found {sorted(versions)!r}"
        )
    cls = cls.rename(columns={cet_col: "cet_area"})
    cls["cet_score"] = cls["_cet_score"]
    keep = ["award_id", "cet_area", "cet_score"]
    if "taxonomy_version" in cls:
        keep.append("taxonomy_version")
    cohort = cohort.merge(cls[keep], on="award_id", how="inner", validate="many_to_one")
    if cohort.empty:
        raise ValueError("no DoD awards have a qualifying primary CET classification")

    identity = _identity_frame(cohort)
    for column in identity:
        cohort[column] = identity[column].to_numpy()
    unresolved = cohort["organization_id"].isna()
    cohort.loc[unresolved, "organization_id"] = cohort.loc[unresolved, "award_id"].map(
        lambda value: f"award:{value}"
    )

    facts = pd.DataFrame(index=cohort.index)
    facts["award_id"] = cohort["award_id"].astype(str)
    facts["fiscal_year"] = cohort["fiscal_year"].astype(int)
    for column in (
        "organization_id",
        "organization_name",
        "identity_method",
        "identity_confidence",
        "exact_identity",
        "cet_area",
        "cet_score",
    ):
        facts[column] = cohort[column]
    facts["taxonomy_version"] = cohort.get("taxonomy_version")
    facts["dod_cta14"] = facts["cet_area"].map(
        lambda cet_id: crosswalk.targets_for(str(cet_id), "dod_cta14")
    )
    facts["dod_sc8"] = facts["cet_area"].map(
        lambda cet_id: crosswalk.targets_for(str(cet_id), "dod_sc8")
    )
    facts["award_amount"] = pd.to_numeric(
        _first_column(cohort, ("award_amount", "Award Amount", "obligation_amount")),
        errors="coerce",
    )
    facts["phase"] = _first_column(cohort, ("phase", "award_phase")).map(_normalize_phase)
    facts["dod_component"] = _first_column(
        cohort, ("branch", "sub_agency", "awarding_sub_tier_agency_name")
    )
    facts["naics_code"] = _first_column(
        cohort, ("naics_code", "fiscal_naics_code", "naics_primary", "primary_naics")
    ).map(_clean_identifier)
    facts["naics_2digit"] = facts["naics_code"].map(lambda value: value[:2] if value else None)
    facts["state"] = _first_column(cohort, ("state", "company_state", "recipient_state"))
    facts["congressional_district"] = _first_column(cohort, ("congressional_district", "district"))
    facts["first_observed_fy"] = facts.groupby("organization_id")["fiscal_year"].transform("min")
    facts["first_observed_entrant"] = facts["fiscal_year"] == facts["first_observed_fy"]
    return facts[FACT_COLUMNS].sort_values(["fiscal_year", "award_id"]).reset_index(drop=True)


def _hhi(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    numeric = numeric.loc[numeric > 0]
    total = float(numeric.sum())
    if not total:
        return None
    shares = numeric / total
    return float((shares * shares).sum())


def _wilson(successes: int, total: int) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _transition_summary(group: pd.DataFrame, survival: pd.DataFrame | None) -> dict[str, object]:
    empty = {
        "transition_status": "not_computed",
        "transition_eligible": 0,
        "transition_observed_5yr": 0,
        "transition_immature_censored": 0,
        "transition_rate_5yr": None,
        "transition_ci95_low": None,
        "transition_ci95_high": None,
    }
    if survival is None or survival.empty:
        return empty
    required = {"phase_ii_award_id", "event_observed", "time_days"}
    if not required.issubset(survival.columns):
        return empty
    phase_ii_ids = set(group.loc[group["phase"] == "II", "award_id"].astype(str))
    if not phase_ii_ids:
        return {**empty, "transition_status": "computed"}
    frame = survival.copy()
    frame["phase_ii_award_id"] = frame["phase_ii_award_id"].astype(str)
    frame = frame.loc[frame["phase_ii_award_id"].isin(phase_ii_ids)].drop_duplicates(
        "phase_ii_award_id"
    )
    if frame.empty:
        return {**empty, "transition_status": "computed"}
    days = pd.to_numeric(frame["time_days"], errors="coerce")
    observed_parsed = frame["event_observed"].map(_parse_boolean)
    observed = observed_parsed.fillna(False).astype(bool)
    horizon = 5 * 365
    eligible = days.notna() & (observed | (days >= horizon))
    successes = eligible & observed & (days <= horizon)
    immature = days.notna() & ~observed & (days < horizon)
    n_eligible = int(eligible.sum())
    n_success = int(successes.sum())
    low, high = _wilson(n_success, n_eligible)
    return {
        "transition_status": "computed",
        "transition_eligible": n_eligible,
        "transition_observed_5yr": n_success,
        "transition_immature_censored": int(immature.sum()),
        "transition_rate_5yr": n_success / n_eligible if n_eligible else None,
        "transition_ci95_low": low,
        "transition_ci95_high": high,
    }


def _period_groups(facts: pd.DataFrame, latest_fy: int, window_years: int):
    for fy in sorted(facts["fiscal_year"].unique()):
        yield "annual", int(fy), int(fy), facts.loc[facts["fiscal_year"] == fy]
    start = latest_fy - window_years + 1
    yield (
        "latest_complete_window",
        start,
        latest_fy,
        facts.loc[facts["fiscal_year"].between(start, latest_fy)],
    )


def _ordered_tag_union(values: pd.Series) -> list[str]:
    return sorted({tag for tags in values for tag in tags})


def build_cet_metrics(
    facts: pd.DataFrame,
    *,
    latest_fy: int,
    survival: pd.DataFrame | None = None,
    window_years: int = 5,
) -> pd.DataFrame:
    """Compute annual and latest-window CET concentration components."""

    records: list[dict[str, object]] = []
    for period_type, start_fy, end_fy, period in _period_groups(facts, latest_fy, window_years):
        for cet_area, group in period.groupby("cet_area", sort=True):
            resolved_group = group.loc[group["identity_method"] != "unresolved"]
            firm = resolved_group.groupby("organization_id", dropna=False).agg(
                award_count=("award_id", "nunique"),
                award_dollars=("award_amount", "sum"),
            )
            dollars = (
                float(group["award_amount"].sum(min_count=1))
                if group["award_amount"].notna().any()
                else 0.0
            )
            dollar_hhi = _hhi(firm["award_dollars"])
            count_hhi = _hhi(firm["award_count"])
            exact_group = group.loc[group["exact_identity"]]
            exact_firm = exact_group.groupby("organization_id", dropna=False).agg(
                award_count=("award_id", "nunique"),
                award_dollars=("award_amount", "sum"),
            )
            ordered = firm["award_dollars"].clip(lower=0).sort_values(ascending=False)
            top1 = float(ordered.head(1).sum() / dollars) if dollars > 0 else None
            top3 = float(ordered.head(3).sum() / dollars) if dollars > 0 else None
            entrant_ids = set(
                resolved_group.loc[
                    resolved_group["first_observed_fy"].between(start_fy, end_fy),
                    "organization_id",
                ]
            )
            entrant_rows = group["organization_id"].isin(entrant_ids)
            distinct_firms = int(resolved_group["organization_id"].nunique())
            states = group.loc[group["state"].notna()].groupby("state")["award_amount"].sum()
            districts = (
                group.loc[group["congressional_district"].notna()]
                .groupby("congressional_district")["award_amount"]
                .sum()
            )
            transition = _transition_summary(group, survival)
            records.append(
                {
                    "period_type": period_type,
                    "period_start_fy": start_fy,
                    "period_end_fy": end_fy,
                    "cet_area": cet_area,
                    "dod_cta14": _ordered_tag_union(group["dod_cta14"]),
                    "dod_sc8": _ordered_tag_union(group["dod_sc8"]),
                    "award_count": int(group["award_id"].nunique()),
                    "distinct_firms": distinct_firms,
                    "award_dollars": dollars,
                    "dollar_hhi": dollar_hhi,
                    "award_count_hhi": count_hhi,
                    "effective_firms_dollars": (1 / dollar_hhi) if dollar_hhi else None,
                    "top1_dollar_share": top1,
                    "top3_dollar_share": top3,
                    "sole_base": distinct_firms == 1,
                    "thin_base": 0 < distinct_firms <= 3,
                    "dominant_firm": top1 is not None and top1 >= 0.5,
                    "state_dollar_hhi": _hhi(states),
                    "district_dollar_hhi": _hhi(districts),
                    "missing_amount_share": float(group["award_amount"].isna().mean()),
                    "missing_state_share": float(group["state"].isna().mean()),
                    "missing_district_share": float(group["congressional_district"].isna().mean()),
                    "exact_identity_award_share": float(group["exact_identity"].mean()),
                    "unresolved_identity_award_share": float(
                        (group["identity_method"] == "unresolved").mean()
                    ),
                    "exact_identity_award_count": int(exact_group["award_id"].nunique()),
                    "exact_identity_distinct_firms": int(exact_group["organization_id"].nunique()),
                    "exact_identity_award_dollars": float(
                        exact_group["award_amount"].sum(min_count=1)
                    )
                    if exact_group["award_amount"].notna().any()
                    else 0.0,
                    "exact_identity_dollar_hhi": _hhi(exact_firm["award_dollars"]),
                    "entrant_firms": len(entrant_ids),
                    "entrant_firm_share": len(entrant_ids) / distinct_firms
                    if distinct_firms
                    else None,
                    "entrant_dollars": float(group.loc[entrant_rows, "award_amount"].sum()),
                    "entrant_dollar_share": (
                        float(group.loc[entrant_rows, "award_amount"].sum()) / dollars
                        if dollars > 0
                        else None
                    ),
                    **transition,
                    "acp10_screening_flag": None,
                }
            )
    metrics = pd.DataFrame(records)
    if metrics.empty:
        return metrics
    for _, indexes in metrics.groupby(
        ["period_type", "period_start_fy", "period_end_fy"]
    ).groups.items():
        subset = metrics.loc[indexes]
        eligible = subset.dropna(subset=["transition_rate_5yr", "entrant_firm_share"])
        if eligible.empty:
            continue
        transition_q25 = eligible["transition_rate_5yr"].quantile(0.25)
        entrant_q25 = eligible["entrant_firm_share"].quantile(0.25)
        for idx in indexes:
            row = metrics.loc[idx]
            if pd.isna(row["transition_rate_5yr"]) or pd.isna(row["entrant_firm_share"]):
                continue
            metrics.at[idx, "acp10_screening_flag"] = bool(
                (row["thin_base"] or row["dominant_firm"])
                and row["transition_rate_5yr"] <= transition_q25
                and row["entrant_firm_share"] <= entrant_q25
            )
    metrics["acp10_screening_flag"] = metrics["acp10_screening_flag"].astype("boolean")
    return metrics.sort_values(["period_end_fy", "period_type", "cet_area"]).reset_index(drop=True)


def build_firm_flags(facts: pd.DataFrame, *, latest_fy: int, window_years: int = 5) -> pd.DataFrame:
    """Return firm-level evidence for sole, thin, and dominant latest-window bases."""

    start_fy = latest_fy - window_years + 1
    window = facts.loc[facts["fiscal_year"].between(start_fy, latest_fy)]
    records: list[dict[str, object]] = []
    for cet_area, group in window.groupby("cet_area", sort=True):
        resolved_group = group.loc[group["identity_method"] != "unresolved"]
        aggregates = (
            resolved_group.groupby(
                ["organization_id", "organization_name", "identity_method"], dropna=False
            )
            .agg(award_count=("award_id", "nunique"), award_dollars=("award_amount", "sum"))
            .reset_index()
            .sort_values(["award_dollars", "organization_id"], ascending=[False, True])
        )
        total = float(aggregates["award_dollars"].sum())
        base_size = len(aggregates)
        for rank, (_, row) in enumerate(aggregates.iterrows(), start=1):
            award_dollars = float(row["award_dollars"])
            share = award_dollars / total if total > 0 else None
            sole = base_size == 1
            dominant = rank == 1 and share is not None and share >= 0.5
            if not (sole or base_size <= 3 or dominant):
                continue
            records.append(
                {
                    "period_start_fy": start_fy,
                    "period_end_fy": latest_fy,
                    "cet_area": cet_area,
                    "organization_id": row["organization_id"],
                    "organization_name": row["organization_name"],
                    "identity_method": row["identity_method"],
                    "firm_rank": rank,
                    "award_count": int(row["award_count"]),
                    "award_dollars": award_dollars,
                    "dollar_share": share,
                    "base_firm_count": base_size,
                    "sole_base_firm": sole,
                    "thin_base_member": base_size <= 3,
                    "dominant_firm": dominant,
                }
            )
    return (
        pd.DataFrame(records).sort_values(["cet_area", "firm_rank"]).reset_index(drop=True)
        if records
        else pd.DataFrame()
    )


def build_baseline(
    awards: pd.DataFrame,
    classifications: pd.DataFrame,
    *,
    survival: pd.DataFrame | None = None,
    as_of: date | None = None,
    min_fiscal_year: int = 2012,
    min_cet_score: float = 40.0,
    window_years: int = 5,
    expected_taxonomy_version: str = CANONICAL_TAXONOMY_VERSION,
    crosswalk_path: Path | None = None,
) -> DoDSupplyChainBaseline:
    """Build all public interfaces for the DoD-only baseline."""

    cutoff = as_of or datetime.now(UTC).date()
    last_fy = latest_complete_fiscal_year(cutoff)
    defense_crosswalk = load_defense_crosswalk(crosswalk_path=crosswalk_path)
    facts = build_award_facts(
        awards,
        classifications,
        as_of=cutoff,
        min_fiscal_year=min_fiscal_year,
        min_cet_score=min_cet_score,
        expected_taxonomy_version=expected_taxonomy_version,
        defense_crosswalk=defense_crosswalk,
    )
    metrics = build_cet_metrics(
        facts, latest_fy=last_fy, survival=survival, window_years=window_years
    )
    flags = build_firm_flags(facts, latest_fy=last_fy, window_years=window_years)
    taxonomy_versions = sorted(facts["taxonomy_version"].dropna().astype(str).unique())
    metadata = {
        "scope": "DoD SBIR/STTR awardee industrial-base concentration",
        "exclusions": [
            "physical and sub-tier supply chains",
            "M&A, UCC, patent-citation, and subaward signals",
        ],
        "as_of_date": cutoff.isoformat(),
        "min_fiscal_year": min_fiscal_year,
        "latest_complete_fiscal_year": last_fy,
        "headline_window_years": window_years,
        "minimum_primary_cet_score": min_cet_score,
        "expected_taxonomy_version": expected_taxonomy_version,
        "taxonomy_versions": taxonomy_versions,
        "defense_crosswalk_version": defense_crosswalk.version,
        "defense_crosswalk_source": str(defense_crosswalk.source_path),
        "defense_target_versions": defense_crosswalk.target_versions,
        "award_fact_rows": len(facts),
        "metric_rows": len(metrics),
        "firm_flag_rows": len(flags),
        "transition_status": "computed"
        if survival is not None and not survival.empty
        else "not_computed",
        "entrant_definition": "first observed DoD SBIR/STTR award in the retained FY2012+ corpus; left-censored",
        "identity_policy": (
            "canonical organization ID, then UEI, CAGE, DUNS, normalized name; "
            "unresolved awards remain in award totals but are excluded from firm denominators"
        ),
        "interpretation_guardrail": "Award concentration is not physical supply-chain dependency.",
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    return DoDSupplyChainBaseline(facts, metrics, flags, metadata)


def write_baseline_outputs(result: DoDSupplyChainBaseline, output_dir: Path) -> dict[str, str]:
    """Write deterministic Parquet/JSON interfaces and run metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "dod_supply_chain_award_facts": result.award_facts,
        "dod_supply_chain_cet_metrics": result.cet_metrics,
        "dod_supply_chain_firm_flags": result.firm_flags,
    }
    paths: dict[str, str] = {}
    for name, table in tables.items():
        parquet_path = output_dir / f"{name}.parquet"
        json_path = output_dir / f"{name}.json"
        table.to_parquet(parquet_path, index=False)
        json_path.write_text(table.to_json(orient="records", indent=2), encoding="utf-8")
        paths[f"{name}_parquet"] = str(parquet_path)
        paths[f"{name}_json"] = str(json_path)
    metadata_path = output_dir / "dod_supply_chain_run_metadata.json"
    metadata_path.write_text(
        json.dumps(result.metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["metadata_json"] = str(metadata_path)
    return paths


__all__ = [
    "CANONICAL_TAXONOMY_VERSION",
    "DoDSupplyChainBaseline",
    "build_award_facts",
    "build_baseline",
    "build_cet_metrics",
    "build_firm_flags",
    "latest_complete_fiscal_year",
    "write_baseline_outputs",
]

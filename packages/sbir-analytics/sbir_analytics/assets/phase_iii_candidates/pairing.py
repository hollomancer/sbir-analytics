"""Shared UEI pair construction and Phase III candidate filters."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

# FPDS Element 10Q codes that mark a contract as already-coded Phase III.
# Duplicated intentionally — avoids cross-package import for a five-element set.
_PHASE_III_RESEARCH_CODES = frozenset({"SR3", "ST3"})

# Tokens we accept as evidence that ``sbir_phase`` already says "Phase III".
_PHASE_III_LABELS = frozenset({"PHASE III", "III", "3", "PHASE 3"})


PAIR_S1_COLUMNS: list[str] = [
    "prior_award_id",
    "prior_recipient_uei",
    "prior_agency",
    "prior_sub_agency",
    "prior_office",
    "prior_naics_code",
    "prior_psc_code",
    "prior_title",
    "prior_abstract",
    "prior_period_of_performance_end",
    "prior_cet",
    "target_id",
    "target_recipient_uei",
    "target_agency",
    "target_sub_agency",
    "target_office",
    "target_naics_code",
    "target_psc_code",
    "target_description",
    "target_action_date",
    "target_competition_type",
    "target_obligated_amount",
    "agency_match_level",
]

# The shared, pre-gate schema.  ``pair_filter_s1`` deliberately projects back
# to ``PAIR_S1_COLUMNS`` so the existing weighted candidate path keeps its
# exact public shape.
PAIR_COLUMNS: list[str] = [
    *PAIR_S1_COLUMNS[:-1],
    "target_research",
    "target_sbir_phase",
    "target_transaction_id",
    "target_contract_key",
    "agency_match_level",
]


def _normalize(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).strip().upper()
    return "" if s in {"", "<NA>", "NAN", "NONE", "NULL"} else s


def _is_phase_iii_already_coded(row: pd.Series) -> bool:
    """True iff a contract row already carries explicit Phase III coding."""

    research = row.get("target_research") if "target_research" in row else row.get("research")
    if isinstance(research, str) and research.strip().upper() in _PHASE_III_RESEARCH_CODES:
        return True

    sbir_phase = (
        row.get("target_sbir_phase") if "target_sbir_phase" in row else row.get("sbir_phase")
    )
    if sbir_phase is not None:
        label = _normalize(sbir_phase)
        if label in _PHASE_III_LABELS:
            return True
    return False


def _agency_match_level(prior: pd.Series, target: pd.Series) -> str | None:
    """Return ``office`` > ``sub_tier`` > ``agency`` match level, or None."""

    p_office = _normalize(prior.get("prior_office"))
    t_office = _normalize(target.get("target_office"))
    if p_office and t_office and p_office == t_office:
        return "office"

    p_sub = _normalize(prior.get("prior_sub_agency"))
    t_sub = _normalize(target.get("target_sub_agency"))
    if p_sub and t_sub and p_sub == t_sub:
        return "sub_tier"

    p_ag = _normalize(prior.get("prior_agency"))
    t_ag = _normalize(target.get("target_agency"))
    if p_ag and t_ag and p_ag == t_ag:
        return "agency"

    return None


def _prepare_priors(prior_awards: pd.DataFrame) -> pd.DataFrame:
    """Project & rename the prior-award frame to canonical ``prior_*`` columns."""

    if prior_awards.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("prior_")])

    df = prior_awards.copy()

    def _col(name: str, default: object = None) -> pd.Series:
        if name in df.columns:
            return df[name]
        return pd.Series([default] * len(df), index=df.index)

    out = pd.DataFrame(
        {
            "prior_award_id": _col("award_id"),
            "prior_recipient_uei": _col("recipient_uei"),
            "prior_agency": _col("agency"),
            "prior_sub_agency": _col("sub_agency"),
            "prior_office": _col("office"),
            "prior_naics_code": _col("naics_code"),
            "prior_psc_code": _col("psc_code"),
            "prior_title": _col("title"),
            "prior_abstract": _col("abstract"),
            "prior_period_of_performance_end": _col("period_of_performance_end"),
            "prior_cet": _col("cet"),
        }
    )
    # UEI is the join gate — drop priors without one.
    out = out.loc[out["prior_recipient_uei"].astype(str).str.strip() != ""].copy()
    out = out.loc[out["prior_recipient_uei"].notna()].reset_index(drop=True)
    return out


def _metadata_field(df: pd.DataFrame, *names: str) -> pd.Series:
    """Return the first present metadata value per row for ``names``.

    ``ContractExtractor`` persists the USAspending transaction id and generated
    unique award id in its top-level ``metadata`` struct.  Reading those values
    is field pass-through; no identifier is inferred or synthesized here.
    """

    if "metadata" not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype="object")

    def _get(value: object) -> object:
        if not isinstance(value, Mapping):
            return None
        for name in names:
            candidate = value.get(name)
            if candidate is not None and _normalize(candidate):
                return candidate
        return None

    return df["metadata"].map(_get)


def _coalesce_fields(
    df: pd.DataFrame, *fields: str, fallback: pd.Series | None = None
) -> pd.Series:
    """Coalesce identifier fields per row, treating blank/null-like strings as absent."""

    out = pd.Series([None] * len(df), index=df.index, dtype="object")
    for field in fields:
        if field not in df.columns:
            continue
        source = df[field]
        missing = out.map(_normalize).eq("")
        usable = source.map(_normalize).ne("")
        out.loc[missing & usable] = source.loc[missing & usable]
    if fallback is not None:
        missing = out.map(_normalize).eq("")
        usable = fallback.map(_normalize).ne("")
        out.loc[missing & usable] = fallback.loc[missing & usable]
    return out


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    """Project and rename contracts to the shared canonical ``target_*`` schema."""

    if contracts.empty:
        return pd.DataFrame(columns=[c for c in PAIR_COLUMNS if c.startswith("target_")])

    df = contracts.copy()

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    metadata_transaction_id = _metadata_field(df, "transaction_unique_id", "transaction_id")
    metadata_contract_key = _metadata_field(df, "generated_unique_award_id", "award_id")

    out = pd.DataFrame(
        {
            "target_id": _pick("contract_id", "piid", "generated_unique_award_id"),
            "target_recipient_uei": _pick("vendor_uei", "recipient_uei", "uei"),
            "target_agency": _pick("awarding_agency_name", "agency", "awarding_agency"),
            "target_sub_agency": _pick("awarding_sub_tier_agency_name", "sub_agency"),
            "target_office": _pick("awarding_office_name", "office"),
            "target_naics_code": _pick("naics_code", "naics"),
            "target_psc_code": _pick("psc_code", "product_or_service_code"),
            "target_description": _pick(
                "transaction_description", "description", "award_description"
            ),
            "target_action_date": _pick("action_date", "award_date"),
            "target_competition_type": _pick(
                "extent_competed", "competition_type", "type_of_set_aside"
            ),
            "target_obligated_amount": _pick(
                "federal_action_obligation", "obligated_amount", "obligation_amount"
            ),
            "target_research": _pick("research"),
            "target_sbir_phase": _pick("sbir_phase"),
            "target_transaction_id": _coalesce_fields(
                df,
                "transaction_unique_id",
                "transaction_id",
                fallback=metadata_transaction_id,
            ),
            "target_contract_key": _coalesce_fields(
                df,
                "generated_unique_award_id",
                "unique_award_key",
                fallback=metadata_contract_key,
            ),
        }
    )
    out = out.loc[out["target_recipient_uei"].astype(str).str.strip() != ""].copy()
    out = out.loc[out["target_recipient_uei"].notna()].reset_index(drop=True)
    return out


def build_uei_pairs(
    prior_awards: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """Build the normalized, nonblank, exact-UEI pair universe without filtering it.

    This is the shared boundary for the legacy scoring path and label-free
    census.  It intentionally performs no agency or SBIR/STTR-code gate.
    """

    priors = _prepare_priors(prior_awards)
    targets = _prepare_contracts(contracts)
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Normalize the join key so case/whitespace differences don't drop pairs.
    priors = priors.assign(_uei=priors["prior_recipient_uei"].map(_normalize))
    targets = targets.assign(_uei=targets["target_recipient_uei"].map(_normalize))
    priors = priors.loc[priors["_uei"] != ""].copy()
    targets = targets.loc[targets["_uei"] != ""].copy()
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    merged = priors.merge(targets, on="_uei", how="inner", suffixes=("", "_t"))
    if merged.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    # Describe the finest observed match, but retain cross-agency pairs as null.
    levels = merged.apply(  # type: ignore[call-overload]
        lambda r: _agency_match_level(r, r),
        axis=1,
    )
    merged = merged.assign(agency_match_level=levels)
    merged = merged.drop(columns=["_uei"])
    return merged.loc[:, PAIR_COLUMNS].reset_index(drop=True)


def pair_filter_s1(
    prior_awards: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """S1 retrospective filter: legacy coded-status and hierarchical agency gates."""

    pairs = build_uei_pairs(prior_awards, contracts)
    if pairs.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    coded_mask = pairs.apply(_is_phase_iii_already_coded, axis=1)
    merged = pairs.loc[~coded_mask & pairs["agency_match_level"].notna()].copy()
    if merged.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    return merged.loc[:, PAIR_S1_COLUMNS].reset_index(drop=True)


__all__ = [
    "PAIR_COLUMNS",
    "PAIR_S1_COLUMNS",
    "build_uei_pairs",
    "pair_filter_s1",
]

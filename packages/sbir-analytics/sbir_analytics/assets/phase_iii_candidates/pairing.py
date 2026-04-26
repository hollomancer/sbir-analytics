"""Pair-filter functions for Phase III candidate signal classes.

Each pair filter is a small module-level function that takes a prior-award frame
and a target frame (contracts or opportunities) and returns the pre-merged
``(prior, target)`` candidate rows that pass the structural gate. The asset
factory then scores those rows.

v1 implements the S1 (RETROSPECTIVE) filter only — S2 and S3 land in later
phases. See ``specs/phase-3-solicitation-alerts/design.md`` for the full set.

The merge shape mirrors ``transformed_phase_ii_iii_pairs``: pre-narrow each
side, then a pandas inner-merge on the join key. UEI is the gate, so the full
cross-product never materializes.
"""

from __future__ import annotations

import pandas as pd

# FPDS Element 10Q codes that mark a contract as already-coded Phase III.
# Mirrors the constant in ``packages/sbir-analytics/.../phase_transition/phase_ii.py``;
# duplicated here intentionally to keep this filter self-contained and avoid a
# cross-package import for a five-character set.
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


def _normalize(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip().upper()
    return "" if s in {"", "NAN", "NONE"} else s


def _is_phase_iii_already_coded(row: pd.Series) -> bool:
    """True iff a contract row already carries explicit Phase III coding."""

    research = row.get("research") if "research" in row else None
    if isinstance(research, str) and research.strip().upper() in _PHASE_III_RESEARCH_CODES:
        return True

    sbir_phase = row.get("sbir_phase") if "sbir_phase" in row else None
    if sbir_phase is not None:
        label = _normalize(sbir_phase)
        if label.startswith("PHASE "):
            label_strip = label
        else:
            label_strip = label
        if label_strip in _PHASE_III_LABELS:
            return True
    return False


def _agency_match_level(prior: pd.Series, target: pd.Series) -> str | None:
    """Return the finest hierarchical agency match level present, or None.

    Levels (finest first): ``office`` > ``sub_tier`` > ``agency``. A row with
    no agreement at any tier returns None and is filtered out.
    """

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
    """Project & rename the prior-award frame to the canonical ``prior_*`` columns.

    Accepts the ``validated_phase_ii_awards`` shape (canonical) or any frame
    that carries the same column names — missing columns are filled with NaN.
    """

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


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    """Project & rename the contracts frame to the canonical ``target_*`` columns.

    Excludes rows already coded Phase III (research code SR3/ST3 or
    ``sbir_phase`` matching a Phase III label).
    """

    if contracts.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    df = contracts.copy()

    # Compute "already coded" mask before column projection so we can read
    # whichever raw column the input frame carries.
    coded_mask = df.apply(_is_phase_iii_already_coded, axis=1) if len(df) else pd.Series(
        [], dtype=bool
    )
    df = df.loc[~coded_mask].copy()
    if df.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

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
        }
    )
    out = out.loc[out["target_recipient_uei"].astype(str).str.strip() != ""].copy()
    out = out.loc[out["target_recipient_uei"].notna()].reset_index(drop=True)
    return out


def pair_filter_s1(
    prior_awards: pd.DataFrame,
    contracts: pd.DataFrame,
) -> pd.DataFrame:
    """S1 — Retrospective pair filter.

    Inner-joins prior Phase II awards to FPDS contracts on ``recipient_uei``
    and requires hierarchical agency agreement at the finest tier present
    (office > sub-tier > agency). Contracts already coded Phase III are
    excluded so we only surface miscoded candidates.

    Returns a DataFrame with the canonical ``PAIR_S1_COLUMNS``. Empty when
    either input lacks the join key or no agency level agrees.
    """

    priors = _prepare_priors(prior_awards)
    targets = _prepare_contracts(contracts)
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    # Normalize the join key so case/whitespace differences don't drop pairs.
    priors = priors.assign(_uei=priors["prior_recipient_uei"].map(_normalize))
    targets = targets.assign(_uei=targets["target_recipient_uei"].map(_normalize))
    priors = priors.loc[priors["_uei"] != ""].copy()
    targets = targets.loc[targets["_uei"] != ""].copy()
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    merged = priors.merge(targets, on="_uei", how="inner", suffixes=("", "_t"))
    if merged.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    # Apply the hierarchical agency gate row-wise.
    levels = merged.apply(
        lambda r: _agency_match_level(r, r),
        axis=1,
    )
    merged = merged.assign(agency_match_level=levels)
    merged = merged.loc[merged["agency_match_level"].notna()].copy()
    if merged.empty:
        return pd.DataFrame(columns=PAIR_S1_COLUMNS)

    merged = merged.drop(columns=["_uei"])
    return merged.loc[:, PAIR_S1_COLUMNS].reset_index(drop=True)


__all__ = [
    "PAIR_S1_COLUMNS",
    "pair_filter_s1",
]

"""Pair-filter functions for Phase III candidate signal classes."""

from __future__ import annotations

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


def _normalize(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip().upper()
    return "" if s in {"", "NAN", "NONE"} else s


# Columns that carry Phase III coding. If a non-empty contracts frame has NONE of these,
# the "already coded" exclusion cannot fire and would silently pass coded Phase IIIs through
# as flags — so we fail loudly instead (see _prepare_contracts).
_CODED_STATUS_COLUMNS: tuple[str, ...] = ("research", "sbir_phase")

# A precomputed, award-unique key if the ingestion provides one (preferred over any compound).
_UNIQUE_AWARD_KEY_COLUMNS: tuple[str, ...] = (
    "contract_award_unique_key",
    "generated_unique_award_id",
    "unique_award_key",
    "contract_id",
)
# Compound award-key parts (FPDS + FederalContract naming). Bare PIID alone is NOT a key:
# order numbers ("0001") recur across parent IDVs, PIIDs recur across mods, legacy PIIDs
# collide across agencies. The parent-IDV + agency parts disambiguate.
_PIID_COLUMNS: tuple[str, ...] = ("piid", "PIID", "award_id")
_AWARD_KEY_PART_COLUMNS: tuple[str, ...] = (
    "agencyID", "agency_id", "awarding_agency_code",
    "referencedIDVID", "referenced_idv_piid", "parent_contract_id", "parent_award_id",
    "referenced_idv_agency_id", "parent_contract_agency",
)


def _is_phase_iii_already_coded(row: pd.Series) -> bool:
    """True iff a contract row already carries explicit Phase III coding."""

    research = row.get("research") if "research" in row else None
    if isinstance(research, str) and research.strip().upper() in _PHASE_III_RESEARCH_CODES:
        return True

    sbir_phase = row.get("sbir_phase") if "sbir_phase" in row else None
    if sbir_phase is not None:
        label = _normalize(sbir_phase)
        if label in _PHASE_III_LABELS:
            return True
    return False


def award_key_series(df: pd.DataFrame) -> pd.Series:
    """Return an award-grade unique key per contract row.

    Preference: a precomputed unique award key, else a compound key
    (PIID + awarding agency + parent-IDV PIID + parent-IDV agency). Raises if only a bare
    PIID is available — bare PIID is not a key (recurs across IDVs/mods/agencies).
    """

    for col in _UNIQUE_AWARD_KEY_COLUMNS:
        if col in df.columns and df[col].astype(str).str.strip().replace("nan", "").ne("").any():
            return df[col].astype(str).str.strip()

    piid_col = next((c for c in _PIID_COLUMNS if c in df.columns), None)
    part_cols = [c for c in _AWARD_KEY_PART_COLUMNS if c in df.columns]
    if piid_col is None:
        raise ValueError(
            "contracts frame has no award-key column "
            f"(none of {_UNIQUE_AWARD_KEY_COLUMNS} or {_PIID_COLUMNS})"
        )
    if not part_cols:
        raise ValueError(
            f"bare PIID ({piid_col!r}) is not an award key: order numbers recur across parent "
            "IDVs, PIIDs recur across mods, legacy PIIDs collide across agencies. Provide a "
            f"unique award key {_UNIQUE_AWARD_KEY_COLUMNS} or compound parts {_AWARD_KEY_PART_COLUMNS}."
        )
    key_cols = [piid_col, *part_cols]
    return df[key_cols].fillna("").astype(str).agg("|".join, axis=1)


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


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    """Project & rename contracts frame to canonical ``target_*`` columns; excludes coded Phase III rows."""

    if contracts.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    df = contracts.copy()

    # Guard: if no coding column is present, the "already coded" exclusion silently passes
    # every coded Phase III through as a flag. For a report-bound audit that is a correctness
    # failure, not a soft default — fail loudly.
    if not any(c in df.columns for c in _CODED_STATUS_COLUMNS):
        raise ValueError(
            "contracts frame carries no Phase III coding column "
            f"(need one of {_CODED_STATUS_COLUMNS}); the already-coded exclusion cannot fire. "
            "USAspending-derived frames must be enriched with the FPDS 10Q 'research' element first."
        )

    # Award-grade unique key (never bare PIID). This is both target_id and the grain at which
    # coded-status is aggregated.
    df = df.assign(_award_key=award_key_series(df))

    # Coded status at AWARD grain: an award is coded if ANY of its transactions carries the
    # Phase III research code (conservative, agency-generous). Per-row masking would keep the
    # non-coded mods of an award that IS coded, manufacturing false flags.
    row_coded = (
        df.apply(_is_phase_iii_already_coded, axis=1) if len(df) else pd.Series([], dtype=bool)
    )
    award_coded = row_coded.groupby(df["_award_key"]).transform("any")
    df = df.loc[~award_coded].copy()
    if df.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    # Collapse to AWARD grain: one row per award key, so downstream flags are award-grade,
    # not transaction/mod-grade (which would multiply a single uncoded award into many flags).
    _date_col = next(
        (c for c in ("action_date", "award_date", "signedDate", "effectiveDate") if c in df.columns),
        None,
    )
    if _date_col is not None:
        df = df.assign(_d=pd.to_datetime(df[_date_col], errors="coerce")).sort_values(
            "_d", na_position="first"
        ).drop(columns="_d")
    df = df.drop_duplicates("_award_key", keep="last").copy()

    def _pick(*names: str) -> pd.Series:
        for n in names:
            if n in df.columns:
                return df[n]
        return pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame(
        {
            "target_id": df["_award_key"],
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
    """S1 retrospective filter: UEI inner-join + hierarchical agency gate; excludes coded Phase III."""

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
    levels = merged.apply(  # type: ignore[call-overload]
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

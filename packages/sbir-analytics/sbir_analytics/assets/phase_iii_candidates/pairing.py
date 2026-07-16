"""Pair-filter functions for Phase III candidate signal classes."""

from __future__ import annotations

import pandas as pd

from sbir_etl.utils.award_identity import (
    award_key_series,
    collapse_transactions_to_award_grain,
)

from .similarity import compute_topical_similarity

# FPDS Element 10Q codes that mark a contract as already-coded Phase III.
# Duplicated intentionally — avoids cross-package import for a five-element set.
_PHASE_III_RESEARCH_CODES = frozenset({"SR3", "ST3"})

# Tokens we accept as evidence that ``sbir_phase`` already says "Phase III".
_PHASE_III_LABELS = frozenset({"PHASE III", "III", "3", "PHASE 3"})

# If neither column exists, the already-coded exclusion cannot run safely.
_CODED_STATUS_COLUMNS: tuple[str, ...] = ("research", "sbir_phase")


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

PAIR_OPPORTUNITY_COLUMNS: list[str] = PAIR_S1_COLUMNS + [
    "target_notice_type",
    "target_response_deadline",
    "target_source_url",
    "target_active",
    "topical_similarity",
]

DIRECTED_NOTICE_TYPES = frozenset({"u", "s", "p"})
FOLLOWON_NOTICE_TYPES = frozenset({"o", "k", "r", "p"})
_LINEAGE_TERMS = (
    "phase iii",
    "phase 3",
    "derives from",
    "prototype transition",
    "follow-on production",
    "continuation of",
    "sole source",
    "notice of intent",
)


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


def _prepare_contracts(contracts: pd.DataFrame) -> pd.DataFrame:
    """Project & rename contracts frame to canonical ``target_*`` columns; excludes coded Phase III rows."""

    if contracts.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    df = contracts.copy()

    if not any(column in df.columns for column in _CODED_STATUS_COLUMNS):
        raise ValueError(
            "contracts frame carries no Phase III coding column "
            f"(need one of {_CODED_STATUS_COLUMNS}); the already-coded exclusion cannot run"
        )

    # Code status is an award-level property. If any transaction is explicitly
    # Phase III, exclude every transaction for that award.
    df = df.assign(_award_key=award_key_series(df))
    row_coded = (
        df.apply(_is_phase_iii_already_coded, axis=1) if len(df) else pd.Series([], dtype=bool)
    )
    award_coded = row_coded.groupby(df["_award_key"], sort=False).transform("any")
    df = df.loc[~award_coded].copy()
    if df.empty:
        return pd.DataFrame(columns=[c for c in PAIR_S1_COLUMNS if c.startswith("target_")])

    # One representative row per award. The shared helper documents that this
    # selects the latest transaction and does not aggregate financial fields.
    df = collapse_transactions_to_award_grain(df, award_keys=df["_award_key"])

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


def _prepare_opportunities(opportunities: pd.DataFrame) -> pd.DataFrame:
    if opportunities.empty:
        return pd.DataFrame(
            columns=[c for c in PAIR_OPPORTUNITY_COLUMNS if c.startswith("target_")]
        )
    df = opportunities.copy()

    def _pick(*names: str) -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([None] * len(df), index=df.index)

    out = pd.DataFrame(
        {
            "target_id": _pick("notice_id", "noticeId"),
            "target_recipient_uei": _pick("awardee_uei", "ueiSAM"),
            "target_agency": _pick("agency", "department"),
            "target_sub_agency": _pick("sub_tier", "subTier"),
            "target_office": _pick("office"),
            "target_naics_code": _pick("naics_code", "naicsCode"),
            "target_psc_code": _pick("psc_code", "classification_code"),
            "target_description": _pick("description", "title"),
            "target_action_date": _pick("posted_date", "postedDate"),
            "target_competition_type": _pick("notice_type_code", "notice_type"),
            "target_obligated_amount": pd.Series([None] * len(df), index=df.index),
            "target_notice_type": _pick("notice_type_code", "notice_type"),
            "target_response_deadline": _pick("response_deadline", "responseDeadLine"),
            "target_source_url": _pick("source_url", "ui_url", "uiLink"),
            "target_active": _pick("active"),
        }
    )
    out["target_notice_type"] = out["target_notice_type"].map(_normalize).str.lower()
    active = out["target_active"].map(
        lambda value: value is True or _normalize(value) in {"YES", "TRUE", "1", "ACTIVE"}
    )
    deadline = pd.to_datetime(out["target_response_deadline"], errors="coerce", utc=True)
    today = pd.Timestamp.now(tz="UTC").normalize()
    live_deadline = deadline.isna() | (deadline >= today)
    return out.loc[active & live_deadline & out["target_id"].notna()].reset_index(drop=True)


def _with_pair_metadata(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)
    levels = merged.apply(  # type: ignore[call-overload]
        lambda row: _agency_match_level(row, row),
        axis=1,
    )
    merged = merged.assign(agency_match_level=levels)
    merged = merged.loc[merged["agency_match_level"].notna()].copy()
    if merged.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)
    merged["topical_similarity"] = merged.apply(
        lambda row: compute_topical_similarity(
            {
                "naics_code": row.get("prior_naics_code"),
                "psc_code": row.get("prior_psc_code"),
                "title": row.get("prior_title"),
                "abstract": row.get("prior_abstract"),
            },
            {
                "naics_code": row.get("target_naics_code"),
                "psc_code": row.get("target_psc_code"),
                "description": row.get("target_description"),
            },
        ),
        axis=1,
    )
    return merged.loc[:, PAIR_OPPORTUNITY_COLUMNS].reset_index(drop=True)


def pair_filter_s2(prior_awards: pd.DataFrame, opportunities: pd.DataFrame) -> pd.DataFrame:
    """Directed candidates: active u/s/p notices with UEI or strong lineage fallback."""

    priors = _prepare_priors(prior_awards)
    targets = _prepare_opportunities(opportunities)
    targets = targets.loc[targets["target_notice_type"].isin(DIRECTED_NOTICE_TYPES)].copy()
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)

    priors["_uei"] = priors["prior_recipient_uei"].map(_normalize)
    targets["_uei"] = targets["target_recipient_uei"].map(_normalize)
    exact = priors.merge(targets.loc[targets["_uei"] != ""], on="_uei", how="inner")

    no_uei = targets.loc[targets["_uei"] == ""].copy()
    fallback = pd.DataFrame()
    if not no_uei.empty:
        priors["_agency"] = priors["prior_agency"].map(_normalize)
        no_uei["_agency"] = no_uei["target_agency"].map(_normalize)
        fallback = priors.merge(no_uei, on="_agency", how="inner")
        lineage = (
            fallback["target_description"]
            .fillna("")
            .str.lower()
            .map(lambda text: any(term in text for term in _LINEAGE_TERMS))
        )
        naics = fallback["prior_naics_code"].map(_normalize) == fallback["target_naics_code"].map(
            _normalize
        )
        missing_codes = (fallback["prior_naics_code"].map(_normalize) == "") | (
            fallback["target_naics_code"].map(_normalize) == ""
        )
        fallback = fallback.loc[lineage & (naics | missing_codes)].copy()
    merged = pd.concat([exact, fallback], ignore_index=True, sort=False)
    return _with_pair_metadata(merged.drop_duplicates(["prior_award_id", "target_id"]))


def pair_filter_s3(prior_awards: pd.DataFrame, opportunities: pd.DataFrame) -> pd.DataFrame:
    """Competitive follow-on candidates gated by codes and topical similarity."""

    priors = _prepare_priors(prior_awards)
    targets = _prepare_opportunities(opportunities)
    targets = targets.loc[targets["target_notice_type"].isin(FOLLOWON_NOTICE_TYPES)].copy()
    if priors.empty or targets.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)

    parts: list[pd.DataFrame] = []
    for prior_key, target_key in (
        ("prior_naics_code", "target_naics_code"),
        ("prior_psc_code", "target_psc_code"),
    ):
        left = priors.assign(_code=priors[prior_key].map(_normalize))
        right = targets.assign(_code=targets[target_key].map(_normalize))
        parts.append(
            left.loc[left["_code"] != ""].merge(right.loc[right["_code"] != ""], on="_code")
        )
    # SBIR.gov does not publish NAICS/PSC on every award. For those rows, use
    # agency as a bounded fallback and retain only pairs that pass topical similarity.
    missing = priors.loc[
        (priors["prior_naics_code"].map(_normalize) == "")
        & (priors["prior_psc_code"].map(_normalize) == "")
    ].copy()
    if not missing.empty:
        missing["_agency"] = missing["prior_agency"].map(_normalize)
        by_agency = targets.assign(_agency=targets["target_agency"].map(_normalize))
        parts.append(missing.loc[missing["_agency"] != ""].merge(by_agency, on="_agency"))
    merged = pd.concat(parts, ignore_index=True, sort=False).drop_duplicates(
        ["prior_award_id", "target_id"]
    )
    paired = _with_pair_metadata(merged)
    return paired.loc[paired["topical_similarity"] >= 0.10].reset_index(drop=True)


__all__ = [
    "DIRECTED_NOTICE_TYPES",
    "FOLLOWON_NOTICE_TYPES",
    "PAIR_OPPORTUNITY_COLUMNS",
    "PAIR_S1_COLUMNS",
    "pair_filter_s1",
    "pair_filter_s2",
    "pair_filter_s3",
]

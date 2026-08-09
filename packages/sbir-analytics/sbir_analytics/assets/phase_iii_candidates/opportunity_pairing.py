"""Opportunity-side Phase III candidate pairing with topical scoring.

Epistemic tier: exploratory. S2/S3 opportunity pairing weighs TF-IDF text and
code similarity to rank live SAM.gov notices against prior awards — contestable
ranking, not the label-free census join. It is split out of ``pairing`` (which
carries a per-file pipelines label for the census-facing ``build_uei_pairs``
boundary) so that pipelines module never imports the exploratory scorer, even
lazily (spec epistemic-tier-enforcement, T1.2 edge 4). Deterministic helpers are
reused from ``pairing`` rather than forked.
"""

from __future__ import annotations

import pandas as pd

from sbir_etl.utils.procurement_text import DIRECTED_LINEAGE_TERMS

from .pairing import (
    PAIR_S1_COLUMNS,
    _normalize,
    _prepare_priors,
    _prior_identity,
)
from .similarity import compute_text_similarity_batch, compute_topical_similarity


EPISTEMIC_TIER = "exploratory"


PAIR_OPPORTUNITY_COLUMNS: list[str] = PAIR_S1_COLUMNS + [
    "target_notice_type",
    "target_response_deadline",
    "target_source_url",
    "target_active",
    "topical_similarity",
]

# SAM.gov notice-type codes, partitioned so every notice lands in exactly one
# corpus. Directed = the agency has named an intended recipient or its intent to
# award without full competition (Justification/J&A ``u``, Special Notice ``s``,
# Award Notice ``a``). Follow-on = the agency is soliciting competitively
# (Solicitation ``o``, Combined Synopsis ``k``, Sources Sought ``r``,
# Pre-solicitation ``p`` — a forthcoming competitive action, not a directed one).
# Disjointness is asserted below: overlapping sets would let one notice become
# two contradictory candidates for the same prior award, rendered and counted twice.
DIRECTED_NOTICE_TYPES = frozenset({"u", "s", "a"})
FOLLOWON_NOTICE_TYPES = frozenset({"o", "k", "r", "p"})

if DIRECTED_NOTICE_TYPES & FOLLOWON_NOTICE_TYPES:  # pragma: no cover - import guard
    raise ValueError(
        "DIRECTED_NOTICE_TYPES and FOLLOWON_NOTICE_TYPES must be disjoint; overlap: "
        f"{sorted(DIRECTED_NOTICE_TYPES & FOLLOWON_NOTICE_TYPES)}"
    )


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
    # A blank notice id is not an identifier: such rows collide with each other on
    # dedupe and render as a candidate nobody can look up. Require a real value.
    has_id = out["target_id"].map(_normalize) != ""
    return out.loc[active & live_deadline & has_id].reset_index(drop=True)


def _with_pair_metadata(merged: pd.DataFrame) -> pd.DataFrame:
    """Annotate opportunity pairs with agency level, temporal sanity, and topicality.

    The agency level is recorded as *evidence*, not applied as a gate: the
    structural gate is signal-class specific and already lives in each filter's
    join keys (exact UEI for S2, exact NAICS/PSC for S3, agency only on the
    bounded fallback paths). Gating here would drop cross-agency exact-identity
    and exact-code matches, which are the strongest signals the pipeline has.
    """

    if merged.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)

    levels = merged.apply(  # type: ignore[call-overload]
        lambda row: _agency_match_level(row, row),
        axis=1,
    )
    merged = merged.assign(agency_match_level=levels)
    # Temporal sanity: a notice posted before the prior award began cannot be its
    # follow-on (transition-ranker "after_first" floor). Unknown dates on either
    # side stay neutral — no false exclusions on missing data.
    posted = pd.to_datetime(merged["target_action_date"], errors="coerce", utc=True)
    awarded = pd.to_datetime(merged["prior_award_date"], errors="coerce", utc=True)
    impossible = posted.notna() & awarded.notna() & (posted < awarded)
    merged = merged.loc[~impossible].copy()
    if merged.empty:
        return pd.DataFrame(columns=PAIR_OPPORTUNITY_COLUMNS)
    # One corpus-fitted TF-IDF pass over the whole frame, then combine with codes per row.
    text_similarities = compute_text_similarity_batch(merged)
    merged["topical_similarity"] = [
        compute_topical_similarity(
            {
                "naics_code": row.get("prior_naics_code"),
                "psc_code": row.get("prior_psc_code"),
            },
            {
                "naics_code": row.get("target_naics_code"),
                "psc_code": row.get("target_psc_code"),
            },
            text_similarity=text_similarity,
        )
        for (_, row), text_similarity in zip(merged.iterrows(), text_similarities, strict=True)
    ]
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
            .map(lambda text: any(term in text for term in DIRECTED_LINEAGE_TERMS))
        )
        naics = fallback["prior_naics_code"].map(_normalize) == fallback["target_naics_code"].map(
            _normalize
        )
        missing_codes = (fallback["prior_naics_code"].map(_normalize) == "") | (
            fallback["target_naics_code"].map(_normalize) == ""
        )
        fallback = fallback.loc[lineage & (naics | missing_codes)].copy()
    merged = pd.concat([exact, fallback], ignore_index=True, sort=False)
    merged = merged.assign(_prior_identity=_prior_identity(merged)).drop_duplicates(
        ["_prior_identity", "target_id"]
    )
    return _with_pair_metadata(merged.drop(columns="_prior_identity"))


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
    merged = pd.concat(parts, ignore_index=True, sort=False)
    merged = merged.assign(_prior_identity=_prior_identity(merged)).drop_duplicates(
        ["_prior_identity", "target_id"]
    )
    merged = merged.drop(columns="_prior_identity")
    paired = _with_pair_metadata(merged)
    return paired.loc[paired["topical_similarity"] >= 0.10].reset_index(drop=True)


__all__ = [
    "DIRECTED_NOTICE_TYPES",
    "FOLLOWON_NOTICE_TYPES",
    "PAIR_OPPORTUNITY_COLUMNS",
    "pair_filter_s2",
    "pair_filter_s3",
]

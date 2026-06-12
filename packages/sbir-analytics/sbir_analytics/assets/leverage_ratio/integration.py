"""Adapters from production-shaped SBIR, entity-resolution, and USAspending frames."""

from __future__ import annotations

import pandas as pd

from .analysis import CANONICAL_COLUMNS


def _pick(frame: pd.DataFrame, *names: str, default=None) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name]
    return pd.Series(default, index=frame.index)


def _norm(value: object) -> str | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip().upper()


def build_canonical_obligations(
    sbir_awards: pd.DataFrame,
    entity_matches: pd.DataFrame,
    usaspending_transactions: pd.DataFrame,
) -> pd.DataFrame:
    """Join existing pipeline outputs into the canonical transaction-level analysis input."""

    awards = pd.DataFrame(
        {
            "company_id": _pick(
                sbir_awards, "company_id", "Company", "company_name", "recipient_name"
            ).map(_norm),
            "recipient_uei": _pick(sbir_awards, "recipient_uei", "uei", "UEI").map(_norm),
            "award_id": _pick(sbir_awards, "award_id", "Award ID", "contract", "piid").map(_norm),
            "award_year": pd.to_numeric(
                _pick(sbir_awards, "fiscal_year", "award_year", "Award Year"), errors="coerce"
            ),
            "firm_size": _pick(sbir_awards, "firm_size", default="unknown").fillna("unknown"),
            "technology_area": _pick(
                sbir_awards, "technology_area", "cet_area", default="unknown"
            ).fillna("unknown"),
        }
    )
    awards = awards[awards["company_id"].notna()].copy()
    profiles = (
        awards.groupby("company_id", dropna=False)
        .agg(
            cohort_year=("award_year", "min"),
            firm_size=("firm_size", "first"),
            technology_area=("technology_area", "first"),
            prior_sbir_award_count=("award_id", "nunique"),
        )
        .reset_index()
    )
    profiles["experience"] = profiles["prior_sbir_award_count"].map(
        lambda n: "experienced" if n > 1 else "new"
    )

    matches = pd.DataFrame(
        {
            "company_id": _pick(
                entity_matches, "company_id", "source_company_id", "company_name"
            ).map(_norm),
            "recipient_uei": _pick(entity_matches, "recipient_uei", "matched_uei", "uei").map(
                _norm
            ),
            "match_confidence": pd.to_numeric(
                _pick(
                    entity_matches, "match_confidence", "match_score", "_usaspending_match_score"
                ),
                errors="coerce",
            ),
        }
    ).dropna(subset=["recipient_uei"])
    # Existing enrichment outputs contain both 0-1 and 0-100 score conventions.
    matches.loc[matches["match_confidence"] > 1, "match_confidence"] /= 100
    direct = awards[["company_id", "recipient_uei"]].dropna().assign(match_confidence=1.0)
    matches = (
        pd.concat([matches, direct], ignore_index=True)
        .sort_values("match_confidence", ascending=False)
        .drop_duplicates("recipient_uei")
    )

    tx = usaspending_transactions.copy()
    canonical = pd.DataFrame(
        {
            "obligation_id": _pick(
                tx,
                "obligation_id",
                "transaction_unique_id",
                "generated_unique_award_id",
                "award_id",
                "piid",
            ),
            "recipient_uei": _pick(tx, "recipient_uei", "vendor_uei", "uei").map(_norm),
            "agency": _pick(tx, "agency", "awarding_agency_code", "awarding_agency_name"),
            "fiscal_year": pd.to_numeric(
                _pick(tx, "fiscal_year", "action_date_fiscal_year", "award_year"), errors="coerce"
            ).astype("Int64"),
            "obligation_amount": pd.to_numeric(
                _pick(
                    tx,
                    "federal_action_obligation",
                    "obligation_amount",
                    "obligated_amount",
                    "award_amount",
                ),
                errors="coerce",
            ),
            "award_id": _pick(tx, "award_id", "generated_unique_award_id", "piid", "fain").map(
                _norm
            ),
            "program": _pick(tx, "program", "program_type", default=""),
        }
    )
    explicit = (
        _pick(tx, "is_sbir", "sbir_gov_confirmed", default=False)
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"true", "1", "yes", "y"})
    )
    known_awards = set(awards["award_id"].dropna())
    aln_confidence = (
        _pick(tx, "sbir_aln_confidence", default="")
        .astype(str)
        .str.lower()
        .isin({"exclusive", "shared_confirmed"})
    )
    canonical["is_sbir"] = (
        explicit
        | canonical["award_id"].isin(known_awards)
        | aln_confidence
        | canonical["program"].astype(str).str.upper().isin({"SBIR", "STTR"})
    )
    canonical = canonical.merge(
        matches, on="recipient_uei", how="left", validate="many_to_one"
    ).merge(profiles, on="company_id", how="left", validate="many_to_one")
    canonical["firm_size"] = canonical["firm_size"].fillna("unknown")
    canonical["technology_area"] = canonical["technology_area"].fillna("unknown")
    canonical["experience"] = canonical["experience"].fillna("unknown")
    return canonical[[*CANONICAL_COLUMNS, "program"]]

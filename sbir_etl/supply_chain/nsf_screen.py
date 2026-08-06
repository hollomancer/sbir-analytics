"""Screen NSF SBIR supplier candidates against existing CET policy mappings.

Epistemic tier: exploratory. Rule-based CET screening decides contestable
technology relevance, so emitted review candidates are non-citable.
"""

from __future__ import annotations

import json

import pandas as pd

from sbir_etl.reporting.defense_taxonomy_crosswalk import (
    DefenseTaxonomyCrosswalk,
    load_defense_crosswalk,
)
from sbir_etl.reporting.local_cet_classifier import (
    LocalCETRuleClassifier,
    load_local_cet_rule_classifier,
)


EPISTEMIC_TIER = "exploratory"


def screen_direct_nsf_awards(
    direct_awards: pd.DataFrame,
    *,
    funded_organization_ids: set[str] | None = None,
    classifier: LocalCETRuleClassifier | None = None,
) -> pd.DataFrame:
    """Screen direct NSF award text with CET rules and observed DoD funding.

    The screen intentionally does not emit DoD-14 or NDIS-8 policy mappings.  No
    authoritative repository mapping exists for those frameworks, so the output
    records that policy mapping as deferred and never promotes criticality beyond
    a review candidate.
    """

    required = {
        "nsf_award_id",
        "nsf_organization_id",
        "nsf_award_title",
        "nsf_award_abstract",
    }
    if missing := sorted(required - set(direct_awards.columns)):
        raise ValueError(f"direct NSF awards are missing screening columns: {missing}")
    if direct_awards["nsf_award_id"].duplicated().any():
        raise ValueError("direct NSF award IDs must be unique for screening")
    local_classifier = classifier or load_local_cet_rule_classifier()
    topic_parts = [
        direct_awards[column].fillna("").astype(str)
        for column in (
            "nsf_fund_program_name",
            "nsf_program_element_codes_json",
            "nsf_program_reference_codes_json",
        )
        if column in direct_awards.columns
    ]
    topic = (
        pd.concat(topic_parts, axis=1).agg(" ".join, axis=1).str.strip()
        if topic_parts
        else pd.Series("", index=direct_awards.index, dtype="object")
    )
    classifier_input = pd.DataFrame(
        {
            "award_id": direct_awards["nsf_award_id"].astype(str),
            "title": direct_awards["nsf_award_title"],
            "topic_code": topic,
            "abstract": direct_awards["nsf_award_abstract"],
        }
    )
    classifications = local_classifier.classify_frame(classifier_input)
    if classifications.empty:
        classifications = pd.DataFrame(
            columns=[
                "award_id",
                "primary_cet",
                "primary_score",
                "supporting_cets",
                "evidence",
                "taxonomy_version",
                "classifier_version",
            ]
        )
    classifications["supporting_cets"] = classifications["supporting_cets"].map(
        lambda value: json.dumps(value, separators=(",", ":"))
    )
    classifications["cet_evidence"] = classifications.pop("evidence").map(
        lambda value: json.dumps(value, separators=(",", ":"))
    )
    classifications = classifications.rename(
        columns={
            "award_id": "nsf_award_id",
            "primary_score": "primary_cet_score",
            "taxonomy_version": "cet_taxonomy_version",
            "classifier_version": "cet_classifier_version",
        }
    )
    columns = [
        "nsf_award_id",
        "nsf_organization_id",
        "nsf_program",
        "nsf_phase",
        "nsf_award_title",
        "nsf_award_abstract",
        "nsf_award_performance_status",
        "analysis_date",
        "source_url",
        "source_path",
        "source_record_sha256",
    ]
    awards = direct_awards.copy()
    for column in columns:
        if column not in awards.columns:
            awards[column] = pd.NA
    screened = awards[columns].merge(
        classifications,
        on="nsf_award_id",
        how="left",
        validate="one_to_one",
    )
    screened["cet_taxonomy_version"] = screened["cet_taxonomy_version"].fillna(
        local_classifier.taxonomy_version
    )
    screened["cet_classifier_version"] = screened["cet_classifier_version"].fillna(
        local_classifier.version
    )
    screened["supporting_cets"] = screened["supporting_cets"].fillna("[]")
    screened["cet_evidence"] = screened["cet_evidence"].fillna("[]")
    funded = funded_organization_ids or set()
    screened["verified_dod_funding_observed"] = screened["nsf_organization_id"].isin(funded)
    classified = screened["primary_cet"].notna()
    screened["critical_supply_chain_review_candidate"] = (
        classified & screened["verified_dod_funding_observed"]
    )
    screened["critical_supply_chain_screen_basis"] = "no_positive_screen"
    screened.loc[classified, "critical_supply_chain_screen_basis"] = "cet_text_screen_only"
    screened.loc[
        screened["verified_dod_funding_observed"], "critical_supply_chain_screen_basis"
    ] = "observed_dod_funding_only"
    screened.loc[
        screened["critical_supply_chain_review_candidate"],
        "critical_supply_chain_screen_basis",
    ] = "observed_dod_funding_plus_cet_text_screen"
    screened["critical_supply_chain_status"] = "not_assessed"
    screened["specific_award_usage_status"] = "not_established"
    screened["defense_policy_mapping_status"] = "deferred_no_authoritative_dod14_or_ndis8_mapping"
    screened["defense_policy_mapping_version"] = pd.NA
    screened["screen_interpretation"] = (
        "CET text and legal-entity funding support review only; criticality and use of the "
        "specific NSF award are not established"
    )
    return screened.sort_values("nsf_award_id").reset_index(drop=True)


def screen_nsf_sbir_award_candidates(
    candidates: pd.DataFrame,
    *,
    classifier: LocalCETRuleClassifier | None = None,
    crosswalk: DefenseTaxonomyCrosswalk | None = None,
) -> pd.DataFrame:
    """Add auditable CET and defense-supply-chain screening fields.

    A positive screen combines an observed supplier relationship with a primary
    CET classification that maps to the repository's defense supply-chain
    framework. It remains a review candidate, not a criticality determination.
    """
    required = {
        "nsf_sbir_award_candidate_id",
        "nsf_sbir_award_title",
        "nsf_sbir_topic_code",
        "nsf_sbir_abstract",
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise ValueError(f"NSF SBIR award candidates are missing required columns: {missing}")

    local_classifier = classifier or load_local_cet_rule_classifier()
    defense_crosswalk = crosswalk or load_defense_crosswalk()
    classifier_input = candidates[
        [
            "nsf_sbir_award_candidate_id",
            "nsf_sbir_award_title",
            "nsf_sbir_topic_code",
            "nsf_sbir_abstract",
        ]
    ].rename(
        columns={
            "nsf_sbir_award_candidate_id": "award_id",
            "nsf_sbir_award_title": "title",
            "nsf_sbir_topic_code": "topic_code",
            "nsf_sbir_abstract": "abstract",
        }
    )
    classifications = local_classifier.classify_frame(classifier_input)
    if classifications.empty:
        classifications = pd.DataFrame(
            columns=[
                "award_id",
                "primary_cet",
                "primary_score",
                "supporting_cets",
                "evidence",
                "taxonomy_version",
                "classifier_version",
            ]
        )
    classifications["dod_supply_chain_categories"] = classifications["primary_cet"].map(
        lambda cet_id: "|".join(defense_crosswalk.targets_for(str(cet_id), "dod_sc8"))
    )
    classifications["dod_supply_chain_mapping_details"] = classifications["primary_cet"].map(
        lambda cet_id: json.dumps(
            defense_crosswalk.mapping_details(str(cet_id), "dod_sc8"), separators=(",", ":")
        )
    )
    classifications["supporting_cets"] = classifications["supporting_cets"].map(
        lambda value: json.dumps(value, separators=(",", ":"))
    )
    classifications["cet_evidence"] = classifications.pop("evidence").map(
        lambda value: json.dumps(value, separators=(",", ":"))
    )
    classifications = classifications.rename(
        columns={
            "award_id": "nsf_sbir_award_candidate_id",
            "primary_score": "primary_cet_score",
            "taxonomy_version": "cet_taxonomy_version",
            "classifier_version": "cet_classifier_version",
        }
    )
    screened = candidates.merge(
        classifications,
        on="nsf_sbir_award_candidate_id",
        how="left",
        validate="one_to_one",
    )
    mapped = screened["dod_supply_chain_categories"].fillna("").ne("")
    screened["critical_supply_chain_review_candidate"] = mapped
    screened["critical_supply_chain_screen_basis"] = "observed_supplier_relationship_only"
    screened.loc[mapped, "critical_supply_chain_screen_basis"] = (
        "observed_supplier_relationship_plus_primary_cet_crosswalk"
    )
    screened["critical_supply_chain_status"] = "not_assessed"
    screened["defense_crosswalk_version"] = defense_crosswalk.version
    screened["defense_supply_chain_taxonomy_version"] = defense_crosswalk.target_versions["dod_sc8"]
    return screened


def aggregate_nsf_supplier_screen(screened_awards: pd.DataFrame) -> pd.DataFrame:
    """Roll specific-award screens up to one auditable row per supplier."""
    required = {
        "sbir_organization_id",
        "primary_cet",
        "dod_supply_chain_categories",
        "critical_supply_chain_review_candidate",
    }
    missing = sorted(required - set(screened_awards.columns))
    if missing:
        raise ValueError(f"screened NSF awards are missing required columns: {missing}")
    if screened_awards.empty:
        return pd.DataFrame()

    def joined_tokens(values: pd.Series) -> str:
        tokens = {
            token.strip()
            for value in values.dropna().astype(str)
            for token in value.split("|")
            if token.strip()
        }
        return "|".join(sorted(tokens))

    working = screened_awards.copy()
    working["cet_classified"] = working["primary_cet"].notna()
    return (
        working.groupby("sbir_organization_id", as_index=False)
        .agg(
            nsf_specific_award_candidate_count=("nsf_sbir_award_candidate_id", "nunique"),
            cet_classified_nsf_award_count=("cet_classified", "sum"),
            critical_supply_chain_candidate_award_count=(
                "critical_supply_chain_review_candidate",
                "sum",
            ),
            primary_cets=("primary_cet", joined_tokens),
            dod_supply_chain_categories=("dod_supply_chain_categories", joined_tokens),
            critical_supply_chain_review_candidate=(
                "critical_supply_chain_review_candidate",
                "max",
            ),
            cet_classifier_version=("cet_classifier_version", "first"),
            defense_crosswalk_version=("defense_crosswalk_version", "first"),
        )
        .sort_values(
            [
                "critical_supply_chain_review_candidate",
                "critical_supply_chain_candidate_award_count",
            ],
            ascending=False,
        )
    )


__all__ = [
    "aggregate_nsf_supplier_screen",
    "screen_direct_nsf_awards",
    "screen_nsf_sbir_award_candidates",
]

"""Screen NSF SBIR supplier candidates against existing CET policy mappings."""

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


__all__ = ["aggregate_nsf_supplier_screen", "screen_nsf_sbir_award_candidates"]

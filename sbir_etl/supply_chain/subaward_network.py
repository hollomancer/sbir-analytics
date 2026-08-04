"""Build observed SBIR-awardee-to-DoD-prime relationships from federal subawards.

USAspending calls these records first-tier subawards. In a DIB-oriented tier
convention, the DoD prime is Tier 1 and its reported subcontractor is Tier 2.
The records do not expose suppliers to that subcontractor and therefore cannot
establish Tier 3+ relationships.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, cast

import pandas as pd

from sbir_etl.utils.text_normalization import normalize_name


class MatchMethod(StrEnum):
    """How a subawardee was linked to an SBIR awardee."""

    UEI = "exact_uei"
    DUNS = "exact_duns"
    NORMALIZED_NAME = "exact_normalized_name"


class EvidenceGrade(StrEnum):
    """Evidence strength for an observed supplier-prime relationship."""

    VERIFIED_IDENTIFIER = "verified_identifier"
    CANDIDATE_NAME = "candidate_name"


_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_NULL_IDENTIFIERS = {
    "NA",
    "NAN",
    "NAT",
    "NONE",
    "NOTAPPLICABLE",
    "NOTAVAILABLE",
    "NULL",
    "UNAVAILABLE",
    "UNKNOWN",
}


def _clean_identifier(value: object) -> str | None:
    if value is None or pd.isna(cast(Any, value)):
        return None
    cleaned = _NON_ALNUM.sub("", str(value).upper())
    if not cleaned or cleaned in _NULL_IDENTIFIERS or not cleaned.strip("0"):
        return None
    return cleaned


def _clean_name(value: object) -> str | None:
    if value is None or pd.isna(cast(Any, value)):
        return None
    cleaned = normalize_name(str(value), remove_suffixes=True)
    return cleaned if len(cleaned) >= 4 else None


def _clean_category(value: object) -> str | None:
    if value is None or pd.isna(cast(Any, value)):
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    return cleaned or None


def _is_nsf(value: object) -> bool:
    cleaned = _clean_category(value)
    if not cleaned:
        return False
    return cleaned.upper() in {"NSF", "NATIONAL SCIENCE FOUNDATION"}


def _joined_unique(values: pd.Series) -> str:
    cleaned = {_clean_category(value) for value in values}
    return "|".join(sorted(value for value in cleaned if value))


def _first_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    for column in aliases:
        if column in frame.columns:
            return frame[column]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _unique_mapping(frame: pd.DataFrame, key: str, value: str) -> dict[str, str]:
    usable = frame.dropna(subset=[key, value])[[key, value]].drop_duplicates()
    unambiguous = usable.groupby(key)[value].nunique()
    allowed = set(unambiguous[unambiguous == 1].index)
    return (
        usable.loc[usable[key].isin(allowed)]
        .drop_duplicates(key)
        .set_index(key)[value]
        .astype(str)
        .to_dict()
    )


def build_sbir_awardee_registry(awards: pd.DataFrame) -> pd.DataFrame:
    """Build one identifier-bearing registry row per observed SBIR organization."""
    names = _first_column(awards, ("company_name", "organization_name", "firm_name", "Company"))
    ueis = _first_column(awards, ("company_uei", "uei", "recipient_uei", "UEI"))
    duns = _first_column(awards, ("company_duns", "duns", "recipient_duns", "Duns"))
    agencies = _first_column(awards, ("agency", "funding_agency", "Agency"))
    programs = _first_column(awards, ("program", "Program"))
    topic_codes = _first_column(awards, ("topic_code", "Topic Code"))
    award_years = pd.to_numeric(
        _first_column(awards, ("award_year", "Award Year")), errors="coerce"
    )
    award_amounts = pd.to_numeric(
        _first_column(awards, ("award_amount", "Award Amount")), errors="coerce"
    ).fillna(0.0)
    nsf_awards = agencies.map(_is_nsf)
    nsf_sbir_awards = nsf_awards & programs.map(_clean_category).str.upper().eq("SBIR")
    nsf_sttr_awards = nsf_awards & programs.map(_clean_category).str.upper().eq("STTR")
    registry = pd.DataFrame(
        {
            "sbir_awardee_name": names,
            "sbir_uei": ueis.map(_clean_identifier),
            "sbir_duns": duns.map(_clean_identifier),
            "normalized_name": names.map(_clean_name),
            "funding_agency": agencies.map(_clean_category),
            "nsf_sbir_award_increment": nsf_sbir_awards.astype(int),
            "nsf_sttr_award_increment": nsf_sttr_awards.astype(int),
            "nsf_sbir_topic_code": topic_codes.where(nsf_sbir_awards),
            "nsf_sbir_award_year": award_years.where(nsf_sbir_awards),
            "nsf_sbir_award_amount_increment": award_amounts.where(nsf_sbir_awards, 0.0),
        }
    )
    registry = registry.dropna(subset=["normalized_name", "sbir_uei", "sbir_duns"], how="all")
    registry["sbir_organization_id"] = (
        registry["sbir_uei"]
        .map(lambda value: f"uei:{value}" if value else None)
        .fillna(registry["sbir_duns"].map(lambda value: f"duns:{value}" if value else None))
        .fillna(registry["normalized_name"].map(lambda value: f"name:{value}" if value else None))
    )
    registry["sbir_award_count"] = 1
    registry = (
        registry.groupby("sbir_organization_id", as_index=False)
        .agg(
            sbir_awardee_name=("sbir_awardee_name", "first"),
            sbir_uei=("sbir_uei", "first"),
            sbir_duns=("sbir_duns", "first"),
            normalized_name=("normalized_name", "first"),
            sbir_award_count=("sbir_award_count", "sum"),
            sbir_funding_agency_count=("funding_agency", "nunique"),
            nsf_sbir_award_count=("nsf_sbir_award_increment", "sum"),
            nsf_sttr_award_count=("nsf_sttr_award_increment", "sum"),
            nsf_sbir_topic_codes=("nsf_sbir_topic_code", _joined_unique),
            nsf_sbir_first_award_year=("nsf_sbir_award_year", "min"),
            nsf_sbir_latest_award_year=("nsf_sbir_award_year", "max"),
            nsf_sbir_award_amount=("nsf_sbir_award_amount_increment", "sum"),
        )
        .sort_values("sbir_organization_id")
        .reset_index(drop=True)
    )
    registry["nsf_sbir_awardee"] = registry["nsf_sbir_award_count"].gt(0)
    return registry


def build_nsf_sbir_award_candidates(
    awards: pd.DataFrame,
    awardees: pd.DataFrame,
    supplier_exposure: pd.DataFrame,
) -> pd.DataFrame:
    """Attach specific NSF SBIR awards to identifier-verified supplier candidates.

    The observed DoD relationship exists at the organization level. A row in this
    output does not establish that the NSF-funded work was used on the subcontract.
    """
    required_awardee_columns = {
        "sbir_organization_id",
        "sbir_uei",
        "sbir_duns",
        "normalized_name",
    }
    missing = sorted(required_awardee_columns - set(awardees.columns))
    if missing:
        raise ValueError(f"awardee registry is missing required columns: {missing}")
    if "sbir_organization_id" not in supplier_exposure.columns:
        raise ValueError("supplier exposure is missing required column: sbir_organization_id")

    names = _first_column(awards, ("company_name", "organization_name", "firm_name", "Company"))
    agencies = _first_column(awards, ("agency", "funding_agency", "Agency"))
    programs = _first_column(awards, ("program", "Program"))
    inventory = pd.DataFrame(
        {
            "nsf_sbir_awardee_name": names,
            "sbir_uei": _first_column(awards, ("company_uei", "uei", "recipient_uei", "UEI")).map(
                _clean_identifier
            ),
            "sbir_duns": _first_column(
                awards, ("company_duns", "duns", "recipient_duns", "Duns")
            ).map(_clean_identifier),
            "normalized_name": names.map(_clean_name),
            "nsf_sbir_award_title": _first_column(awards, ("award_title", "Award Title")),
            "nsf_sbir_phase": _first_column(awards, ("phase", "Phase")),
            "nsf_sbir_topic_code": _first_column(awards, ("topic_code", "Topic Code")),
            "nsf_sbir_award_year": pd.to_numeric(
                _first_column(awards, ("award_year", "Award Year")), errors="coerce"
            ),
            "nsf_sbir_award_amount": pd.to_numeric(
                _first_column(awards, ("award_amount", "Award Amount")), errors="coerce"
            ),
            "nsf_agency_tracking_number": _first_column(
                awards, ("agency_tracking_number", "Agency Tracking Number")
            ),
            "nsf_contract_number": _first_column(awards, ("contract", "Contract")),
            "nsf_solicitation_number": _first_column(
                awards, ("solicitation_number", "Solicitation Number")
            ),
            "nsf_proposal_award_date": pd.to_datetime(
                _first_column(awards, ("proposal_award_date", "Proposal Award Date")),
                errors="coerce",
            ),
            "nsf_contract_end_date": pd.to_datetime(
                _first_column(awards, ("contract_end_date", "Contract End Date")),
                errors="coerce",
            ),
            "nsf_sbir_abstract": _first_column(awards, ("abstract", "Abstract")),
            "funding_agency": agencies.map(_clean_category),
            "program": programs.map(_clean_category),
        }
    )
    inventory = inventory.loc[
        inventory["funding_agency"].map(_is_nsf) & inventory["program"].str.upper().eq("SBIR")
    ].copy()
    if inventory.empty:
        return inventory

    uei_map = _unique_mapping(awardees, "sbir_uei", "sbir_organization_id")
    duns_map = _unique_mapping(awardees, "sbir_duns", "sbir_organization_id")
    name_map = _unique_mapping(awardees, "normalized_name", "sbir_organization_id")
    inventory["uei_match"] = inventory["sbir_uei"].map(uei_map)
    inventory["duns_match"] = inventory["sbir_duns"].map(duns_map)
    inventory["name_match"] = inventory["normalized_name"].map(name_map)
    inventory["sbir_organization_id"] = (
        inventory["uei_match"].fillna(inventory["duns_match"]).fillna(inventory["name_match"])
    )
    inventory["awardee_association_method"] = MatchMethod.NORMALIZED_NAME.value
    inventory.loc[inventory["duns_match"].notna(), "awardee_association_method"] = (
        MatchMethod.DUNS.value
    )
    inventory.loc[inventory["uei_match"].notna(), "awardee_association_method"] = (
        MatchMethod.UEI.value
    )
    inventory = inventory.dropna(subset=["sbir_organization_id"])
    inventory["nsf_sbir_award_candidate_id"] = pd.util.hash_pandas_object(
        inventory[
            [
                "sbir_organization_id",
                "nsf_agency_tracking_number",
                "nsf_contract_number",
                "nsf_sbir_award_title",
                "nsf_sbir_award_year",
            ]
        ],
        index=False,
    ).map(lambda value: f"nsf-sbir:{value:016x}")
    inventory["_title_available"] = ~inventory["nsf_sbir_award_title"].fillna("").str.match(
        r"^\s*(?:not available)?\s*$", case=False
    )
    inventory["_abstract_length"] = inventory["nsf_sbir_abstract"].fillna("").astype(str).str.len()
    inventory = (
        inventory.sort_values(
            [
                "nsf_sbir_award_candidate_id",
                "_title_available",
                "nsf_sbir_award_amount",
                "_abstract_length",
            ],
            ascending=[True, False, False, False],
            na_position="last",
        )
        .drop_duplicates("nsf_sbir_award_candidate_id", keep="first")
        .drop(columns=["_title_available", "_abstract_length"])
    )

    exposure_columns = [
        "sbir_organization_id",
        "observed_prime_family_count",
        "observed_prime_legal_entity_count",
        "observed_prime_award_count",
        "max_relationship_fiscal_years",
        "reported_subaward_count",
        "reported_subaward_amount",
        "screening_status",
        "nsf_review_priority",
        "dependency_status",
    ]
    available_exposure_columns = [
        column for column in exposure_columns if column in supplier_exposure.columns
    ]
    candidates = inventory.merge(
        supplier_exposure[available_exposure_columns],
        on="sbir_organization_id",
        how="inner",
        validate="many_to_one",
    )
    candidates["supplier_relationship_evidence"] = EvidenceGrade.VERIFIED_IDENTIFIER.value
    candidates["specific_award_usage_status"] = "not_established"
    candidates["critical_supply_chain_status"] = "not_assessed"
    candidates["interpretation"] = (
        "The awardee has an identifier-verified observed DoD subaward relationship; "
        "use of this specific NSF-funded work and supply-chain criticality are not established"
    )
    return candidates.drop(columns=["uei_match", "duns_match", "name_match"]).sort_values(
        [
            "max_relationship_fiscal_years",
            "observed_prime_family_count",
            "nsf_sbir_award_year",
        ],
        ascending=[False, False, False],
        na_position="last",
    )


def _project_subawards(subawards: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prime_award_unique_key": _first_column(
                subawards, ("prime_award_unique_key", "unique_award_key")
            ),
            "prime_award_piid": _first_column(
                subawards, ("prime_award_piid", "prime_piid", "award_id")
            ),
            "prime_uei": _first_column(subawards, ("prime_awardee_uei", "prime_recipient_uei")).map(
                _clean_identifier
            ),
            "prime_duns": _first_column(
                subawards, ("prime_awardee_duns", "prime_recipient_duns")
            ).map(_clean_identifier),
            "prime_name": _first_column(subawards, ("prime_awardee_name", "prime_recipient_name")),
            "prime_parent_uei": _first_column(
                subawards, ("prime_awardee_parent_uei", "prime_parent_uei")
            ).map(_clean_identifier),
            "prime_parent_name": _first_column(
                subawards, ("prime_awardee_parent_name", "prime_parent_name")
            ),
            "prime_naics_code": _first_column(subawards, ("prime_award_naics_code", "naics_code")),
            "prime_award_description": _first_column(
                subawards,
                ("prime_award_base_transaction_description", "prime_award_description"),
            ),
            "subaward_number": _first_column(subawards, ("subaward_number", "subaward_id")),
            "subaward_sam_report_id": _first_column(
                subawards, ("subaward_sam_report_id", "sam_report_id")
            ),
            "subaward_amount": pd.to_numeric(
                _first_column(subawards, ("subaward_amount", "amount")), errors="coerce"
            ),
            "subaward_action_date": pd.to_datetime(
                _first_column(subawards, ("subaward_action_date", "action_date")),
                errors="coerce",
            ),
            "subawardee_uei": _first_column(subawards, ("subawardee_uei", "sub_recipient_uei")).map(
                _clean_identifier
            ),
            "subawardee_duns": _first_column(
                subawards, ("subawardee_duns", "sub_recipient_duns")
            ).map(_clean_identifier),
            "subawardee_name": _first_column(subawards, ("subawardee_name", "sub_recipient_name")),
            "subaward_description": _first_column(
                subawards, ("subaward_description", "description")
            ),
            "source_url": _first_column(subawards, ("usaspending_permalink", "source_url")),
            "source_last_modified": pd.to_datetime(
                _first_column(
                    subawards,
                    ("subaward_sam_report_last_modified_date", "source_last_modified"),
                ),
                errors="coerce",
                utc=True,
            ),
            "source_input_path": _first_column(subawards, ("source_input_path",)),
            "source_input_sha256": _first_column(subawards, ("source_input_sha256",)),
        }
    )


def build_subaward_facts(
    awardees: pd.DataFrame,
    subawards: pd.DataFrame,
    *,
    include_name_candidates: bool = True,
) -> pd.DataFrame:
    """Match reported DoD first-tier subawards to known SBIR awardees."""
    required = {
        "sbir_organization_id",
        "sbir_awardee_name",
        "sbir_uei",
        "sbir_duns",
        "normalized_name",
    }
    missing = sorted(required - set(awardees.columns))
    if missing:
        raise ValueError(f"awardee registry is missing required columns: {missing}")

    projected = _project_subawards(subawards)
    projected["subawardee_normalized_name"] = projected["subawardee_name"].map(_clean_name)
    uei_map = _unique_mapping(awardees, "sbir_uei", "sbir_organization_id")
    duns_map = _unique_mapping(awardees, "sbir_duns", "sbir_organization_id")
    name_map = _unique_mapping(awardees, "normalized_name", "sbir_organization_id")

    projected["uei_match"] = projected["subawardee_uei"].map(uei_map)
    projected["duns_match"] = projected["subawardee_duns"].map(duns_map)
    projected["name_match"] = (
        projected["subawardee_normalized_name"].map(name_map) if include_name_candidates else pd.NA
    )
    projected["sbir_organization_id"] = (
        projected["uei_match"].fillna(projected["duns_match"]).fillna(projected["name_match"])
    )
    projected = projected.dropna(subset=["sbir_organization_id"]).copy()

    # The prime award, prime-assigned subaward number, action date, and recipient
    # identify one economic fact. Amount and SAM report metadata can change when
    # that same fact is corrected or re-reported.
    projected["_logical_prime_award_id"] = (
        projected["prime_award_unique_key"]
        .map(_clean_category)
        .fillna(projected["prime_award_piid"].map(_clean_category))
    )
    projected["_logical_subaward_number"] = projected["subaward_number"].map(_clean_category)
    projected["_logical_subaward_action_date"] = projected["subaward_action_date"].dt.normalize()
    logical_key_available = (
        projected[
            [
                "_logical_prime_award_id",
                "_logical_subaward_number",
                "_logical_subaward_action_date",
            ]
        ]
        .notna()
        .all(axis=1)
    )
    fallback_fact_id = pd.util.hash_pandas_object(
        projected[
            [
                "prime_award_unique_key",
                "subaward_number",
                "_logical_subaward_action_date",
                "subawardee_uei",
                "subawardee_name",
            ]
        ],
        index=False,
    ).map(lambda value: f"{value:016x}")
    projected["_logical_row_fallback"] = fallback_fact_id.where(~logical_key_available)
    projected["subaward_fact_id"] = pd.util.hash_pandas_object(
        projected[
            [
                "_logical_prime_award_id",
                "_logical_subaward_number",
                "_logical_subaward_action_date",
                "sbir_organization_id",
                "_logical_row_fallback",
            ]
        ],
        index=False,
    ).map(lambda value: f"composite:{value:016x}")
    projected["match_method"] = MatchMethod.NORMALIZED_NAME.value
    projected.loc[projected["duns_match"].notna(), "match_method"] = MatchMethod.DUNS.value
    projected.loc[projected["uei_match"].notna(), "match_method"] = MatchMethod.UEI.value
    projected["evidence_grade"] = EvidenceGrade.CANDIDATE_NAME.value
    projected.loc[
        projected["match_method"].isin([MatchMethod.UEI.value, MatchMethod.DUNS.value]),
        "evidence_grade",
    ] = EvidenceGrade.VERIFIED_IDENTIFIER.value

    organization_columns = [
        "sbir_organization_id",
        "sbir_awardee_name",
        "sbir_uei",
        "sbir_duns",
        "sbir_award_count",
        "sbir_funding_agency_count",
        "nsf_sbir_awardee",
        "nsf_sbir_award_count",
        "nsf_sttr_award_count",
        "nsf_sbir_topic_codes",
        "nsf_sbir_first_award_year",
        "nsf_sbir_latest_award_year",
        "nsf_sbir_award_amount",
    ]
    facts = projected.merge(
        awardees[organization_columns],
        on="sbir_organization_id",
        how="left",
        validate="many_to_one",
    )
    facts["federal_reporting_level"] = "first_tier_subaward"
    facts["dib_supplier_tier"] = "tier_2"
    facts["dib_customer_tier"] = "tier_1_prime"
    facts["relationship_type"] = "reported_subcontract"
    facts["source_system"] = "USAspending.gov subaward data (SAM.gov/FSRS)"
    facts["absence_is_negative_evidence"] = False
    facts["source_report_version_count"] = facts.groupby(
        ["sbir_organization_id", "subaward_fact_id"], dropna=False
    )["subaward_fact_id"].transform("size")
    facts["_report_version_sort"] = facts["subaward_sam_report_id"].map(_clean_category).fillna("")
    facts["_version_tiebreaker"] = pd.util.hash_pandas_object(facts, index=False)

    output_columns = [
        "sbir_organization_id",
        "sbir_awardee_name",
        "sbir_uei",
        "sbir_duns",
        "sbir_award_count",
        "sbir_funding_agency_count",
        "nsf_sbir_awardee",
        "nsf_sbir_award_count",
        "nsf_sttr_award_count",
        "nsf_sbir_topic_codes",
        "nsf_sbir_first_award_year",
        "nsf_sbir_latest_award_year",
        "nsf_sbir_award_amount",
        "match_method",
        "evidence_grade",
        "relationship_type",
        "federal_reporting_level",
        "dib_supplier_tier",
        "dib_customer_tier",
        "prime_uei",
        "prime_duns",
        "prime_name",
        "prime_parent_uei",
        "prime_parent_name",
        "prime_award_unique_key",
        "prime_award_piid",
        "prime_naics_code",
        "prime_award_description",
        "subaward_number",
        "subaward_sam_report_id",
        "subaward_fact_id",
        "subaward_amount",
        "subaward_action_date",
        "subawardee_uei",
        "subawardee_duns",
        "subawardee_name",
        "subaward_description",
        "source_url",
        "source_last_modified",
        "source_input_path",
        "source_input_sha256",
        "source_report_version_count",
        "source_system",
        "absence_is_negative_evidence",
    ]
    latest_facts = facts.sort_values(
        [
            "sbir_organization_id",
            "subaward_fact_id",
            "source_last_modified",
            "_report_version_sort",
            "_version_tiebreaker",
        ],
        na_position="first",
    ).drop_duplicates(["sbir_organization_id", "subaward_fact_id"], keep="last")
    return (
        latest_facts[output_columns]
        .sort_values(["sbir_organization_id", "subaward_action_date", "prime_name"])
        .reset_index(drop=True)
    )


def aggregate_supplier_prime_edges(facts: pd.DataFrame) -> pd.DataFrame:
    """Aggregate subaward facts into one observed SBIR-supplier-to-prime edge."""
    required = {
        "sbir_organization_id",
        "sbir_awardee_name",
        "prime_uei",
        "prime_name",
        "prime_parent_uei",
        "prime_parent_name",
        "prime_award_unique_key",
        "subaward_number",
        "subaward_amount",
        "subaward_action_date",
        "evidence_grade",
    }
    missing = sorted(required - set(facts.columns))
    if missing:
        raise ValueError(f"subaward facts are missing required columns: {missing}")
    if facts.empty:
        return pd.DataFrame()

    working = facts.copy()
    working["prime_organization_id"] = (
        working["prime_uei"]
        .map(lambda value: f"uei:{value}" if value else None)
        .fillna(working["prime_parent_uei"].map(lambda value: f"uei:{value}" if value else None))
        .fillna(working["prime_name"].map(lambda value: f"name:{_clean_name(value)}"))
    )
    working["prime_family_id"] = (
        working["prime_parent_uei"]
        .map(lambda value: f"uei:{value}" if value else None)
        .fillna(working["prime_organization_id"])
    )
    working["prime_family_name"] = working["prime_parent_name"].fillna(working["prime_name"])
    working["identifier_verified"] = working["evidence_grade"].eq(
        EvidenceGrade.VERIFIED_IDENTIFIER.value
    )
    action_dates = pd.to_datetime(working["subaward_action_date"], errors="coerce")
    working["observed_fiscal_year"] = action_dates.dt.year + action_dates.dt.month.ge(10).astype(
        "Int64"
    )
    edges = (
        working.groupby(
            ["sbir_organization_id", "prime_organization_id"],
            as_index=False,
            dropna=False,
        )
        .agg(
            sbir_awardee_name=("sbir_awardee_name", "first"),
            nsf_sbir_awardee=("nsf_sbir_awardee", "first"),
            nsf_sbir_award_count=("nsf_sbir_award_count", "first"),
            nsf_sbir_topic_codes=("nsf_sbir_topic_codes", "first"),
            nsf_sbir_first_award_year=("nsf_sbir_first_award_year", "first"),
            nsf_sbir_latest_award_year=("nsf_sbir_latest_award_year", "first"),
            nsf_sbir_award_amount=("nsf_sbir_award_amount", "first"),
            prime_name=("prime_name", "first"),
            prime_parent_name=("prime_parent_name", "first"),
            prime_family_id=("prime_family_id", "first"),
            prime_family_name=("prime_family_name", "first"),
            reported_subaward_count=("subaward_number", "nunique"),
            prime_award_count=("prime_award_unique_key", "nunique"),
            reported_subaward_amount=("subaward_amount", "sum"),
            first_observed_date=("subaward_action_date", "min"),
            last_observed_date=("subaward_action_date", "max"),
            observed_fiscal_year_count=("observed_fiscal_year", "nunique"),
            identifier_verified_facts=("identifier_verified", "sum"),
            evidence_fact_count=("identifier_verified", "size"),
        )
        .sort_values("reported_subaward_amount", ascending=False)
        .reset_index(drop=True)
    )
    edges["all_facts_identifier_verified"] = (
        edges["identifier_verified_facts"] == edges["evidence_fact_count"]
    )
    edges["relationship_type"] = "observed_sbir_supplier_to_dod_prime"
    edges["supplier_dib_tier"] = "tier_2"
    edges["customer_dib_tier"] = "tier_1_prime"
    edges["dependency_status"] = "not_established"
    edges["nsf_supply_chain_review_candidate"] = edges["nsf_sbir_awardee"]
    return edges


def build_supplier_customer_exposure(edges: pd.DataFrame) -> pd.DataFrame:
    """Screen concentration in each SBIR supplier's observed prime-customer set."""
    required = {
        "sbir_organization_id",
        "sbir_awardee_name",
        "prime_organization_id",
        "prime_name",
        "prime_family_id",
        "prime_family_name",
        "reported_subaward_amount",
        "reported_subaward_count",
        "prime_award_count",
    }
    missing = sorted(required - set(edges.columns))
    if missing:
        raise ValueError(f"supplier-prime edges are missing required columns: {missing}")
    if edges.empty:
        return pd.DataFrame()

    source = edges.copy()
    nsf_defaults: dict[str, object] = {
        "nsf_sbir_awardee": False,
        "nsf_sbir_award_count": 0,
        "nsf_sbir_topic_codes": "",
        "nsf_sbir_first_award_year": pd.NA,
        "nsf_sbir_latest_award_year": pd.NA,
        "nsf_sbir_award_amount": 0.0,
    }
    for column, default in nsf_defaults.items():
        if column not in source.columns:
            source[column] = default

    working = source.groupby(
        ["sbir_organization_id", "prime_family_id"],
        as_index=False,
        dropna=False,
    ).agg(
        sbir_awardee_name=("sbir_awardee_name", "first"),
        nsf_sbir_awardee=("nsf_sbir_awardee", "first"),
        nsf_sbir_award_count=("nsf_sbir_award_count", "first"),
        nsf_sbir_topic_codes=("nsf_sbir_topic_codes", "first"),
        nsf_sbir_first_award_year=("nsf_sbir_first_award_year", "first"),
        nsf_sbir_latest_award_year=("nsf_sbir_latest_award_year", "first"),
        nsf_sbir_award_amount=("nsf_sbir_award_amount", "first"),
        prime_family_name=("prime_family_name", "first"),
        observed_prime_legal_entities=("prime_organization_id", "nunique"),
        prime_award_count=("prime_award_count", "sum"),
        observed_fiscal_year_count=("observed_fiscal_year_count", "max"),
        reported_subaward_count=("reported_subaward_count", "sum"),
        reported_subaward_amount=("reported_subaward_amount", "sum"),
    )
    working["reported_subaward_amount"] = working["reported_subaward_amount"].fillna(0.0)
    working["positive_net_amount"] = working["reported_subaward_amount"].clip(lower=0.0)
    totals = (
        working.groupby("sbir_organization_id", as_index=False)
        .agg(
            sbir_awardee_name=("sbir_awardee_name", "first"),
            nsf_sbir_awardee=("nsf_sbir_awardee", "first"),
            nsf_sbir_award_count=("nsf_sbir_award_count", "first"),
            nsf_sbir_topic_codes=("nsf_sbir_topic_codes", "first"),
            nsf_sbir_first_award_year=("nsf_sbir_first_award_year", "first"),
            nsf_sbir_latest_award_year=("nsf_sbir_latest_award_year", "first"),
            nsf_sbir_award_amount=("nsf_sbir_award_amount", "first"),
            observed_prime_family_count=("prime_family_id", "nunique"),
            observed_prime_legal_entity_count=("observed_prime_legal_entities", "sum"),
            observed_prime_award_count=("prime_award_count", "sum"),
            max_relationship_fiscal_years=("observed_fiscal_year_count", "max"),
            reported_subaward_count=("reported_subaward_count", "sum"),
            reported_subaward_amount=("reported_subaward_amount", "sum"),
            concentration_basis_amount=("positive_net_amount", "sum"),
            nonpositive_edge_count=(
                "reported_subaward_amount",
                lambda values: int(values.le(0).sum()),
            ),
        )
        .set_index("sbir_organization_id")
    )
    working = working.join(
        totals["concentration_basis_amount"].rename("supplier_total"),
        on="sbir_organization_id",
    )
    working["customer_share"] = working["positive_net_amount"].div(
        working["supplier_total"].where(working["supplier_total"].ne(0))
    )
    hhi = working.groupby("sbir_organization_id")["customer_share"].apply(
        lambda shares: float((shares.fillna(0.0) ** 2).sum())
    )
    top_index = working.groupby("sbir_organization_id")["reported_subaward_amount"].idxmax()
    top_customers = working.loc[
        top_index,
        [
            "sbir_organization_id",
            "prime_family_id",
            "prime_family_name",
            "customer_share",
        ],
    ].set_index("sbir_organization_id")
    exposure = totals.join(hhi.rename("observed_customer_hhi")).join(
        top_customers.rename(
            columns={
                "prime_family_id": "top_observed_prime_family_id",
                "prime_family_name": "top_observed_prime_family_name",
                "customer_share": "top_observed_prime_share",
            }
        )
    )
    exposure["screening_status"] = "multiple_observed_primes"
    exposure.loc[
        exposure["top_observed_prime_share"].ge(0.75),
        "screening_status",
    ] = "high_observed_customer_concentration"
    exposure.loc[
        exposure["observed_prime_family_count"].eq(1),
        "screening_status",
    ] = "single_observed_prime"
    exposure.loc[
        exposure["concentration_basis_amount"].le(0),
        "screening_status",
    ] = "nonpositive_reported_total"
    exposure["dependency_status"] = "not_established"
    exposure["nsf_supply_chain_review_candidate"] = exposure["nsf_sbir_awardee"]
    exposure["nsf_review_priority"] = "observed_relationship"
    exposure.loc[exposure["max_relationship_fiscal_years"].ge(3), "nsf_review_priority"] = (
        "persistent_relationship"
    )
    exposure.loc[~exposure["nsf_sbir_awardee"], "nsf_review_priority"] = "not_nsf_sbir"
    exposure["interpretation"] = (
        "Customer concentration from positive net supplier-prime edge amounts; "
        "not total revenue dependence or prime dependence on supplier"
    )
    return exposure.reset_index().sort_values(
        ["observed_customer_hhi", "reported_subaward_amount"],
        ascending=[False, False],
    )


def network_metadata(
    verified_facts: pd.DataFrame,
    verified_edges: pd.DataFrame,
    *,
    candidate_facts: pd.DataFrame | None = None,
    candidate_edges: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Summarize scope and guardrails for a materialized network slice."""
    candidate_facts = candidate_facts if candidate_facts is not None else pd.DataFrame()
    candidate_edges = candidate_edges if candidate_edges is not None else pd.DataFrame()
    return {
        "identifier_verified_subaward_facts": int(len(verified_facts)),
        "identifier_verified_supplier_prime_edges": int(len(verified_edges)),
        "identifier_verified_sbir_awardees": int(verified_facts["sbir_organization_id"].nunique())
        if not verified_facts.empty
        else 0,
        "identifier_verified_primes": int(verified_edges["prime_organization_id"].nunique())
        if not verified_edges.empty
        else 0,
        "identifier_verified_reported_subaward_amount": float(
            verified_facts["subaward_amount"].sum()
        )
        if not verified_facts.empty
        else 0.0,
        "identifier_verified_source_versions_collapsed": int(
            verified_facts["source_report_version_count"].sum() - len(verified_facts)
        )
        if not verified_facts.empty
        else 0,
        "identifier_verified_nonpositive_amount_facts": int(
            verified_facts["subaward_amount"].le(0).sum()
        )
        if not verified_facts.empty
        else 0,
        "name_candidate_subaward_facts": int(len(candidate_facts)),
        "name_candidate_supplier_prime_edges": int(len(candidate_edges)),
        "name_candidate_source_versions_collapsed": int(
            candidate_facts["source_report_version_count"].sum() - len(candidate_facts)
        )
        if not candidate_facts.empty
        else 0,
        "tier_semantics": {
            "tier_1": "DoD prime award recipient",
            "tier_2": "SBIR awardee reported as the prime's first-tier subcontractor",
            "tier_3_plus": "not observable in USAspending first-tier subaward data",
        },
        "interpretation_guardrails": [
            "A reported subcontract is an observed commercial relationship, not proof of dependency.",
            "Absence of a subaward is not evidence that no supplier relationship exists.",
            "Name-only matches are candidates and must not be treated as verified edges.",
            "Amounts are net reported subaward amounts and may include negative corrections.",
            "Customer concentration uses positive net edge amounts, not total revenue.",
        ],
    }


__all__ = [
    "EvidenceGrade",
    "MatchMethod",
    "aggregate_supplier_prime_edges",
    "build_sbir_awardee_registry",
    "build_nsf_sbir_award_candidates",
    "build_supplier_customer_exposure",
    "build_subaward_facts",
    "network_metadata",
]

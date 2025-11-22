"""Neo4j loading assets for SBIR awards."""

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    Output,
    asset,
    asset_check,
)
from loguru import logger

from ..config.loader import get_config
from ..loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig
from ..loaders.neo4j.organizations import OrganizationLoader
from ..models.award import Award
from ..utils.company_canonicalizer import canonicalize_companies_from_awards


# State name to code mapping
STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
    "puerto rico": "PR",
    "guam": "GU",
    "virgin islands": "VI",
    "american samoa": "AS",
    "northern mariana islands": "MP",
}

# Legal suffixes to remove during company name normalization
LEGAL_SUFFIXES = [
    r"\bincorporated\b",
    r"\bincorporation\b",
    r"\bcorporation\b",
    r"\bcompany\b",
    r"\blimited\b",
    r"\bliability\b",
    r"\bpartnership\b",
    r"\binc\.?\b",
    r"\bcorp\.?\b",
    r"\bco\.?\b",
    r"\bltd\.?\b",
    r"\bllc\.?\b",
    r"\bllp\.?\b",
    r"\blp\.?\b",
    r"\bplc\.?\b",
    r"\bp\.?c\.?\b",
    r"\bl\.?l\.?c\.?\b",
    r"\bl\.?l\.?p\.?\b",
    r"\bl\.?p\.?\b",
]

# Common abbreviation standardizations
ABBREVIATION_REPLACEMENTS = {
    r"\btechnologies\b": "tech",
    r"\btechnology\b": "tech",
    r"\bsystems?\b": "sys",
    r"\bsolutions?\b": "sol",
    r"\bservices?\b": "svc",
    r"\binternational\b": "intl",
    r"\bamerican\b": "amer",
    r"\bmanufacturing\b": "mfg",
    r"\bindustries\b": "ind",
    r"\benterprises?\b": "ent",
    r"\bassociates?\b": "assoc",
    r"\blaboratories\b": "lab",
    r"\blaboratory\b": "lab",
    r"\bresearch\b": "rsch",
    r"\bdevelopment\b": "dev",
}


def normalize_company_name(name: str) -> str:
    """Normalize company name for better matching across records.

    Applies the following transformations:
    1. Lowercase and strip whitespace
    2. Remove punctuation (except hyphens in the middle of words)
    3. Remove legal suffixes (Inc, Corp, LLC, etc.)
    4. Standardize common abbreviations
    5. Normalize whitespace to single spaces

    Args:
        name: Raw company name

    Returns:
        Normalized company name for use as identifier

    Example:
        >>> normalize_company_name("Acme Technologies, Inc.")
        'acme tech'
        >>> normalize_company_name("ABC Systems & Solutions LLC")
        'abc sys sol'
    """
    if not name:
        return ""

    # Lowercase and strip
    normalized = name.lower().strip()

    # Remove punctuation except hyphens (but replace hyphens with spaces)
    normalized = re.sub(r"[^\w\s-]", " ", normalized)
    normalized = normalized.replace("-", " ")

    # Remove legal suffixes
    for suffix in LEGAL_SUFFIXES:
        normalized = re.sub(suffix, "", normalized, flags=re.IGNORECASE)

    # Apply abbreviation standardizations
    for pattern, replacement in ABBREVIATION_REPLACEMENTS.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    # Normalize whitespace to single spaces
    normalized = " ".join(normalized.split())

    return normalized.strip()


def _get_neo4j_client() -> Neo4jClient | None:
    """Get Neo4j client from configuration, or None if unavailable."""
    try:
        config = get_config()
        neo4j_config = config.neo4j

        client_config = Neo4jConfig(
            uri=neo4j_config.uri,
            username=neo4j_config.username,
            password=neo4j_config.password,
            database=neo4j_config.database,
            batch_size=neo4j_config.batch_size,
        )

        client = Neo4jClient(client_config)
        # Test connection
        with client.session() as session:
            session.run("RETURN 1")
        return client
    except Exception as e:
        logger.warning(f"Neo4j unavailable: {e}")
        return None


def detect_award_progressions(
    awards: list[Award],
) -> list[tuple[str, str, str, str, str, str, str, dict[str, Any] | None]]:
    """Detect Phase I → Phase II → Phase III award progressions.

    Matches awards that represent the same project progressing through SBIR/STTR phases.

    Matching criteria:
    - Same company (via UEI, DUNS, or normalized name)
    - Same agency
    - Same program (SBIR or STTR)
    - Sequential phases (I → II or II → III)
    - Chronological order (earlier phase comes first)

    Additional scoring factors:
    - Same topic code (+0.3)
    - Same PI (+0.2)
    - Time gap within reasonable bounds (+0.1 if 1-4 years)

    Args:
        awards: List of Award objects to analyze

    Returns:
        List of relationship tuples in the format expected by batch_create_relationships:
        (source_label, source_key, source_id, target_label, target_key, target_id, rel_type, properties)
    """
    # Group awards by company identifier for efficient matching
    company_awards: dict[str, list[Award]] = {}

    for award in awards:
        if not award.phase or award.phase not in ["I", "II", "III"]:
            continue

        # Determine company identifier (same logic as main loading code)
        company_id = None
        if award.company_uei:
            company_id = award.company_uei
        elif award.company_duns:
            company_id = f"DUNS:{award.company_duns}"
        elif award.company_name:
            normalized_name = normalize_company_name(award.company_name)
            if normalized_name:
                company_id = f"NAME:{normalized_name}"

        if company_id:
            if company_id not in company_awards:
                company_awards[company_id] = []
            company_awards[company_id].append(award)

    # Detect progressions within each company's awards
    progressions = []
    phase_transitions = {"I": "II", "II": "III"}

    for _company_id, company_award_list in company_awards.items():
        # Sort by award date for chronological matching
        sorted_awards = sorted(
            company_award_list, key=lambda a: a.award_date if a.award_date else date(1900, 1, 1)
        )

        for i, earlier_award in enumerate(sorted_awards):
            if earlier_award.phase not in phase_transitions:
                continue

            expected_next_phase = phase_transitions[earlier_award.phase]

            # Look for matching later awards in the next phase
            for later_award in sorted_awards[i + 1 :]:
                if later_award.phase != expected_next_phase:
                    continue

                # Check basic matching criteria
                if earlier_award.agency != later_award.agency:
                    continue

                if earlier_award.program != later_award.program:
                    continue

                # Ensure chronological order
                if earlier_award.award_date and later_award.award_date:
                    if earlier_award.award_date >= later_award.award_date:
                        continue
                    years_between = (
                        later_award.award_date - earlier_award.award_date
                    ).days / 365.25
                else:
                    years_between = None

                # Calculate confidence score
                confidence = 0.5  # Base confidence for matching company, agency, program

                # Same topic code boosts confidence
                same_topic = False
                if (
                    earlier_award.topic_code
                    and later_award.topic_code
                    and earlier_award.topic_code == later_award.topic_code
                ):
                    confidence += 0.3
                    same_topic = True

                # Same PI boosts confidence
                same_pi = False
                if (
                    earlier_award.principal_investigator
                    and later_award.principal_investigator
                    and earlier_award.principal_investigator.lower()
                    == later_award.principal_investigator.lower()
                ):
                    confidence += 0.2
                    same_pi = True

                # Reasonable time gap boosts confidence
                if years_between is not None and 1 <= years_between <= 4:
                    confidence += 0.1

                # Create relationship properties
                rel_props = {
                    "phase_progression": f"{earlier_award.phase}_to_{expected_next_phase}",
                    "confidence": round(confidence, 2),
                    "same_topic": same_topic,
                    "same_pi": same_pi,
                }

                if years_between is not None:
                    rel_props["years_between"] = round(years_between, 2)

                # Add relationship tuple (FinancialTransaction -> FinancialTransaction)
                progressions.append(
                    (
                        "FinancialTransaction",
                        "transaction_id",
                        f"txn_award_{earlier_award.award_id}",
                        "FinancialTransaction",
                        "transaction_id",
                        f"txn_award_{later_award.award_id}",
                        "FOLLOWS",
                        rel_props,
                    )
                )

                # Only match each Phase I to the first qualifying Phase II
                # (to avoid multiple FOLLOWS from one award if there are multiple Phase IIs)
                break

    return progressions


@asset(
    description="Load validated SBIR awards into Neo4j with Award, Organization, Individual, and Institution nodes",
    group_name="neo4j_loading",
    compute_kind="neo4j",
)
def neo4j_sbir_awards(
    context: AssetExecutionContext, validated_sbir_awards: pd.DataFrame
) -> Output[dict[str, Any]]:
    """
    Load validated SBIR awards into Neo4j.

    Creates the following nodes:
    - Award nodes with properties from the validated DataFrame
    - Organization nodes (companies, deduplicated by UEI/DUNS/Name)
    - Individual nodes (researchers from PI fields, deduplicated by name+email)
    - Organization nodes (research institutions from RI fields, deduplicated by name)

    Creates the following relationships:
    - (FinancialTransaction)-[RECIPIENT_OF]->(Organization)
    - (Individual)-[PARTICIPATED_IN]->(Award)
    - (Award)-[CONDUCTED_AT]->(Organization)
    - (Individual)-[WORKED_AT]->(Organization)
    - (FinancialTransaction)-[FOLLOWS]->(FinancialTransaction) - Phase I → II → III progressions
    - (FinancialTransaction)-[FUNDED_BY]->(Organization {agency})

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame

    Returns:
        Dictionary with load metrics and status
    """
    client = _get_neo4j_client()
    if client is None:
        return Output(
            value={"status": "skipped", "reason": "neo4j_unavailable"},
            metadata={"skipped": True, "reason": "Neo4j client unavailable"},
        )

    start_time = time.time()
    metrics = LoadMetrics()

    try:
        # Ensure constraints exist (deprecated - migrations handle this, but keep for backward compatibility)
        client.create_constraints()
        client.create_indexes()

        # STEP 1: Pre-loading deduplication - canonicalize companies before processing
        config = get_config()
        dedup_config = config.company_deduplication
        context.log.info("Pre-processing: Canonicalizing companies...")

        canonical_map = canonicalize_companies_from_awards(
            validated_sbir_awards,
            high_threshold=dedup_config.get("high_threshold", 90),
            low_threshold=dedup_config.get("low_threshold", 75),
            enhanced_config=dedup_config.get("enhanced_matching"),
        )

        context.log.info(f"Canonicalized {len(canonical_map)} companies")

        # Convert DataFrame rows to Award models, then to Neo4j node properties
        award_nodes = []
        award_objects: list[Award] = []  # Keep Award objects for progression detection
        company_nodes_map: dict[str, dict[str, Any]] = {}
        researcher_nodes_map: dict[str, dict[str, Any]] = {}
        institution_nodes_map: dict[str, dict[str, Any]] = {}
        award_company_rels: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []
        award_institution_rels: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []
        researcher_award_rels: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []  # PARTICIPATED_IN
        researcher_company_rels: list[
            tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]
        ] = []  # WORKED_AT

        # Track skip reasons
        skipped_zero_amount = 0
        skipped_no_company_id = 0
        validation_errors = 0
        date_validation_errors = 0  # Track date hygiene validation errors
        companies_by_name_only = 0  # Track companies identified by name only

        for _, row in validated_sbir_awards.iterrows():
            try:
                # Convert row dict to Award model
                # Normalize column names: lowercase and replace spaces with underscores
                # Also convert pandas NaN to None for proper Pydantic validation
                row_dict = row.to_dict()
                normalized_dict: dict[str, Any] = {}
                for key, value in row_dict.items():
                    normalized_key = key.lower().replace(" ", "_")
                    # Convert pandas NaN/NA to None
                    if pd.isna(value):
                        normalized_dict[normalized_key] = None
                    else:
                        # Special handling for state - convert full name to 2-letter code
                        if normalized_key == "state" and isinstance(value, str):
                            state_lower = value.strip().lower()
                            normalized_dict[normalized_key] = STATE_NAME_TO_CODE.get(
                                state_lower, value
                            )
                        # Special handling for number_employees - convert float to int
                        # (CSV has "Number Employees", not "Number Of Employees")
                        elif normalized_key == "number_employees" and isinstance(value, float):
                            # Only convert if it's a whole number (no fractional part)
                            if value.is_integer():
                                normalized_dict[normalized_key] = int(value)
                            else:
                                normalized_dict[normalized_key] = value
                        # Special handling for zip - convert '-' placeholder to None
                        elif (
                            normalized_key == "zip"
                            and isinstance(value, str)
                            and value.strip() == "-"
                        ):
                            normalized_dict[normalized_key] = None
                        # Special handling for DUNS - pad short DUNS with leading zeros
                        elif normalized_key == "duns" and isinstance(value, str):
                            # Strip hyphens and extract digits
                            digits = "".join(ch for ch in value if ch.isdigit())
                            # Pad with leading zeros if 7-8 digits (some old DUNS were 7-8 digits)
                            if 7 <= len(digits) <= 8:
                                normalized_dict[normalized_key] = digits.zfill(9)
                            else:
                                normalized_dict[normalized_key] = value
                        # Special handling for boolean fields - convert 'U' (Unknown) to None
                        elif (
                            normalized_key
                            in (
                                "hubzone_owned",
                                "woman_owned",
                                "socially_and_economically_disadvantaged",
                            )
                            and value == "U"
                        ):
                            normalized_dict[normalized_key] = None
                        else:
                            normalized_dict[normalized_key] = value

                # Skip records with zero or missing award amounts (likely cancelled/placeholder awards)
                award_amount = normalized_dict.get("award_amount")
                if award_amount is None or (
                    isinstance(award_amount, (int, float)) and award_amount <= 0
                ):
                    # Try to identify the award for logging
                    tracking = normalized_dict.get("agency_tracking_number", "")
                    contract = normalized_dict.get("contract", "")
                    company = normalized_dict.get("company", "")
                    award_id_hint = f"{tracking[:20] if tracking else contract[:20] if contract else company[:30]}"

                    if skipped_zero_amount < 10:  # Only log first 10 to avoid spam
                        logger.debug(
                            f"Skipping award with zero/missing amount: {award_id_hint} (amount={award_amount})"
                        )
                    skipped_zero_amount += 1
                    metrics.errors += 1
                    continue

                award = Award.from_sbir_csv(normalized_dict)

                # Create FinancialTransaction node properties (unified Award/Contract model)
                transaction_id = f"txn_award_{award.award_id}"
                transaction_props = {
                    "transaction_id": transaction_id,
                    "transaction_type": "AWARD",
                    "award_id": award.award_id,  # Legacy ID for backward compatibility
                    "recipient_name": award.company_name,
                    "amount": award.award_amount,
                    "transaction_date": award.award_date.isoformat() if award.award_date else None,
                    "program": award.program,
                    "phase": award.phase,
                    "agency": award.agency,
                    "agency_name": award.agency,  # Will be enriched later
                    "sub_agency": award.branch,
                    "title": award.award_title,
                    "description": award.abstract,
                    "award_year": award.award_year,
                    "fiscal_year": award.fiscal_year,
                    "principal_investigator": award.principal_investigator,
                    "research_institution": award.research_institution,
                    "completion_date": award.contract_end_date.isoformat()
                    if award.contract_end_date
                    else None,
                    "start_date": award.contract_start_date.isoformat()
                    if award.contract_start_date
                    else None,
                    "end_date": award.contract_end_date.isoformat()
                    if award.contract_end_date
                    else None,
                }

                # Add optional fields if present
                if award.company_uei:
                    transaction_props["recipient_uei"] = award.company_uei
                if award.company_duns:
                    transaction_props["recipient_duns"] = award.company_duns
                if award.company_cage:
                    transaction_props["recipient_cage"] = award.company_cage
                # NAICS code might be on award if enriched, otherwise skip
                naics_code = getattr(award, "naics_primary", None)  # type: ignore[arg-type]
                if naics_code:
                    transaction_props["naics_code"] = naics_code

                award_nodes.append(transaction_props)
                award_objects.append(award)  # Keep Award object for progression detection

                # Create Company node with fallback hierarchy: UEI > DUNS > Name
                # Use canonical mapping from pre-loading deduplication
                normalized_company_name = (
                    normalize_company_name(award.company_name) if award.company_name else ""
                )

                # Build original key
                if award.company_uei:
                    original_key = award.company_uei
                elif award.company_duns:
                    original_key = f"DUNS:{award.company_duns}"
                elif normalized_company_name:
                    original_key = f"NAME:{normalized_company_name}"
                else:
                    original_key = None

                # Map to canonical using pre-loading deduplication result
                company_id = None
                company_id_type = None

                if original_key and original_key in canonical_map:
                    canonical_key = canonical_map[original_key]
                    if canonical_key.startswith("UEI:"):
                        company_id = canonical_key[4:]  # Remove "UEI:" prefix
                        company_id_type = "uei"
                    elif canonical_key.startswith("DUNS:"):
                        company_id = canonical_key[5:]  # Remove "DUNS:" prefix
                        company_id_type = "duns"
                    else:
                        company_id = canonical_key  # Keep full "NAME:..." for name-based
                        company_id_type = "name"
                elif original_key:
                    # Fallback to original logic if not in canonical map
                    if award.company_uei:
                        company_id = award.company_uei
                        company_id_type = "uei"
                    elif award.company_duns:
                        company_id = f"DUNS:{award.company_duns}"
                        company_id_type = "duns"
                    elif normalized_company_name:
                        company_id = f"NAME:{normalized_company_name}"
                        company_id_type = "name"
                        companies_by_name_only += 1
                else:
                    # Track awards without any company identifier
                    if skipped_no_company_id < 10:
                        logger.debug(f"Award {award.award_id} has no company name, UEI, or DUNS")
                    skipped_no_company_id += 1

                if company_id:
                    # Generate organization_id from company_id
                    organization_id = f"org_company_{company_id}"

                    if company_id not in company_nodes_map:
                        company_props = {
                            "organization_id": organization_id,
                            "company_id": company_id,  # Keep for backward compatibility
                            "name": award.company_name,
                            "normalized_name": normalized_company_name,
                            "organization_type": "COMPANY",
                            "source_contexts": ["SBIR"],
                            "id_type": company_id_type,  # Track identification method
                        }
                        # Store all known identifiers for cross-walking
                        if award.company_uei:
                            company_props["uei"] = award.company_uei
                        if award.company_duns:
                            company_props["duns"] = award.company_duns
                        if award.company_city:
                            company_props["city"] = award.company_city
                        if award.company_state:
                            company_props["state"] = award.company_state
                        if award.company_zip:
                            company_props["postcode"] = (
                                award.company_zip
                            )  # Use postcode for consistency
                        company_nodes_map[company_id] = company_props
                    else:
                        # Company already exists - update with additional identifiers (cross-walking)
                        existing_company = company_nodes_map[company_id]
                        if award.company_uei and not existing_company.get("uei"):
                            existing_company["uei"] = award.company_uei
                        if award.company_duns and not existing_company.get("duns"):
                            existing_company["duns"] = award.company_duns
                        # Update location if missing
                        if award.company_city and not existing_company.get("city"):
                            existing_company["city"] = award.company_city
                        if award.company_state and not existing_company.get("state"):
                            existing_company["state"] = award.company_state
                        if award.company_zip and not existing_company.get("postcode"):
                            existing_company["postcode"] = award.company_zip

                    # Create RECIPIENT_OF relationship (FinancialTransaction -> Organization)
                    award_company_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "Organization",
                            "organization_id",
                            organization_id,
                            "RECIPIENT_OF",
                            None,
                        )
                    )

                # Create Researcher node if PI name available
                if award.principal_investigator:
                    # Generate researcher_id from name and email (or just name)
                    pi_name = award.principal_investigator.strip()
                    pi_email = award.pi_email.strip() if award.pi_email else None

                    # Create unique researcher ID
                    if pi_email:
                        researcher_id = f"{pi_name}|{pi_email}".lower()
                    else:
                        researcher_id = pi_name.lower()

                    if researcher_id not in researcher_nodes_map:
                        individual_id = f"ind_researcher_{researcher_id}"
                        researcher_props = {
                            "individual_id": individual_id,
                            "researcher_id": researcher_id,  # Keep for backward compatibility
                            "name": pi_name,
                            "normalized_name": pi_name.upper(),
                            "individual_type": "RESEARCHER",
                            "source_contexts": ["SBIR"],
                        }
                        if pi_email:
                            researcher_props["email"] = pi_email
                        if award.pi_title:
                            researcher_props["title"] = award.pi_title
                        if award.pi_phone:
                            researcher_props["phone"] = award.pi_phone
                        researcher_nodes_map[researcher_id] = researcher_props

                    # Create PARTICIPATED_IN relationship (Individual -> Award)
                    # Unified relationship replacing RESEARCHED_BY and WORKED_ON
                    individual_id = f"ind_researcher_{researcher_id}"
                    researcher_award_rels.append(
                        (
                            "Individual",
                            "individual_id",
                            individual_id,
                            "Award",
                            "award_id",
                            award.award_id,
                            "PARTICIPATED_IN",
                            {"role": "RESEARCHER"},
                        )
                    )

                    # Create WORKED_AT relationship (Individual -> Organization) if company exists
                    if company_id:
                        organization_id = f"org_company_{company_id}"
                        researcher_company_rels.append(
                            (
                                "Individual",
                                "individual_id",
                                individual_id,
                                "Organization",
                                "organization_id",
                                organization_id,
                                "WORKED_AT",
                                None,
                            )
                        )

                # Create Research Institution node as Organization if RI name available
                if award.research_institution:
                    institution_name = award.research_institution.strip()
                    organization_id = f"org_research_{institution_name}"

                    if institution_name not in institution_nodes_map:
                        institution_props = {
                            "organization_id": organization_id,
                            "name": institution_name,
                            "normalized_name": institution_name.upper(),
                            "organization_type": "UNIVERSITY",
                            "source_contexts": ["RESEARCH"],
                        }
                        if award.ri_poc_name:
                            institution_props["poc_name"] = award.ri_poc_name
                        if award.ri_poc_phone:
                            institution_props["poc_phone"] = award.ri_poc_phone
                        institution_nodes_map[institution_name] = institution_props

                    # Create CONDUCTED_AT relationship (Award -> Organization)
                    award_institution_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "Organization",
                            "organization_id",
                            organization_id,
                            "CONDUCTED_AT",
                            None,
                        )
                    )

            except Exception as e:
                error_msg = str(e)
                # Check if it's a date validation error by examining the error message
                is_date_error = any(
                    keyword in error_msg.lower()
                    for keyword in ["date", "future", "before", "after"]
                )

                if is_date_error:
                    if date_validation_errors < 10:  # Only log first 10 to avoid spam
                        logger.warning(f"Date validation error: {e}")
                    date_validation_errors += 1
                else:
                    if validation_errors < 10:  # Only log first 10 to avoid spam
                        logger.warning(f"Failed to process award row: {e}")
                    validation_errors += 1
                metrics.errors += 1

        # Load Organization nodes (companies) first - using multi-key MERGE
        if company_nodes_map:
            company_nodes_list = list(company_nodes_map.values())
            company_metrics = client.batch_upsert_organizations_with_multi_key(
                nodes=company_nodes_list,
                metrics=metrics,
                merge_on_uei=dedup_config.get("merge_on_uei", True),
                merge_on_duns=dedup_config.get("merge_on_duns", True),
                track_merge_history=dedup_config.get("track_merge_history", True),
            )
            metrics = company_metrics
            context.log.info(
                f"Loaded {len(company_nodes_list)} Organization nodes (companies): "
                f"{metrics.nodes_created.get('Organization', 0)} created, "
                f"{metrics.nodes_updated.get('Organization', 0)} updated"
            )

        # Load FinancialTransaction nodes (unified Award/Contract model)
        if award_nodes:
            transaction_metrics = client.batch_upsert_nodes(
                label="FinancialTransaction",
                key_property="transaction_id",
                nodes=award_nodes,
                metrics=metrics,
            )
            metrics = transaction_metrics
            context.log.info(f"Loaded {len(award_nodes)} FinancialTransaction nodes (AWARD type)")

        # Load Individual nodes (researchers)
        if researcher_nodes_map:
            researcher_nodes_list = list(researcher_nodes_map.values())
            researcher_metrics = client.batch_upsert_nodes(
                label="Individual",
                key_property="individual_id",
                nodes=researcher_nodes_list,
                metrics=metrics,
            )
            metrics = researcher_metrics
            context.log.info(f"Loaded {len(researcher_nodes_list)} Individual nodes (researchers)")

        # Load Research Institution nodes as Organizations
        if institution_nodes_map:
            institution_nodes_list = list(institution_nodes_map.values())
            institution_metrics = client.batch_upsert_nodes(
                label="Organization",
                key_property="organization_id",
                nodes=institution_nodes_list,
                metrics=metrics,
            )
            metrics = institution_metrics
            context.log.info(
                f"Loaded {len(institution_nodes_list)} Organization nodes (research institutions)"
            )

        # Create RECIPIENT_OF relationships (FinancialTransaction -> Organization)
        if award_company_rels:
            # Update relationship tuples to use FinancialTransaction instead of Award
            updated_rels = []
            for rel in award_company_rels:
                if rel[0] == "Award":
                    # Convert Award relationships to FinancialTransaction
                    updated_rels.append(
                        (
                            "FinancialTransaction",
                            "transaction_id",
                            f"txn_award_{rel[2]}",  # transaction_id from award_id
                            rel[3],
                            rel[4],
                            rel[5],
                            rel[6],
                            rel[7],
                        )
                    )
                else:
                    updated_rels.append(rel)
            rel_metrics = client.batch_create_relationships(updated_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(
                f"Created {len(updated_rels)} RECIPIENT_OF relationships (FinancialTransaction -> Organization)"
            )

        # Create CONDUCTED_AT relationships (FinancialTransaction -> Organization)
        if award_institution_rels:
            # Update relationship tuples to use FinancialTransaction instead of Award
            updated_rels = []
            for rel in award_institution_rels:
                if rel[0] == "Award":
                    updated_rels.append(
                        (
                            "FinancialTransaction",
                            "transaction_id",
                            f"txn_award_{rel[2]}",
                            rel[3],
                            rel[4],
                            rel[5],
                            rel[6],
                            rel[7],
                        )
                    )
                else:
                    updated_rels.append(rel)
            rel_metrics = client.batch_create_relationships(updated_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(
                f"Created {len(updated_rels)} CONDUCTED_AT relationships (FinancialTransaction -> Organization)"
            )

        # Create PARTICIPATED_IN relationships (Individual -> FinancialTransaction)
        # Unified relationship replacing RESEARCHED_BY and WORKED_ON
        if researcher_award_rels:
            # Update relationship tuples to use FinancialTransaction instead of Award
            updated_rels = []
            for rel in researcher_award_rels:
                if rel[3] == "Award":
                    updated_rels.append(
                        (
                            rel[0],
                            rel[1],
                            rel[2],
                            "FinancialTransaction",
                            "transaction_id",
                            f"txn_award_{rel[5]}",  # transaction_id from award_id
                            rel[6],
                            rel[7],
                        )
                    )
                else:
                    updated_rels.append(rel)
            rel_metrics = client.batch_create_relationships(updated_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(
                f"Created {len(updated_rels)} PARTICIPATED_IN relationships (Individual -> FinancialTransaction)"
            )

        # Create WORKED_AT relationships (Individual -> Organization)
        if researcher_company_rels:
            rel_metrics = client.batch_create_relationships(
                researcher_company_rels, metrics=metrics
            )
            metrics = rel_metrics
            context.log.info(
                f"Created {len(researcher_company_rels)} WORKED_AT relationships (Individual -> Organization)"
            )

        # Create FUNDED_BY relationships (Award -> Organization {agency})
        # Extract unique agencies and create Organization nodes for them
        # Also create sub-agency nodes and SUBSIDIARY_OF relationships
        agency_orgs_map = {}
        sub_agency_orgs_map = {}
        award_agency_rels = []
        agency_subsidiary_pairs = []

        for award in award_objects:
            agency_code = award.agency
            agency_name = getattr(award, "agency_name", award.agency)  # type: ignore[arg-type]
            if agency_code and agency_name:
                parent_organization_id = f"org_agency_{agency_code}"

                # Create parent agency node if not exists
                if parent_organization_id not in agency_orgs_map:
                    agency_props = {
                        "organization_id": parent_organization_id,
                        "name": agency_name,
                        "normalized_name": agency_name.upper(),
                        "organization_type": "AGENCY",
                        "source_contexts": ["AGENCY"],
                        "agency_code": agency_code,
                        "agency_name": agency_name,
                    }
                    agency_orgs_map[parent_organization_id] = agency_props

                # Handle sub-agency if present
                target_organization_id = parent_organization_id
                sub_agency_code = getattr(award, "sub_agency", None)  # type: ignore[arg-type]
                sub_agency_name = getattr(award, "sub_agency_name", None)  # type: ignore[arg-type]
                if award.branch and sub_agency_code:
                    sub_agency_name = sub_agency_name or award.branch
                    sub_organization_id = f"org_agency_{agency_code}_{sub_agency_code}"

                    # Create sub-agency node if not exists
                    if sub_organization_id not in sub_agency_orgs_map:
                        sub_agency_props = {
                            "organization_id": sub_organization_id,
                            "name": sub_agency_name,
                            "normalized_name": sub_agency_name.upper(),
                            "organization_type": "AGENCY",
                            "source_contexts": ["AGENCY"],
                            "agency_code": agency_code,
                            "agency_name": agency_name,
                            "sub_agency_code": sub_agency_code,
                            "sub_agency_name": sub_agency_name,
                        }
                        sub_agency_orgs_map[sub_organization_id] = sub_agency_props

                    # Track SUBSIDIARY_OF relationship (sub-agency -> parent agency)
                    agency_subsidiary_pairs.append(
                        (
                            "organization_id",
                            sub_organization_id,
                            "organization_id",
                            parent_organization_id,
                        )
                    )
                    target_organization_id = sub_organization_id

                # Create FUNDED_BY relationship (to parent agency or sub-agency)
                award_agency_rels.append(
                    (
                        "FinancialTransaction",
                        "transaction_id",
                        f"txn_award_{award.award_id}",
                        "Organization",
                        "organization_id",
                        target_organization_id,
                        "FUNDED_BY",
                        None,
                    )
                )

        # Load Agency Organization nodes (parent agencies)
        if agency_orgs_map:
            agency_nodes_list = list(agency_orgs_map.values())
            agency_metrics = client.batch_upsert_nodes(
                label="Organization",
                key_property="organization_id",
                nodes=agency_nodes_list,
                metrics=metrics,
            )
            metrics = agency_metrics
            context.log.info(
                f"Loaded {len(agency_nodes_list)} Organization nodes (parent agencies)"
            )

        # Load Sub-Agency Organization nodes
        if sub_agency_orgs_map:
            sub_agency_nodes_list = list(sub_agency_orgs_map.values())
            sub_agency_metrics = client.batch_upsert_nodes(
                label="Organization",
                key_property="organization_id",
                nodes=sub_agency_nodes_list,
                metrics=metrics,
            )
            metrics = sub_agency_metrics
            context.log.info(
                f"Loaded {len(sub_agency_nodes_list)} Organization nodes (sub-agencies)"
            )

        # Create FUNDED_BY relationships
        if award_agency_rels:
            rel_metrics = client.batch_create_relationships(award_agency_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(
                f"Created {len(award_agency_rels)} FUNDED_BY relationships (FinancialTransaction -> Organization)"
            )

        # Create SUBSIDIARY_OF relationships (sub-agency -> parent agency)
        if agency_subsidiary_pairs:
            org_loader = OrganizationLoader(client)
            org_metrics = org_loader.create_subsidiary_relationships(
                agency_subsidiary_pairs,
                source="AGENCY_HIERARCHY",
                metrics=metrics,
            )
            metrics = org_metrics
            context.log.info(
                f"Created {len(agency_subsidiary_pairs)} SUBSIDIARY_OF relationships (sub-agency -> parent agency)"
            )

        # Detect and create FOLLOWS relationships (FinancialTransaction -> FinancialTransaction for phase progressions)
        context.log.info("Detecting award phase progressions...")
        follows_rels = detect_award_progressions(award_objects)
        if follows_rels:
            rel_metrics = client.batch_create_relationships(follows_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(
                f"Created {len(follows_rels)} FOLLOWS relationships for award progressions (FinancialTransaction -> FinancialTransaction)"
            )
        else:
            context.log.info("No award progressions detected")

        # Log comprehensive summary of processing results
        total_rows = len(validated_sbir_awards)
        successfully_processed = len(award_nodes)
        # Only count actual failures (zero amounts and validation errors), not missing company IDs
        # Awards without company IDs are still successfully processed, just not linked to companies
        total_failed = skipped_zero_amount + validation_errors + date_validation_errors

        logger.info("=" * 80)
        logger.info("Neo4j SBIR Awards Loading Summary")
        logger.info("=" * 80)
        logger.info(f"Total rows processed: {total_rows}")
        logger.info(
            f"Successfully processed: {successfully_processed} ({successfully_processed / total_rows * 100:.1f}%)"
        )
        logger.info(f"Failed to process: {total_failed} ({total_failed / total_rows * 100:.1f}%)")
        logger.info("")
        logger.info("Processing Issues:")
        logger.info(
            f"  • Zero/missing award amount: {skipped_zero_amount} ({skipped_zero_amount / total_rows * 100:.1f}%)"
        )
        logger.info(
            f"  • Date validation errors: {date_validation_errors} ({date_validation_errors / total_rows * 100:.1f}%)"
        )
        logger.info(
            f"  • Other validation errors: {validation_errors} ({validation_errors / total_rows * 100:.1f}%)"
        )
        logger.info(
            f"  • Awards without any company identifier: {skipped_no_company_id} ({skipped_no_company_id / total_rows * 100:.1f}%)"
        )
        logger.info("")
        logger.info("Nodes Created/Updated:")
        logger.info(f"  • Awards: {len(award_nodes)} nodes")
        logger.info(f"  • Companies: {len(company_nodes_map)} unique nodes")
        logger.info(
            f"    - Identified by name only: {companies_by_name_only} ({companies_by_name_only / len(company_nodes_map) * 100:.1f}% of companies)"
        )
        logger.info(f"  • Researchers: {len(researcher_nodes_map)} unique nodes")
        logger.info(f"  • Research Institutions: {len(institution_nodes_map)} unique nodes")
        logger.info("")
        logger.info("Relationships Created:")
        logger.info(
            f"  • RECIPIENT_OF (FinancialTransaction → Organization): {len(award_company_rels)} relationships"
        )
        logger.info(
            f"  • PARTICIPATED_IN (Individual → Award): {len(researcher_award_rels)} relationships"
        )
        logger.info(
            f"  • CONDUCTED_AT (Award → Organization): {len(award_institution_rels)} relationships"
        )
        logger.info(
            f"  • WORKED_AT (Individual → Organization): {len(researcher_company_rels)} relationships"
        )
        logger.info(
            f"  • FOLLOWS (FinancialTransaction → FinancialTransaction): {len(follows_rels)} phase progressions"
        )
        logger.info("=" * 80)

        duration = time.time() - start_time

        result = {
            "status": "success",
            "awards_loaded": metrics.nodes_created.get("Award", 0),
            "awards_updated": metrics.nodes_updated.get("Award", 0),
            "companies_loaded": metrics.nodes_created.get("Company", 0),
            "companies_updated": metrics.nodes_updated.get("Company", 0),
            "researchers_loaded": metrics.nodes_created.get("Researcher", 0),
            "researchers_updated": metrics.nodes_updated.get("Researcher", 0),
            "institutions_loaded": metrics.nodes_created.get("ResearchInstitution", 0),
            "institutions_updated": metrics.nodes_updated.get("ResearchInstitution", 0),
            "relationships_created": sum(metrics.relationships_created.values()),
            "errors": metrics.errors,
            "duration_seconds": duration,
            "total_rows_processed": total_rows,
            "successfully_processed": successfully_processed,
            "skip_reasons": {
                "zero_or_missing_amount": skipped_zero_amount,
                "no_company_identifier": skipped_no_company_id,
                "date_validation_errors": date_validation_errors,
                "other_validation_errors": validation_errors,
            },
            "companies_by_name_only": companies_by_name_only,
            "metrics": {
                "nodes_created": metrics.nodes_created,
                "nodes_updated": metrics.nodes_updated,
                "relationships_created": metrics.relationships_created,
                "errors": metrics.errors,
            },
        }

        # Write metrics to file
        output_dir = Path("data/loaded/neo4j")
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics_file = output_dir / f"neo4j_sbir_awards_metrics_{int(time.time())}.json"
        with metrics_file.open("w") as f:
            json.dump(result, f, indent=2)

        context.log.info(
            "Neo4j SBIR awards load complete",
            extra={
                "awards_loaded": result["awards_loaded"],
                "companies_loaded": result["companies_loaded"],
                "researchers_loaded": result["researchers_loaded"],
                "institutions_loaded": result["institutions_loaded"],
                "relationships_created": result["relationships_created"],
                "errors": result["errors"],
                "duration_seconds": duration,
            },
        )

        return Output(
            value=result,
            metadata={  # type: ignore[dict-item]
                "awards_loaded": result["awards_loaded"],
                "companies_loaded": result["companies_loaded"],
                "researchers_loaded": result["researchers_loaded"],
                "institutions_loaded": result["institutions_loaded"],
                "relationships_created": result["relationships_created"],
                "errors": result["errors"],
                "duration_seconds": round(duration, 2),
                "metrics_file": str(metrics_file),
            },
        )

    except Exception as e:
        logger.error(f"Failed to load SBIR awards to Neo4j: {e}")
        return Output(
            value={"status": "error", "error": str(e)},
            metadata={"error": str(e)},
        )
    finally:
        client.close()


@asset_check(
    asset=neo4j_sbir_awards,
    description="Verify SBIR awards were loaded successfully into Neo4j",
)
def neo4j_sbir_awards_load_check(neo4j_sbir_awards: dict[str, Any]) -> AssetCheckResult:
    """
    Check that SBIR awards were loaded successfully into Neo4j.

    Fails if load status is not "success" or if error count is too high.
    """
    status = neo4j_sbir_awards.get("status")
    errors = neo4j_sbir_awards.get("errors", 0)
    awards_loaded = neo4j_sbir_awards.get("awards_loaded", 0)
    total_rows = neo4j_sbir_awards.get("total_rows_processed", 0)

    if status != "success":
        reason = neo4j_sbir_awards.get("reason") or neo4j_sbir_awards.get("error", "unknown")
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Neo4j load failed: {reason}",
            metadata={"status": status, "reason": reason},
        )

    # Allow some errors but fail if error rate is too high (percentage-based threshold)
    error_rate_threshold = 0.25  # 25% error rate threshold
    error_rate = errors / total_rows if total_rows > 0 else 0
    if error_rate > error_rate_threshold:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"✗ Too many load errors: {errors}/{total_rows} ({error_rate * 100:.1f}% > {error_rate_threshold * 100:.0f}% threshold)",
            metadata={
                "errors": errors,
                "total_rows": total_rows,
                "error_rate": error_rate,
                "threshold": error_rate_threshold,
            },
        )

    if awards_loaded == 0:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ No awards were loaded",
            metadata={"awards_loaded": 0},
        )

    return AssetCheckResult(
        passed=True,
        severity=AssetCheckSeverity.WARN,
        description=f"✓ Neo4j load successful: {awards_loaded} awards, {neo4j_sbir_awards.get('researchers_loaded', 0)} researchers, {neo4j_sbir_awards.get('institutions_loaded', 0)} institutions ({error_rate * 100:.1f}% error rate)",
        metadata={
            "awards_loaded": awards_loaded,
            "companies_loaded": neo4j_sbir_awards.get("companies_loaded", 0),
            "researchers_loaded": neo4j_sbir_awards.get("researchers_loaded", 0),
            "institutions_loaded": neo4j_sbir_awards.get("institutions_loaded", 0),
            "relationships_created": neo4j_sbir_awards.get("relationships_created", 0),
            "errors": errors,
            "error_rate": error_rate,
        },
    )

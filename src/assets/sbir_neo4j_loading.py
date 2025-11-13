"""Neo4j loading assets for SBIR awards."""

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dagster import AssetCheckResult, AssetCheckSeverity, AssetExecutionContext, Output, asset, asset_check
from loguru import logger

from ..config.loader import get_config
from ..loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig
from ..models.award import Award

# State name to code mapping
STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "guam": "GU", "virgin islands": "VI", "american samoa": "AS",
    "northern mariana islands": "MP",
}


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


@asset(
    description="Load validated SBIR awards into Neo4j with Award, Company, Researcher, and Institution nodes",
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
    - Company nodes (deduplicated by UEI/DUNS/Name)
    - Researcher nodes (from PI fields, deduplicated by name+email)
    - ResearchInstitution nodes (from RI fields, deduplicated by name)

    Creates the following relationships:
    - (Award)-[AWARDED_TO]->(Company)
    - (Award)-[RESEARCHED_BY]->(Researcher)
    - (Award)-[CONDUCTED_AT]->(ResearchInstitution)
    - (Researcher)-[WORKED_ON]->(Award)
    - (Researcher)-[WORKED_AT]->(Company)

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
        # Ensure constraints exist
        client.create_constraints()
        client.create_indexes()

        # Convert DataFrame rows to Award models, then to Neo4j node properties
        award_nodes = []
        company_nodes_map: dict[str, dict[str, Any]] = {}
        researcher_nodes_map: dict[str, dict[str, Any]] = {}
        institution_nodes_map: dict[str, dict[str, Any]] = {}
        award_company_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []
        award_researcher_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []
        award_institution_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []
        researcher_award_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []  # WORKED_ON
        researcher_company_rels: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []  # WORKED_AT

        # Track skip reasons
        skipped_zero_amount = 0
        skipped_no_company_id = 0
        validation_errors = 0
        companies_by_name_only = 0  # Track companies identified by name only

        for _, row in validated_sbir_awards.iterrows():
            try:
                # Convert row dict to Award model
                # Normalize column names: lowercase and replace spaces with underscores
                # Also convert pandas NaN to None for proper Pydantic validation
                row_dict = row.to_dict()
                normalized_dict = {}
                for key, value in row_dict.items():
                    normalized_key = key.lower().replace(" ", "_")
                    # Convert pandas NaN/NA to None
                    if pd.isna(value):
                        normalized_dict[normalized_key] = None
                    else:
                        # Special handling for state - convert full name to 2-letter code
                        if normalized_key == "state" and isinstance(value, str):
                            state_lower = value.strip().lower()
                            normalized_dict[normalized_key] = STATE_NAME_TO_CODE.get(state_lower, value)
                        # Special handling for number_employees - convert float to int
                        # (CSV has "Number Employees", not "Number Of Employees")
                        elif normalized_key == "number_employees" and isinstance(value, float):
                            # Only convert if it's a whole number (no fractional part)
                            if value.is_integer():
                                normalized_dict[normalized_key] = int(value)
                            else:
                                normalized_dict[normalized_key] = value
                        # Special handling for zip - convert '-' placeholder to None
                        elif normalized_key == "zip" and isinstance(value, str) and value.strip() == "-":
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
                        elif normalized_key in ("hubzone_owned", "woman_owned", "socially_and_economically_disadvantaged") and value == "U":
                            normalized_dict[normalized_key] = None
                        else:
                            normalized_dict[normalized_key] = value

                # Skip records with zero or missing award amounts (likely cancelled/placeholder awards)
                award_amount = normalized_dict.get("award_amount")
                if award_amount is None or (isinstance(award_amount, (int, float)) and award_amount <= 0):
                    # Try to identify the award for logging
                    tracking = normalized_dict.get("agency_tracking_number", "")
                    contract = normalized_dict.get("contract", "")
                    company = normalized_dict.get("company", "")
                    award_id_hint = f"{tracking[:20] if tracking else contract[:20] if contract else company[:30]}"

                    if skipped_zero_amount < 10:  # Only log first 10 to avoid spam
                        logger.debug(f"Skipping award with zero/missing amount: {award_id_hint} (amount={award_amount})")
                    skipped_zero_amount += 1
                    metrics.errors += 1
                    continue

                award = Award.from_sbir_csv(normalized_dict)

                # Create Award node properties
                award_props = {
                    "award_id": award.award_id,
                    "company_name": award.company_name,
                    "award_amount": award.award_amount,
                    "award_date": award.award_date.isoformat() if award.award_date else None,
                    "program": award.program,
                    "phase": award.phase,
                    "agency": award.agency,
                    "branch": award.branch,
                    "contract": award.contract,
                    "award_year": award.award_year,
                    "award_title": award.award_title,
                    "abstract": award.abstract,
                }

                # Add optional fields if present (for backward compatibility, but we'll also create separate nodes)
                if award.company_uei:
                    award_props["company_uei"] = award.company_uei
                if award.company_duns:
                    award_props["company_duns"] = award.company_duns

                award_nodes.append(award_props)

                # Create Company node with fallback hierarchy: UEI > DUNS > Name
                company_id = None
                company_id_type = None  # Track identification method

                if award.company_uei:
                    company_id = award.company_uei
                    company_id_type = "uei"
                elif award.company_duns:
                    company_id = f"DUNS:{award.company_duns}"
                    company_id_type = "duns"
                elif award.company_name:
                    # Use normalized company name as final fallback
                    normalized_name = award.company_name.strip().lower()
                    company_id = f"NAME:{normalized_name}"
                    company_id_type = "name"
                    companies_by_name_only += 1
                else:
                    # Track awards without any company identifier
                    if skipped_no_company_id < 10:
                        logger.debug(f"Award {award.award_id} has no company name, UEI, or DUNS")
                    skipped_no_company_id += 1

                if company_id:
                    if company_id not in company_nodes_map:
                        company_props = {
                            "company_id": company_id,
                            "name": award.company_name,
                            "id_type": company_id_type,  # Track identification method
                        }
                        if award.company_uei:
                            company_props["uei"] = award.company_uei
                        if award.company_duns:
                            company_props["duns"] = award.company_duns
                        if award.company_city:
                            company_props["city"] = award.company_city
                        if award.company_state:
                            company_props["state"] = award.company_state
                        if award.company_zip:
                            company_props["zip"] = award.company_zip
                        company_nodes_map[company_id] = company_props

                    # Create AWARDED_TO relationship
                    award_company_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "Company",
                            "company_id",
                            company_id,
                            "AWARDED_TO",
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
                        researcher_props = {
                            "researcher_id": researcher_id,
                            "name": pi_name,
                        }
                        if pi_email:
                            researcher_props["email"] = pi_email
                        if award.pi_title:
                            researcher_props["title"] = award.pi_title
                        if award.pi_phone:
                            researcher_props["phone"] = award.pi_phone
                        researcher_nodes_map[researcher_id] = researcher_props

                    # Create RESEARCHED_BY relationship (Award -> Researcher)
                    award_researcher_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "Researcher",
                            "researcher_id",
                            researcher_id,
                            "RESEARCHED_BY",
                            None,
                        )
                    )

                    # Create WORKED_ON relationship (Researcher -> Award)
                    researcher_award_rels.append(
                        (
                            "Researcher",
                            "researcher_id",
                            researcher_id,
                            "Award",
                            "award_id",
                            award.award_id,
                            "WORKED_ON",
                            None,
                        )
                    )

                    # Create WORKED_AT relationship (Researcher -> Company) if company exists
                    if company_id:
                        researcher_company_rels.append(
                            (
                                "Researcher",
                                "researcher_id",
                                researcher_id,
                                "Company",
                                "company_id",
                                company_id,
                                "WORKED_AT",
                                None,
                            )
                        )

                # Create Research Institution node if RI name available
                if award.research_institution:
                    institution_name = award.research_institution.strip()

                    if institution_name not in institution_nodes_map:
                        institution_props = {
                            "name": institution_name,
                        }
                        if award.ri_poc_name:
                            institution_props["poc_name"] = award.ri_poc_name
                        if award.ri_poc_phone:
                            institution_props["poc_phone"] = award.ri_poc_phone
                        institution_nodes_map[institution_name] = institution_props

                    # Create CONDUCTED_AT relationship
                    award_institution_rels.append(
                        (
                            "Award",
                            "award_id",
                            award.award_id,
                            "ResearchInstitution",
                            "name",
                            institution_name,
                            "CONDUCTED_AT",
                            None,
                        )
                    )

            except Exception as e:
                if validation_errors < 10:  # Only log first 10 validation errors
                    logger.warning(f"Failed to process award row: {e}")
                validation_errors += 1
                metrics.errors += 1

        # Load Company nodes first
        if company_nodes_map:
            company_nodes_list = list(company_nodes_map.values())
            company_metrics = client.batch_upsert_nodes(
                label="Company", key_property="company_id", nodes=company_nodes_list, metrics=metrics
            )
            metrics = company_metrics
            context.log.info(f"Loaded {len(company_nodes_list)} Company nodes")

        # Load Award nodes
        if award_nodes:
            award_metrics = client.batch_upsert_nodes(
                label="Award", key_property="award_id", nodes=award_nodes, metrics=metrics
            )
            metrics = award_metrics
            context.log.info(f"Loaded {len(award_nodes)} Award nodes")

        # Load Researcher nodes
        if researcher_nodes_map:
            researcher_nodes_list = list(researcher_nodes_map.values())
            researcher_metrics = client.batch_upsert_nodes(
                label="Researcher", key_property="researcher_id", nodes=researcher_nodes_list, metrics=metrics
            )
            metrics = researcher_metrics
            context.log.info(f"Loaded {len(researcher_nodes_list)} Researcher nodes")

        # Load Research Institution nodes
        if institution_nodes_map:
            institution_nodes_list = list(institution_nodes_map.values())
            institution_metrics = client.batch_upsert_nodes(
                label="ResearchInstitution", key_property="name", nodes=institution_nodes_list, metrics=metrics
            )
            metrics = institution_metrics
            context.log.info(f"Loaded {len(institution_nodes_list)} ResearchInstitution nodes")

        # Create AWARDED_TO relationships (Award -> Company)
        if award_company_rels:
            rel_metrics = client.batch_create_relationships(award_company_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(award_company_rels)} AWARDED_TO relationships")

        # Create RESEARCHED_BY relationships (Award -> Researcher)
        if award_researcher_rels:
            rel_metrics = client.batch_create_relationships(award_researcher_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(award_researcher_rels)} RESEARCHED_BY relationships")

        # Create CONDUCTED_AT relationships (Award -> ResearchInstitution)
        if award_institution_rels:
            rel_metrics = client.batch_create_relationships(award_institution_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(award_institution_rels)} CONDUCTED_AT relationships")

        # Create WORKED_ON relationships (Researcher -> Award)
        if researcher_award_rels:
            rel_metrics = client.batch_create_relationships(researcher_award_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(researcher_award_rels)} WORKED_ON relationships")

        # Create WORKED_AT relationships (Researcher -> Company)
        if researcher_company_rels:
            rel_metrics = client.batch_create_relationships(researcher_company_rels, metrics=metrics)
            metrics = rel_metrics
            context.log.info(f"Created {len(researcher_company_rels)} WORKED_AT relationships")

        # Log comprehensive summary of processing results
        total_rows = len(validated_sbir_awards)
        successfully_processed = len(award_nodes)
        # Only count actual failures (zero amounts and validation errors), not missing company IDs
        # Awards without company IDs are still successfully processed, just not linked to companies
        total_failed = skipped_zero_amount + validation_errors

        logger.info("=" * 80)
        logger.info("Neo4j SBIR Awards Loading Summary")
        logger.info("=" * 80)
        logger.info(f"Total rows processed: {total_rows}")
        logger.info(f"Successfully processed: {successfully_processed} ({successfully_processed/total_rows*100:.1f}%)")
        logger.info(f"Failed to process: {total_failed} ({total_failed/total_rows*100:.1f}%)")
        logger.info("")
        logger.info("Processing Issues:")
        logger.info(f"  • Zero/missing award amount: {skipped_zero_amount} ({skipped_zero_amount/total_rows*100:.1f}%)")
        logger.info(f"  • Validation errors: {validation_errors} ({validation_errors/total_rows*100:.1f}%)")
        logger.info(f"  • Awards without any company identifier: {skipped_no_company_id} ({skipped_no_company_id/total_rows*100:.1f}%)")
        logger.info("")
        logger.info("Nodes Created/Updated:")
        logger.info(f"  • Awards: {len(award_nodes)} nodes")
        logger.info(f"  • Companies: {len(company_nodes_map)} unique nodes")
        logger.info(f"    - Identified by name only: {companies_by_name_only} ({companies_by_name_only/len(company_nodes_map)*100:.1f}% of companies)")
        logger.info(f"  • Researchers: {len(researcher_nodes_map)} unique nodes")
        logger.info(f"  • Research Institutions: {len(institution_nodes_map)} unique nodes")
        logger.info("")
        logger.info("Relationships Created:")
        logger.info(f"  • AWARDED_TO (Award → Company): {len(award_company_rels)} relationships")
        logger.info(f"  • RESEARCHED_BY (Award → Researcher): {len(award_researcher_rels)} relationships")
        logger.info(f"  • CONDUCTED_AT (Award → Institution): {len(award_institution_rels)} relationships")
        logger.info(f"  • WORKED_ON (Researcher → Award): {len(researcher_award_rels)} relationships")
        logger.info(f"  • WORKED_AT (Researcher → Company): {len(researcher_company_rels)} relationships")
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
                "validation_errors": validation_errors,
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
            metadata={
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
            description=f"✗ Too many load errors: {errors}/{total_rows} ({error_rate*100:.1f}% > {error_rate_threshold*100:.0f}% threshold)",
            metadata={"errors": errors, "total_rows": total_rows, "error_rate": error_rate, "threshold": error_rate_threshold},
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
        description=f"✓ Neo4j load successful: {awards_loaded} awards, {neo4j_sbir_awards.get('researchers_loaded', 0)} researchers, {neo4j_sbir_awards.get('institutions_loaded', 0)} institutions ({error_rate*100:.1f}% error rate)",
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


"""Neo4j loading assets for SBIR awards."""

import json
import os
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

from sbir_etl.config.loader import get_config
from sbir_etl.models.award import Award
from sbir_etl.utils.company_canonicalizer import canonicalize_companies_from_awards

try:
    from sbir_graph.loaders.neo4j import LoadMetrics, Neo4jClient, Neo4jConfig
    from sbir_graph.loaders.neo4j.organizations import OrganizationLoader
except ImportError:
    LoadMetrics = None  # type: ignore[assignment, misc]
    Neo4jClient = None  # type: ignore[assignment, misc]
    Neo4jConfig = None  # type: ignore[assignment, misc]
    OrganizationLoader = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# Legal suffixes stripped during normalization.
_LEGAL_SUFFIXES = [
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

# Standardized abbreviations applied after suffix removal.
_ABBREVIATION_REPLACEMENTS = {
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

_PHASE_NEXT = {"I": "II", "II": "III"}

_BOOL_FIELDS_WITH_UNKNOWN = (
    "hubzone_owned",
    "woman_owned",
    "socially_and_economically_disadvantaged",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_company_name(name: str) -> str:
    """Normalize a company name for cross-record matching.

    Lowercases, strips punctuation, removes legal suffixes (Inc/Corp/LLC/etc.),
    standardizes abbreviations, and collapses whitespace.

    Example:
        >>> normalize_company_name("Acme Technologies, Inc.")
        'acme tech'
    """
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", " ", s).replace("-", " ")
    for pattern in _LEGAL_SUFFIXES:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    for pattern, repl in _ABBREVIATION_REPLACEMENTS.items():
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    return " ".join(s.split()).strip()


def _company_id_for_award(award: Award) -> str | None:
    """Return UEI / DUNS-prefixed / NAME-prefixed identifier (in that priority)."""
    if award.company_uei:
        return award.company_uei
    if award.company_duns:
        return f"DUNS:{award.company_duns}"
    if award.company_name:
        normalized = normalize_company_name(award.company_name)
        if normalized:
            return f"NAME:{normalized}"
    return None


def _get_neo4j_client() -> "Neo4jClient | None":
    """Open a Neo4j connection from config; return None when SKIP_NEO4J_LOADING is set."""
    skip_neo4j = os.getenv("SKIP_NEO4J_LOADING", "false").lower() in ("true", "1", "yes")
    try:
        neo4j_config = get_config().neo4j
        client = Neo4jClient(
            Neo4jConfig(
                uri=neo4j_config.uri,
                username=neo4j_config.username,
                password=neo4j_config.password,
                database=neo4j_config.database,
                batch_size=neo4j_config.batch_size,
            )
        )
        with client.session() as session:
            session.run("RETURN 1")
        return client
    except Exception as e:
        if skip_neo4j:
            logger.warning(f"Neo4j unavailable but skipping: {e}")
            return None
        raise RuntimeError(
            f"Neo4j connection failed but Neo4j loading not skipped: {e}. "
            "Set SKIP_NEO4J_LOADING=true to skip."
        )


# ---------------------------------------------------------------------------
# Phase-progression detection
# ---------------------------------------------------------------------------


def detect_award_progressions(
    awards: list[Award],
) -> list[tuple[str, str, str, str, str, str, str, dict[str, Any] | None]]:
    """Detect Phase I → II → III progressions across awards.

    Matches awards from the same company (UEI/DUNS/normalized-name), same agency,
    same program, sequential phases, chronological order. Confidence scoring adds
    +0.3 for same topic code, +0.2 for same PI, +0.1 for 1–4 year gap.

    Returns: list of relationship tuples in `batch_create_relationships` format
    (source_label, source_key, source_id, target_label, target_key, target_id,
    rel_type, properties). All relationships are FinancialTransaction → FinancialTransaction
    with rel_type "FOLLOWS".
    """
    by_company: dict[str, list[Award]] = {}
    for award in awards:
        if award.phase not in ("I", "II", "III"):
            continue
        company_id = _company_id_for_award(award)
        if company_id:
            by_company.setdefault(company_id, []).append(award)

    progressions: list[tuple] = []
    for company_award_list in by_company.values():
        sorted_awards = sorted(company_award_list, key=lambda a: a.award_date or date(1900, 1, 1))
        for i, earlier in enumerate(sorted_awards):
            next_phase = _PHASE_NEXT.get(earlier.phase or "")
            if not next_phase:
                continue
            for later in sorted_awards[i + 1 :]:
                if later.phase != next_phase:
                    continue
                if earlier.agency != later.agency or earlier.program != later.program:
                    continue
                if earlier.award_date and later.award_date:
                    if earlier.award_date >= later.award_date:
                        continue
                    years_between: float | None = (
                        later.award_date - earlier.award_date
                    ).days / 365.25
                else:
                    years_between = None

                same_topic = bool(
                    earlier.topic_code
                    and later.topic_code
                    and earlier.topic_code == later.topic_code
                )
                same_pi = bool(
                    earlier.principal_investigator
                    and later.principal_investigator
                    and earlier.principal_investigator.lower()
                    == later.principal_investigator.lower()
                )

                confidence = 0.5
                if same_topic:
                    confidence += 0.3
                if same_pi:
                    confidence += 0.2
                if years_between is not None and 1 <= years_between <= 4:
                    confidence += 0.1

                props: dict[str, Any] = {
                    "phase_progression": f"{earlier.phase}_to_{next_phase}",
                    "confidence": round(confidence, 2),
                    "same_topic": same_topic,
                    "same_pi": same_pi,
                }
                if years_between is not None:
                    props["years_between"] = round(years_between, 2)

                progressions.append(
                    (
                        "FinancialTransaction",
                        "transaction_id",
                        f"txn_award_{earlier.award_id}",
                        "FinancialTransaction",
                        "transaction_id",
                        f"txn_award_{later.award_id}",
                        "FOLLOWS",
                        props,
                    )
                )
                # Only match each earlier award to the first qualifying later award.
                break
    return progressions  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Row normalization & Award construction
# ---------------------------------------------------------------------------


def _normalize_row(row: pd.Series) -> dict[str, Any]:
    """Convert a CSV row to the dict shape expected by Award.from_sbir_csv.

    Normalizes column names, replaces NaN/NA with None, and applies a few
    field-specific fixups (state name→code, employee count cast, DUNS padding,
    'U' boolean handling).
    """
    out: dict[str, Any] = {}
    for key, value in row.to_dict().items():
        nk = key.lower().replace(" ", "_")
        if pd.isna(value):
            out[nk] = None
            continue
        if nk == "state" and isinstance(value, str):
            out[nk] = STATE_NAME_TO_CODE.get(value.strip().lower(), value)
        elif nk == "number_employees" and isinstance(value, float) and value.is_integer():
            out[nk] = int(value)
        elif nk == "zip" and isinstance(value, str) and value.strip() == "-":
            out[nk] = None
        elif nk == "duns" and isinstance(value, str):
            digits = "".join(ch for ch in value if ch.isdigit())
            out[nk] = digits.zfill(9) if 7 <= len(digits) <= 8 else value
        elif nk in _BOOL_FIELDS_WITH_UNKNOWN and value == "U":
            out[nk] = None
        else:
            out[nk] = value
    return out


def _award_id_hint(normalized: dict[str, Any]) -> str:
    """Best-effort short identifier for logging when Award validation fails."""
    tracking = normalized.get("agency_tracking_number") or ""
    contract = normalized.get("contract") or ""
    company = normalized.get("company_name") or ""
    return tracking[:20] or contract[:20] or company[:30]


def _is_date_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("date", "future", "before", "after", "time", "year"))


def _try_create_award(normalized: dict[str, Any]) -> tuple[Award | None, str]:
    """Build an Award from a normalized row.

    Returns (award, status). status is one of:
      - "ok"         — created successfully
      - "ok_minimal" — created with date fields zeroed after a date validation failure
      - "date_error" — date-related failure, even minimal Award couldn't be built
      - "error"      — other validation failure
    """
    try:
        return Award.from_sbir_csv(normalized), "ok"
    except Exception as e:
        if not _is_date_error(e):
            return None, "error"
        try:
            return (
                Award(
                    award_id=normalized.get("award_id", ""),
                    company_name=normalized.get("company_name", ""),
                    award_amount=normalized.get("award_amount", 0.0),
                    award_date=None,
                    program=normalized.get("program"),
                    phase=normalized.get("phase"),
                    agency=normalized.get("agency"),
                    company_uei=normalized.get("company_uei"),
                    company_duns=normalized.get("company_duns"),
                ),
                "ok_minimal",
            )
        except Exception:
            return None, "date_error"


# ---------------------------------------------------------------------------
# Node-property builders
# ---------------------------------------------------------------------------


def _transaction_props(award: Award) -> dict[str, Any]:
    """Build the FinancialTransaction node properties for an SBIR award."""
    props: dict[str, Any] = {
        "transaction_id": f"txn_award_{award.award_id}",
        "transaction_type": "AWARD",
        "award_id": award.award_id,
        "recipient_name": award.company_name,
        "amount": award.award_amount,
        "transaction_date": award.award_date.isoformat() if award.award_date else None,
        "program": award.program,
        "phase": award.phase,
        "agency": award.agency,
        "agency_name": award.agency,
        "sub_agency": award.branch,
        "title": award.award_title,
        "description": award.abstract,
        "award_year": award.award_year,
        "fiscal_year": award.fiscal_year,
        "principal_investigator": award.principal_investigator,
        "research_institution": award.research_institution,
        "completion_date": (
            award.contract_end_date.isoformat() if award.contract_end_date else None
        ),
        "start_date": (
            award.contract_start_date.isoformat() if award.contract_start_date else None
        ),
        "end_date": award.contract_end_date.isoformat() if award.contract_end_date else None,
    }
    if award.company_uei:
        props["recipient_uei"] = award.company_uei
    if award.company_duns:
        props["recipient_duns"] = award.company_duns
    if award.company_cage:
        props["recipient_cage"] = award.company_cage
    naics = getattr(award, "naics_primary", None)
    if naics:
        props["naics_code"] = naics
    return props


def _company_node_props(
    award: Award, *, company_id: str, id_type: str, normalized_name: str
) -> dict[str, Any]:
    props: dict[str, Any] = {
        "organization_id": f"org_company_{company_id}",
        "company_id": company_id,
        "name": award.company_name,
        "normalized_name": normalized_name,
        "organization_type": "COMPANY",
        "source_contexts": ["SBIR"],
        "id_type": id_type,
    }
    if award.company_uei:
        props["uei"] = award.company_uei
    if award.company_duns:
        props["duns"] = award.company_duns
    if award.company_city:
        props["city"] = award.company_city
    if award.company_state:
        props["state"] = award.company_state
    if award.company_zip:
        props["postcode"] = award.company_zip
    return props


def _update_company_crosswalk(existing: dict[str, Any], award: Award) -> None:
    """Cross-walk additional identifiers / location onto an existing Organization."""
    if award.company_uei and not existing.get("uei"):
        existing["uei"] = award.company_uei
    if award.company_duns and not existing.get("duns"):
        existing["duns"] = award.company_duns
    if award.company_city and not existing.get("city"):
        existing["city"] = award.company_city
    if award.company_state and not existing.get("state"):
        existing["state"] = award.company_state
    if award.company_zip and not existing.get("postcode"):
        existing["postcode"] = award.company_zip


def _resolve_canonical_company(
    award: Award, canonical_map: dict[str, str], normalized_name: str
) -> tuple[str | None, str | None, bool]:
    """Resolve canonical company ID + id_type from the pre-loading dedup map.

    Returns (company_id, id_type, name_only_fallback) where name_only_fallback is
    True when the fallback name-based path was used (used for telemetry).
    """
    if award.company_uei:
        original_key = award.company_uei
    elif award.company_duns:
        original_key = f"DUNS:{award.company_duns}"
    elif normalized_name:
        original_key = f"NAME:{normalized_name}"
    else:
        return None, None, False

    canonical = canonical_map.get(original_key)
    if canonical:
        if canonical.startswith("UEI:"):
            return canonical[4:], "uei", False
        if canonical.startswith("DUNS:"):
            return canonical[5:], "duns", False
        return canonical, "name", False

    # Fallback: use original identifier (no canonical mapping found).
    if award.company_uei:
        return award.company_uei, "uei", False
    if award.company_duns:
        return f"DUNS:{award.company_duns}", "duns", False
    if normalized_name:
        return f"NAME:{normalized_name}", "name", True
    return None, None, False


# ---------------------------------------------------------------------------
# Main asset
# ---------------------------------------------------------------------------


def _load_nodes(
    client: "Neo4jClient",
    *,
    label: str,
    key: str,
    nodes_map: dict[str, dict[str, Any]],
    metrics: "LoadMetrics",
    description: str,
    context: AssetExecutionContext,
) -> "LoadMetrics":
    """Upsert a node map and log the count."""
    if not nodes_map:
        return metrics
    nodes = list(nodes_map.values())
    new_metrics = client.batch_upsert_nodes(
        label=label, key_property=key, nodes=nodes, metrics=metrics
    )
    context.log.info(f"Loaded {len(nodes)} {label} nodes ({description})")
    return new_metrics


@asset(
    description="Load validated SBIR awards into Neo4j with Award, Organization, Individual, and Institution nodes",
    group_name="neo4j_loading",
    compute_kind="neo4j",
)
def neo4j_sbir_awards(
    context: AssetExecutionContext, validated_sbir_awards: pd.DataFrame
) -> Output[dict[str, Any]]:
    """Load validated SBIR awards into Neo4j.

    Creates FinancialTransaction (AWARD) nodes, Organization nodes for companies /
    research institutions / agencies / sub-agencies, and Individual nodes for PIs.
    Creates RECIPIENT_OF, PARTICIPATED_IN, CONDUCTED_AT, WORKED_AT, FUNDED_BY,
    SUBSIDIARY_OF, and FOLLOWS (phase-progression) relationships.
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
        # Legacy: migrations own constraints/indexes, but keep these for backward compat.
        client.create_constraints()
        client.create_indexes()

        dedup_config = get_config().transformation.company_deduplication  # type: ignore[attr-defined]
        context.log.info("Pre-processing: Canonicalizing companies...")
        canonical_map = canonicalize_companies_from_awards(
            validated_sbir_awards,
            high_threshold=dedup_config.get("high_threshold", 90),
            low_threshold=dedup_config.get("low_threshold", 75),
            enhanced_config=dedup_config.get("enhanced_matching"),
        )
        context.log.info(f"Canonicalized {len(canonical_map)} companies")

        award_nodes: list[dict[str, Any]] = []
        award_objects: list[Award] = []
        company_nodes_map: dict[str, dict[str, Any]] = {}
        researcher_nodes_map: dict[str, dict[str, Any]] = {}
        institution_nodes_map: dict[str, dict[str, Any]] = {}
        award_company_rels: list[tuple] = []
        award_institution_rels: list[tuple] = []
        researcher_award_rels: list[tuple] = []
        researcher_company_rels: list[tuple] = []

        # Error counters (logged at end; first 10 of each kind go to debug log).
        skipped_zero_amount = 0
        skipped_no_company_id = 0
        validation_errors = 0
        date_validation_errors = 0
        companies_by_name_only = 0

        for _, row in validated_sbir_awards.iterrows():
            try:
                normalized = _normalize_row(row)
                award, status = _try_create_award(normalized)

                if status == "error":
                    if validation_errors < 10:
                        logger.warning(f"Award validation failed for {_award_id_hint(normalized)}")
                    validation_errors += 1
                    metrics.errors += 1
                    continue
                if status == "date_error":
                    if validation_errors < 10:
                        logger.warning(
                            f"Award validation failed for {_award_id_hint(normalized)} (date)"
                        )
                    validation_errors += 1
                    metrics.errors += 1
                    continue
                if status == "ok_minimal":
                    if date_validation_errors < 10:
                        logger.warning(
                            f"Date validation failed for {_award_id_hint(normalized)}, "
                            "using minimal Award"
                        )
                    date_validation_errors += 1
                assert award is not None  # for type-checkers

                transaction_id = f"txn_award_{award.award_id}"
                award_nodes.append(_transaction_props(award))
                award_objects.append(award)

                normalized_name = normalize_company_name(award.company_name or "")
                company_id, id_type, name_only_fallback = _resolve_canonical_company(
                    award, canonical_map, normalized_name
                )
                if name_only_fallback:
                    companies_by_name_only += 1

                if company_id is None:
                    if skipped_no_company_id < 10:
                        logger.debug(f"Award {award.award_id} has no company name, UEI, or DUNS")
                    skipped_no_company_id += 1
                else:
                    organization_id = f"org_company_{company_id}"
                    if company_id not in company_nodes_map:
                        company_nodes_map[company_id] = _company_node_props(
                            award,
                            company_id=company_id,
                            id_type=id_type or "name",
                            normalized_name=normalized_name,
                        )
                    else:
                        _update_company_crosswalk(company_nodes_map[company_id], award)

                    award_company_rels.append(
                        (
                            "FinancialTransaction",
                            "transaction_id",
                            transaction_id,
                            "Organization",
                            "organization_id",
                            organization_id,
                            "RECIPIENT_OF",
                            None,
                        )
                    )

                # Researcher node (PI) and PARTICIPATED_IN / WORKED_AT relationships.
                if award.principal_investigator:
                    pi_name = award.principal_investigator.strip()
                    pi_email = award.pi_email.strip() if award.pi_email else None
                    researcher_id = f"{pi_name}|{pi_email}".lower() if pi_email else pi_name.lower()
                    individual_id = f"ind_researcher_{researcher_id}"

                    if researcher_id not in researcher_nodes_map:
                        props: dict[str, Any] = {
                            "individual_id": individual_id,
                            "researcher_id": researcher_id,
                            "name": pi_name,
                            "normalized_name": pi_name.upper(),
                            "individual_type": "RESEARCHER",
                            "source_contexts": ["SBIR"],
                        }
                        if pi_email:
                            props["email"] = pi_email
                        if award.pi_title:
                            props["title"] = award.pi_title
                        if award.pi_phone:
                            props["phone"] = award.pi_phone
                        researcher_nodes_map[researcher_id] = props

                    researcher_award_rels.append(
                        (
                            "Individual",
                            "individual_id",
                            individual_id,
                            "FinancialTransaction",
                            "transaction_id",
                            transaction_id,
                            "PARTICIPATED_IN",
                            {"role": "RESEARCHER"},
                        )
                    )
                    if company_id:
                        researcher_company_rels.append(
                            (
                                "Individual",
                                "individual_id",
                                individual_id,
                                "Organization",
                                "organization_id",
                                f"org_company_{company_id}",
                                "WORKED_AT",
                                None,
                            )
                        )

                # Research institution node + CONDUCTED_AT relationship.
                if award.research_institution:
                    institution_name = award.research_institution.strip()
                    institution_org_id = f"org_research_{institution_name}"
                    if institution_name not in institution_nodes_map:
                        ri_props: dict[str, Any] = {
                            "organization_id": institution_org_id,
                            "name": institution_name,
                            "normalized_name": institution_name.upper(),
                            "organization_type": "UNIVERSITY",
                            "source_contexts": ["RESEARCH"],
                        }
                        if award.ri_poc_name:
                            ri_props["poc_name"] = award.ri_poc_name
                        if award.ri_poc_phone:
                            ri_props["poc_phone"] = award.ri_poc_phone
                        institution_nodes_map[institution_name] = ri_props

                    award_institution_rels.append(
                        (
                            "FinancialTransaction",
                            "transaction_id",
                            transaction_id,
                            "Organization",
                            "organization_id",
                            institution_org_id,
                            "CONDUCTED_AT",
                            None,
                        )
                    )

            except Exception as e:
                if _is_date_error(e):
                    if date_validation_errors < 10:
                        logger.warning(f"Date validation error: {e}")
                    date_validation_errors += 1
                else:
                    if validation_errors < 10:
                        logger.warning(f"Failed to process award row: {e}")
                    validation_errors += 1
                metrics.errors += 1

        # Companies use a multi-key MERGE (UEI ∪ DUNS) so they cross-walk correctly.
        if company_nodes_map:
            nodes = list(company_nodes_map.values())
            metrics = client.batch_upsert_organizations_with_multi_key(
                nodes=nodes,
                metrics=metrics,
                merge_on_uei=dedup_config.get("merge_on_uei", True),
                merge_on_duns=dedup_config.get("merge_on_duns", True),
                track_merge_history=dedup_config.get("track_merge_history", True),
            )
            context.log.info(
                f"Loaded {len(nodes)} Organization nodes (companies): "
                f"{metrics.nodes_created.get('Organization', 0)} created, "
                f"{metrics.nodes_updated.get('Organization', 0)} updated"
            )

        if award_nodes:
            metrics = client.batch_upsert_nodes(
                label="FinancialTransaction",
                key_property="transaction_id",
                nodes=award_nodes,
                metrics=metrics,
            )
            context.log.info(f"Loaded {len(award_nodes)} FinancialTransaction nodes (AWARD type)")

        metrics = _load_nodes(
            client,
            label="Individual",
            key="individual_id",
            nodes_map=researcher_nodes_map,
            metrics=metrics,
            description="researchers",
            context=context,
        )
        metrics = _load_nodes(
            client,
            label="Organization",
            key="organization_id",
            nodes_map=institution_nodes_map,
            metrics=metrics,
            description="research institutions",
            context=context,
        )

        for rels, desc in (
            (award_company_rels, "RECIPIENT_OF (FinancialTransaction → Organization)"),
            (award_institution_rels, "CONDUCTED_AT (FinancialTransaction → Organization)"),
            (researcher_award_rels, "PARTICIPATED_IN (Individual → FinancialTransaction)"),
            (researcher_company_rels, "WORKED_AT (Individual → Organization)"),
        ):
            if rels:
                metrics = client.batch_create_relationships(rels, metrics=metrics)
                context.log.info(f"Created {len(rels)} {desc} relationships")

        # FUNDED_BY: agency Organization nodes + sub-agency hierarchy.
        agency_orgs_map: dict[str, dict[str, Any]] = {}
        sub_agency_orgs_map: dict[str, dict[str, Any]] = {}
        award_agency_rels: list[tuple] = []
        agency_subsidiary_pairs: list[tuple] = []

        for award in award_objects:
            agency_code = award.agency
            agency_name = getattr(award, "agency_name", award.agency)
            if not (agency_code and agency_name):
                continue

            parent_organization_id = f"org_agency_{agency_code}"
            if parent_organization_id not in agency_orgs_map:
                agency_orgs_map[parent_organization_id] = {
                    "organization_id": parent_organization_id,
                    "name": agency_name,
                    "normalized_name": agency_name.upper(),
                    "organization_type": "AGENCY",
                    "source_contexts": ["AGENCY"],
                    "agency_code": agency_code,
                    "agency_name": agency_name,
                }

            target_organization_id = parent_organization_id
            sub_agency_code = getattr(award, "sub_agency", None)
            sub_agency_name = getattr(award, "sub_agency_name", None)
            if award.branch and sub_agency_code:
                sub_agency_name = sub_agency_name or award.branch
                sub_organization_id = f"org_agency_{agency_code}_{sub_agency_code}"
                if sub_organization_id not in sub_agency_orgs_map:
                    sub_agency_orgs_map[sub_organization_id] = {
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
                agency_subsidiary_pairs.append(
                    (
                        "organization_id",
                        sub_organization_id,
                        "organization_id",
                        parent_organization_id,
                    )
                )
                target_organization_id = sub_organization_id

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

        metrics = _load_nodes(
            client,
            label="Organization",
            key="organization_id",
            nodes_map=agency_orgs_map,
            metrics=metrics,
            description="parent agencies",
            context=context,
        )
        metrics = _load_nodes(
            client,
            label="Organization",
            key="organization_id",
            nodes_map=sub_agency_orgs_map,
            metrics=metrics,
            description="sub-agencies",
            context=context,
        )

        if award_agency_rels:
            metrics = client.batch_create_relationships(award_agency_rels, metrics=metrics)  # type: ignore[arg-type]
            context.log.info(
                f"Created {len(award_agency_rels)} FUNDED_BY relationships "
                "(FinancialTransaction → Organization)"
            )
        if agency_subsidiary_pairs:
            metrics = OrganizationLoader(client).create_subsidiary_relationships(
                agency_subsidiary_pairs,
                source="AGENCY_HIERARCHY",
            )
            context.log.info(
                f"Created {len(agency_subsidiary_pairs)} SUBSIDIARY_OF relationships "
                "(sub-agency → parent agency)"
            )

        # FOLLOWS: phase progressions.
        context.log.info("Detecting award phase progressions...")
        follows_rels = detect_award_progressions(award_objects)
        if follows_rels:
            metrics = client.batch_create_relationships(follows_rels, metrics=metrics)
            context.log.info(
                f"Created {len(follows_rels)} FOLLOWS relationships for award progressions"
            )
        else:
            context.log.info("No award progressions detected")

        # Summary logging.
        total_rows = len(validated_sbir_awards)
        successfully_processed = len(award_nodes)
        total_failed = skipped_zero_amount + validation_errors + date_validation_errors
        pct = lambda n: (n / total_rows * 100) if total_rows else 0  # noqa: E731
        logger.info("=" * 80)
        logger.info("Neo4j SBIR Awards Loading Summary")
        logger.info("=" * 80)
        logger.info(f"Total rows processed:      {total_rows}")
        logger.info(
            f"Successfully processed:    {successfully_processed} ({pct(successfully_processed):.1f}%)"
        )
        logger.info(f"Failed to process:         {total_failed} ({pct(total_failed):.1f}%)")
        logger.info("Processing Issues:")
        logger.info(
            f"  Zero/missing amount:     {skipped_zero_amount} ({pct(skipped_zero_amount):.1f}%)"
        )
        logger.info(
            f"  Date validation errors:  {date_validation_errors} ({pct(date_validation_errors):.1f}%)"
        )
        logger.info(
            f"  Other validation errors: {validation_errors} ({pct(validation_errors):.1f}%)"
        )
        logger.info(
            f"  No company identifier:   {skipped_no_company_id} ({pct(skipped_no_company_id):.1f}%)"
        )
        logger.info("Nodes:")
        logger.info(f"  Awards:                  {len(award_nodes)}")
        company_count = len(company_nodes_map) or 1
        logger.info(
            f"  Companies:               {len(company_nodes_map)} "
            f"({companies_by_name_only} ({companies_by_name_only / company_count * 100:.1f}%) name-only)"
        )
        logger.info(f"  Researchers:             {len(researcher_nodes_map)}")
        logger.info(f"  Research Institutions:   {len(institution_nodes_map)}")
        logger.info("Relationships:")
        logger.info(f"  RECIPIENT_OF:            {len(award_company_rels)}")
        logger.info(f"  PARTICIPATED_IN:         {len(researcher_award_rels)}")
        logger.info(f"  CONDUCTED_AT:            {len(award_institution_rels)}")
        logger.info(f"  WORKED_AT:               {len(researcher_company_rels)}")
        logger.info(f"  FOLLOWS:                 {len(follows_rels)} phase progressions")
        logger.info("=" * 80)

        duration = time.time() - start_time
        result = {
            "status": "success",
            "awards_loaded": len(award_nodes),
            "awards_updated": metrics.nodes_updated.get("Award", 0),
            "companies_loaded": len(company_nodes_map),
            "companies_updated": metrics.nodes_updated.get("Company", 0),
            "researchers_loaded": len(researcher_nodes_map),
            "researchers_updated": metrics.nodes_updated.get("Researcher", 0),
            "institutions_loaded": len(institution_nodes_map),
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

        errors_meta = (
            len(result["errors"])  # type: ignore[arg-type]
            if isinstance(result.get("errors"), list)
            else 0
        )
        return Output(
            value=result,
            metadata={  # type: ignore[dict-item]
                "awards_loaded": int(result.get("awards_loaded", 0)),  # type: ignore[call-overload]
                "companies_loaded": int(result.get("companies_loaded", 0)),  # type: ignore[call-overload]
                "researchers_loaded": int(result.get("researchers_loaded", 0)),  # type: ignore[call-overload]
                "institutions_loaded": int(result.get("institutions_loaded", 0)),  # type: ignore[call-overload]
                "relationships_created": int(result.get("relationships_created", 0)),  # type: ignore[call-overload]
                "errors": errors_meta,
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
    """Fail if the loader status is not "success", error rate is too high, or no awards loaded."""
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

    error_rate = errors / total_rows if total_rows > 0 else 0
    if error_rate > 0.25:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=(
                f"✗ Too many load errors: {errors}/{total_rows} "
                f"({error_rate * 100:.1f}% > 25% threshold)"
            ),
            metadata={
                "errors": errors,
                "total_rows": total_rows,
                "error_rate": error_rate,
                "threshold": 0.25,
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
        description=(
            f"✓ Neo4j load successful: {awards_loaded} awards, "
            f"{neo4j_sbir_awards.get('researchers_loaded', 0)} researchers, "
            f"{neo4j_sbir_awards.get('institutions_loaded', 0)} institutions "
            f"({error_rate * 100:.1f}% error rate)"
        ),
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

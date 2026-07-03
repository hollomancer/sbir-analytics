"""Pure digest builders that compress enrichment data into LLM prompt context."""

from sbir_etl.enrichers.pi_enrichment import (
    PIPatentRecord,
    PIPublicationRecord,
    ORCIDRecord,
)
from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary as PIFederalAwardRecord,
    SAMEntityRecord,
)
from sbir_etl.enrichers.opencorporates import CorporateRecord
from sbir_etl.enrichers.press_wire import PressRelease

from sbir_etl.reporting.weekly.rendering import build_solicitation_url
from sbir_etl.reporting.weekly.models import CompanyResearch, SolicitationTopic


def _award_digest(
    award: dict,
    company_research: CompanyResearch | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
    corporate_record: CorporateRecord | None = None,
    press_releases: list[PressRelease] | None = None,
) -> str:
    """Build a compact text digest of an award for LLM context."""
    parts = [
        f"Title: {award.get('Award Title', 'N/A')}",
        f"Company: {award.get('Company', 'N/A')}",
        f"Agency: {award.get('Agency', 'N/A')}",
        f"Program: {award.get('Program', 'N/A')} {award.get('Phase', '')}",
        f"Amount: {award.get('Award Amount', 'N/A')}",
        f"State: {award.get('State', 'N/A')}",
        f"Date: {award.get('Proposal Award Date', 'N/A')}",
    ]
    abstract = str(award.get("Abstract", "")).strip()
    if abstract:
        if len(abstract) > 1500:
            abstract = abstract[:1500] + "..."
        parts.append(f"Abstract: {abstract}")
    topic_code = str(award.get("Topic Code", "")).strip()
    if topic_code:
        parts.append(f"Topic Code: {topic_code}")
    solicitation = str(award.get("Solicitation Number", "")).strip()
    if solicitation:
        parts.append(f"Solicitation: {solicitation}")
    solicitation_year = str(award.get("Solicitation Year", "")).strip()
    if solicitation_year:
        parts.append(f"Solicitation Year: {solicitation_year}")

    # Solicitation topic context (title + description from SBIR.gov API)
    has_sol_topic = False
    if solicitation_topics and topic_code:
        topic = solicitation_topics.get(topic_code)
        if topic:
            has_sol_topic = True
            if topic.title:
                parts.append(f"Solicitation Topic Title: {topic.title}")
            if topic.description:
                parts.append(
                    f"Solicitation Topic Description (government research need): "
                    f"{topic.description}"
                )

    contract = str(award.get("Contract", "")).strip()
    if contract:
        parts.append(f"Contract: {contract}")
        parts.append(
            f"USAspending Record: https://www.usaspending.gov/search"
            f'?form_fields={{"search_term":"{contract}"}}'
        )

    # Supplementary context from USAspending and SAM.gov when solicitation
    # topic data is unavailable — gives the LLM program/industry context.
    if not has_sol_topic:
        if usaspending_descriptions and contract:
            usa_desc = usaspending_descriptions.get(contract)
            if usa_desc:
                parts.append(
                    f"USAspending contract description (supplementary context): {usa_desc}"
                )
        company = str(award.get("Company", "")).strip()
        if sam_entities and company:
            sam = sam_entities.get(company.upper())
            if sam and sam.naics_codes:
                parts.append(
                    f"Company NAICS codes (industry classification from SAM.gov): "
                    f"{', '.join(sam.naics_codes)}"
                )

    solicitation_url = build_solicitation_url(award)
    if solicitation_url:
        parts.append(f"Solicitation Reference: {solicitation_url}")
    if company_research:
        parts.append(f"Company Background (from web research): {company_research.summary}")
        if company_research.source_urls:
            parts.append("Company Sources: " + ", ".join(company_research.source_urls[:5]))
    if corporate_record:
        oc_parts = []
        if corporate_record.incorporation_date:
            oc_parts.append(f"Incorporated: {corporate_record.incorporation_date}")
        if corporate_record.status:
            oc_parts.append(f"State filing status: {corporate_record.status}")
        if corporate_record.company_type:
            oc_parts.append(f"Entity type: {corporate_record.company_type}")
        if corporate_record.parent_company:
            oc_parts.append(f"Parent company: {corporate_record.parent_company}")
        if corporate_record.officers:
            officer_names = [o.name for o in corporate_record.officers[:3]]
            oc_parts.append(f"Officers: {', '.join(officer_names)}")
        if oc_parts:
            parts.append("State corporation filing (OpenCorporates): " + " | ".join(oc_parts))
    if press_releases:
        pr_summaries = []
        for pr in press_releases[:3]:
            pr_summaries.append(
                f"- [{pr.source}] {pr.title}" + (f" ({pr.published})" if pr.published else "")
            )
        parts.append("Recent press releases:\n" + "\n".join(pr_summaries))
    return "\n".join(parts)


def _company_history_digest(name: str, history: dict | None) -> str:
    """Format a company's historical SBIR record for LLM context."""
    if not history:
        return "No prior SBIR/STTR award history found in the dataset."
    parts = [
        f"Total historical SBIR/STTR awards: {history['total_awards']}",
        f"Phases achieved: {', '.join(history['phases']) or 'N/A'}",
        f"Agencies: {', '.join(history['agencies']) or 'N/A'}",
        f"Programs: {', '.join(history['programs']) or 'N/A'}",
        f"Total historical funding: ${history['total_funding']:,.0f}",
        f"Award date range: {history.get('earliest_date', 'N/A')} to {history.get('latest_date', 'N/A')}",
    ]
    if history.get("sample_titles"):
        parts.append("Sample award titles: " + "; ".join(history["sample_titles"]))
    return "\n".join(parts)


def _pi_history_digest(name: str, history: dict | None) -> str:
    """Format a PI's historical SBIR record for LLM context."""
    if not history:
        return "No prior SBIR/STTR award history found for this PI."
    parts = [
        f"Total historical SBIR/STTR awards as PI: {history['total_awards']}",
        f"Companies: {', '.join(history['companies']) or 'N/A'}",
        f"Phases: {', '.join(history['phases']) or 'N/A'}",
        f"Agencies: {', '.join(history['agencies']) or 'N/A'}",
        f"Total funding as PI: ${history['total_funding']:,.0f}",
        f"Date range: {history.get('earliest_date', 'N/A')} to {history.get('latest_date', 'N/A')}",
    ]
    if history.get("sample_titles"):
        parts.append("Sample award titles: " + "; ".join(history["sample_titles"]))
    return "\n".join(parts)


def _pi_external_digest(external: dict | None) -> str:
    """Format a PI's external data (patents, publications, ORCID, federal awards) for LLM context."""
    if not external:
        return "No external data available for this PI."

    parts = []

    # ORCID profile
    orcid: ORCIDRecord | None = external.get("orcid")
    if orcid:
        parts.append(f"ORCID ID: {orcid.orcid_id}")
        if orcid.affiliations:
            parts.append(f"ORCID affiliations: {', '.join(orcid.affiliations)}")
        parts.append(f"ORCID works count: {orcid.works_count}")
        parts.append(f"ORCID funding entries: {orcid.funding_count}")
        if orcid.keywords:
            parts.append(f"ORCID research keywords: {', '.join(orcid.keywords)}")
        if orcid.sample_work_titles:
            parts.append("ORCID sample works: " + "; ".join(orcid.sample_work_titles))
    else:
        parts.append("ORCID: No ORCID profile found for this researcher.")

    # Patents
    patents: PIPatentRecord | None = external.get("patents")
    if patents:
        parts.append(f"USPTO Patents as inventor: {patents.total_patents}")
        if patents.assignees:
            parts.append(f"Patent assignees: {', '.join(patents.assignees)}")
        if patents.date_range[0]:
            parts.append(f"Patent date range: {patents.date_range[0]} to {patents.date_range[1]}")
        if patents.sample_titles:
            parts.append("Sample patent titles: " + "; ".join(patents.sample_titles))
    else:
        parts.append("USPTO Patents: No patents found for this inventor name.")

    # Publications
    pubs: PIPublicationRecord | None = external.get("publications")
    if pubs:
        parts.append(f"Academic publications: {pubs.total_papers}")
        if pubs.h_index is not None:
            parts.append(f"h-index: {pubs.h_index}")
        parts.append(f"Total citations: {pubs.citation_count}")
        if pubs.affiliations:
            parts.append(f"Affiliations: {', '.join(pubs.affiliations)}")
        if pubs.sample_titles:
            parts.append("Sample paper titles: " + "; ".join(pubs.sample_titles))
    else:
        parts.append("Academic publications: No Semantic Scholar profile found.")

    # Federal awards (company-level) with SBIR vs non-SBIR breakdown
    fed: PIFederalAwardRecord | None = external.get("federal_awards")
    if fed:
        parts.append(f"Company federal awards (USAspending): {fed.total_awards} total")
        parts.append(f"Company total federal funding: ${fed.total_funding:,.0f}")
        parts.append(f"SBIR/STTR awards: {fed.sbir_award_count} (${fed.sbir_funding:,.0f})")
        parts.append(
            f"Non-SBIR federal awards (potential follow-on/Phase III): "
            f"{fed.non_sbir_award_count} (${fed.non_sbir_funding:,.0f})"
        )
        if fed.non_sbir_agencies:
            parts.append(f"Non-SBIR awarding agencies: {', '.join(fed.non_sbir_agencies)}")
        if fed.non_sbir_sample_descriptions:
            parts.append("Sample non-SBIR award descriptions (follow-on signals):")
            for desc in fed.non_sbir_sample_descriptions:
                parts.append(f"  - {desc}")
        if fed.agencies:
            parts.append(f"All federal agencies: {', '.join(fed.agencies)}")
        if fed.award_types:
            parts.append(f"Award types: {', '.join(fed.award_types)}")
        if fed.date_range[0]:
            parts.append(f"Federal award date range: {fed.date_range[0]} to {fed.date_range[1]}")
    else:
        parts.append("Company federal awards: No USAspending records found.")

    return "\n".join(parts)

"""OpenAI-backed generation stages for the weekly report."""

import json
import os
import sys


from sbir_etl.utils.text_normalization import normalize_name as _normalize_name
from sbir_etl.enrichers.openai_client import OpenAIClient
from sbir_etl.enrichers.company_enrichment import (
    FederalAwardSummary as PIFederalAwardRecord,
    USARecipientProfile,
    SAMEntityRecord,
)
from sbir_etl.enrichers.opencorporates import CorporateRecord
from sbir_etl.enrichers.press_wire import PressRelease

from sbir_etl.reporting.weekly.debug import _debug
from sbir_etl.reporting.weekly.fetching import _company_key
from sbir_etl.reporting.weekly.rendering import format_amount
from sbir_etl.reporting.weekly.models import CompanyResearch, SolicitationTopic
from sbir_etl.reporting.weekly.llm_digests import (
    _award_digest,
    _company_history_digest,
    _pi_history_digest,
    _pi_external_digest,
)


OPENAI_MODEL = "gpt-4.1-mini"


OPENAI_DILIGENCE_MODEL = "gpt-4.1"


DESCRIPTION_BATCH_SIZE = 10


MAX_COMPANIES_TO_RESEARCH = int(os.environ.get("MAX_COMPANIES_TO_RESEARCH", "50"))


MAX_AWARDS_TO_DESCRIBE = int(os.environ.get("MAX_AWARDS_TO_DESCRIBE", "100"))


# Lazy-initialized OpenAI client — created on first use.  Concurrency
# control lives inside OpenAIClient (via its internal semaphore).
_openai_client_instance: OpenAIClient | None = None

MAX_COMPANIES_TO_DILIGENCE = int(os.environ.get("MAX_COMPANIES_TO_DILIGENCE", "50"))
MAX_PIS_TO_DILIGENCE = int(os.environ.get("MAX_PIS_TO_DILIGENCE", "50"))


def _get_openai_client(api_key: str) -> OpenAIClient:
    """Return (and cache) the shared OpenAIClient instance."""
    global _openai_client_instance  # noqa: PLW0603
    if _openai_client_instance is None:
        _openai_client_instance = OpenAIClient(
            api_key=api_key,
            max_concurrent=int(os.environ.get("OPENAI_MAX_CONCURRENT", "4")),
            model=OPENAI_MODEL,
        )
    return _openai_client_instance


def _openai_chat(
    api_key: str,
    system: str,
    user: str,
    model: str = OPENAI_MODEL,
    temperature: float = 0.3,
) -> str | None:
    """Call the OpenAI chat completions API. Returns the assistant message text."""
    _debug(
        f"OpenAI chat: model={model} temp={temperature} "
        f"system_len={len(system)} user_len={len(user)}"
    )

    oai = _get_openai_client(api_key)
    result = oai.chat(system, user, model=model, temperature=temperature)
    if result:
        _debug(f"OpenAI chat response: {len(result)} chars")
    return result


def _openai_web_search(api_key: str, query: str) -> CompanyResearch | None:
    """Use the OpenAI Responses API with web_search_preview to research a company."""
    _debug(f"OpenAI web search: query='{query[:200]}'")

    oai = _get_openai_client(api_key)
    result = oai.web_search(query)
    if result is None:
        return None
    return CompanyResearch(summary=result.summary, source_urls=result.source_urls)


def research_companies(api_key: str, awards: list[dict]) -> dict[str, CompanyResearch]:
    """Research each unique awardee company via web search."""
    companies: dict[str, dict] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = _company_key(a)
        if key not in companies:
            companies[key] = {
                "name": name,
                "state": str(a.get("State", "")),
                "website": str(a.get("Company Website", "")),
            }

    results: dict[str, CompanyResearch] = {}
    # Cap the number of companies to research
    company_items = list(companies.items())
    if len(company_items) > MAX_COMPANIES_TO_RESEARCH:
        print(
            f"Capping company research at {MAX_COMPANIES_TO_RESEARCH} of {len(company_items)} companies",
            file=sys.stderr,
        )
        company_items = company_items[:MAX_COMPANIES_TO_RESEARCH]
    total = len(company_items)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _research_single(item: tuple[str, dict]) -> tuple[str, CompanyResearch | None]:
        key, info = item
        name = info["name"]
        state = info["state"]
        website = info["website"]
        query = (
            f"Find public information about {name}"
            + (f" based in {state}" if state else "")
            + ". They are an SBIR/STTR federal award recipient."
            + (f" Their website is {website}." if website else "")
            + " What does this company do? How large are they? "
            + "What is their technology focus? Any notable contracts or previous SBIR awards?"
        )
        return key, _openai_web_search(api_key, query)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_research_single, item): item for item in company_items}
        done = 0
        for future in as_completed(futures):
            done += 1
            key_info = futures[future]
            name = key_info[1]["name"]
            try:
                key, research = future.result()
                if research:
                    results[key] = research
                print(f"Completed company research {done}/{total}: {name}", file=sys.stderr)
            except Exception as e:
                print(f"Company research error for {name}: {e}", file=sys.stderr)

    return results


def generate_weekly_synopsis(
    api_key: str,
    awards: list[dict],
    days: int,
    company_research: dict[str, CompanyResearch] | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
    corporate_records: dict[str, CorporateRecord] | None = None,
    press_releases: dict[str, list[PressRelease]] | None = None,
) -> str | None:
    """Generate a two-paragraph synopsis of all weekly award activity."""
    if not awards:
        return None

    total_amount = 0.0
    agencies: dict[str, int] = {}
    for a in awards:
        try:
            total_amount += float(str(a.get("Award Amount", "0")).replace(",", "").replace("$", ""))
        except (ValueError, AttributeError):
            pass
        ag = str(a.get("Agency", "Unknown"))
        agencies[ag] = agencies.get(ag, 0) + 1

    digests = []
    for i, a in enumerate(awards[:50]):
        key = _company_key(a)
        cr = company_research.get(key) if company_research else None
        oc = corporate_records.get(key) if corporate_records else None
        pr = press_releases.get(key) if press_releases else None
        digests.append(
            f"[{i + 1}] {_award_digest(a, cr, solicitation_topics, usaspending_descriptions, sam_entities, oc, pr)}"
        )
    digest_block = "\n\n".join(digests)
    if len(awards) > 50:
        digest_block += f"\n\n... and {len(awards) - 50} additional awards."

    system = (
        "You are an analyst writing a concise executive briefing about weekly "
        "SBIR/STTR federal small business innovation award activity. "
        "Write in a professional, informative tone. Do not use markdown headers. "
        "Do not use bullet points. Write exactly two paragraphs. "
        "Incorporate relevant context about the awardee companies when provided."
    )
    user = (
        f"Write a two-paragraph synopsis of this week's SBIR/STTR award activity.\n\n"
        f"Period: past {days} days\n"
        f"Total awards: {len(awards)}\n"
        f"Total funding: ${total_amount:,.0f}\n"
        f"Agencies: {json.dumps(agencies)}\n\n"
        f"Award details:\n{digest_block}"
    )

    print("Generating weekly synopsis via OpenAI...", file=sys.stderr)
    return _openai_chat(api_key, system, user)


def generate_award_descriptions(
    api_key: str,
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
    solicitation_topics: dict[str, SolicitationTopic] | None = None,
    usaspending_descriptions: dict[str, str] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
    corporate_records: dict[str, CorporateRecord] | None = None,
    press_releases: dict[str, list[PressRelease]] | None = None,
) -> dict[int, str]:
    """Generate a brief description for each award using batched API calls."""
    descriptions: dict[int, str] = {}
    if not awards:
        return descriptions

    # Cap the number of awards to describe
    awards_to_describe = awards
    if len(awards) > MAX_AWARDS_TO_DESCRIBE:
        print(
            f"Capping award descriptions at {MAX_AWARDS_TO_DESCRIBE} of {len(awards)} awards",
            file=sys.stderr,
        )
        awards_to_describe = awards[:MAX_AWARDS_TO_DESCRIBE]

    system = (
        "You summarize SBIR/STTR awards in plain language. "
        "For each award, write 3-4 sentences. The first 1-2 sentences should "
        "explain what the project does and why it matters — be specific about "
        "the technology and its intended application.\n\n"
        "When a solicitation topic description is provided, the final 1-2 "
        "sentences MUST assess the alignment between the award and the "
        "originating solicitation:\n"
        "- Does the award's abstract directly address the technical "
        "objectives laid out in the solicitation topic description?\n"
        "- Is the award tightly scoped to the solicitation's stated research "
        "need, or does it appear to address the topic tangentially or "
        "partially?\n"
        "- Are there aspects of the solicitation's requirements that the "
        "award abstract does not appear to cover?\n"
        "State the alignment clearly (e.g. 'This award directly addresses "
        "the solicitation's need for...' or 'While the solicitation sought "
        "X, this award focuses primarily on Y, which addresses only a "
        "portion of the stated need.'). Do not hedge — make a specific "
        "assessment based on the available text.\n\n"
        "If no solicitation topic description is available, skip the "
        "alignment assessment and focus on the technology, its application, "
        "and company context.\n\n"
        "Reference relevant company context (e.g. their expertise, previous "
        "work, or market position) when it adds value. Avoid generic filler.\n\n"
        "Respond with a JSON object mapping the award number (as a string key) "
        'to its description string. Example: {"1": "Description.", "2": "Description."}'
    )

    for batch_start in range(0, len(awards_to_describe), DESCRIPTION_BATCH_SIZE):
        batch = awards_to_describe[batch_start : batch_start + DESCRIPTION_BATCH_SIZE]
        digests = []
        for i, a in enumerate(batch):
            idx = batch_start + i + 1
            key = _company_key(a)
            cr = company_research.get(key) if company_research else None
            oc = corporate_records.get(key) if corporate_records else None
            pr = press_releases.get(key) if press_releases else None
            digests.append(
                f"[{idx}] {_award_digest(a, cr, solicitation_topics, usaspending_descriptions, sam_entities, oc, pr)}"
            )

        user = (
            "Generate a description for each award below. Each description "
            "should convey the technology, its application, and — when "
            "solicitation topic data is provided — a specific assessment of "
            "how well the award aligns with the solicitation's stated "
            "research need. Respond ONLY with a JSON object.\n\n" + "\n\n".join(digests)
        )

        batch_label = f"{batch_start + 1}-{batch_start + len(batch)}"
        print(
            f"Generating descriptions for awards {batch_label} of {len(awards_to_describe)}...",
            file=sys.stderr,
        )
        raw = _openai_chat(api_key, system, user)
        if not raw:
            continue

        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            batch_descriptions = json.loads(text)
            for key, desc in batch_descriptions.items():
                descriptions[int(key) - 1] = desc
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse description batch {batch_label}: {e}", file=sys.stderr)

    return descriptions


def generate_company_diligence(
    api_key: str,
    awards: list[dict],
    company_research: dict[str, CompanyResearch] | None = None,
    company_history: dict[str, dict] | None = None,
    sam_entities: dict[str, SAMEntityRecord] | None = None,
    company_federal_awards: dict[str, PIFederalAwardRecord] | None = None,
    usa_recipients: dict[str, USARecipientProfile] | None = None,
    congressional_districts: dict[str, str] | None = None,
    bea_sectors: dict[str, str] | None = None,
    corporate_records: dict[str, CorporateRecord] | None = None,
    press_releases: dict[str, list[PressRelease]] | None = None,
) -> dict[str, str]:
    """Generate a diligence paragraph for each unique awardee company.

    Combines web research, historical SBIR data, SAM.gov registration data,
    USAspending federal award data (with SBIR vs non-SBIR breakdown),
    state corporation filings (OpenCorporates), press wire hits, and
    the current award context to produce a focused due-diligence assessment
    per company.

    Returns a dict keyed by upper-cased company name.
    """
    # Collect unique companies (grouped by normalized name)
    companies: dict[str, list[dict]] = {}
    for a in awards:
        name = str(a.get("Company", "")).strip()
        if not name:
            continue
        key = _company_key(a)
        companies.setdefault(key, []).append(a)

    company_items = list(companies.items())
    if len(company_items) > MAX_COMPANIES_TO_DILIGENCE:
        print(
            f"Capping company diligence at {MAX_COMPANIES_TO_DILIGENCE} "
            f"of {len(company_items)} companies",
            file=sys.stderr,
        )
        company_items = company_items[:MAX_COMPANIES_TO_DILIGENCE]

    system = (
        "You are a due-diligence analyst evaluating companies that receive "
        "SBIR/STTR federal innovation awards. Write exactly one paragraph "
        "(4-6 sentences) of diligence analysis for the company. Cover:\n"
        "1. Company background and technology focus\n"
        "2. SBIR track record — award volume, phase progression (Phase I→II→III "
        "indicates commercialization progress), agency diversity\n"
        "3. SAM.gov registration status — active registration, entity structure, "
        "business type, NAICS codes (industry classification), and any "
        "exclusion flags are important compliance signals. An expired or "
        "missing SAM registration is a red flag for federal contracting.\n"
        "4. Commercialization and follow-on signals — the strongest evidence "
        "of SBIR success is non-SBIR federal awards (contracts, grants) to "
        "the same company, which represent Phase III transitions where SBIR "
        "research led to production work. Also consider products, revenue, "
        "patents, or partnerships. A company with many SBIR awards but zero "
        "non-SBIR federal work may be an 'SBIR mill' that hasn't "
        "commercialized.\n"
        "5. Corporate structure signals — if state filing data is available, "
        "note incorporation date (firm age), whether the company is a "
        "subsidiary of a larger entity (potential SBIR eligibility concern), "
        "shared officers with other SBIR awardees, or dissolved/inactive "
        "state filing status. A mismatch between SAM.gov active status and "
        "state filing inactive/dissolved status is a red flag.\n"
        "6. Recent news — if press releases are available, note any contract "
        "wins, acquisitions, partnerships, or product launches that signal "
        "commercialization progress or strategic direction.\n"
        "7. Risk factors — e.g. sole reliance on SBIR funding, narrow agency "
        "base, lack of phase progression, SAM exclusions, no follow-on "
        "contracts, subsidiary of a large company, or limited public presence\n\n"
        "Be specific and analytical. Do not use bullet points or headers. "
        "Write in a professional, neutral tone. If information is limited, "
        "note that as a risk factor."
    )

    results: dict[str, str] = {}
    total = len(company_items)

    def _build_and_generate(idx: int, key: str, co_awards: list[dict]) -> tuple[str, str | None]:
        display_name = co_awards[0].get("Company", key)
        state = str(co_awards[0].get("State", ""))

        # Build context
        context_parts = [f"Company: {display_name}"]
        if state:
            context_parts.append(f"State: {state}")

        # Current week's awards
        current_summaries = []
        for a in co_awards:
            current_summaries.append(
                f"- {a.get('Award Title', 'N/A')} | {a.get('Agency', '')} "
                f"{a.get('Program', '')} {a.get('Phase', '')} | "
                f"{format_amount(str(a.get('Award Amount', '')))}"
            )
        context_parts.append(
            f"Current week's awards ({len(co_awards)}):\n" + "\n".join(current_summaries)
        )

        # Historical SBIR data
        hist = company_history.get(key) if company_history else None
        context_parts.append(f"Historical SBIR record:\n{_company_history_digest(key, hist)}")

        # Web research
        cr = company_research.get(key) if company_research else None
        if cr:
            context_parts.append(f"Web research summary:\n{cr.summary}")
            if cr.source_urls:
                context_parts.append("Sources: " + ", ".join(cr.source_urls[:5]))
        else:
            context_parts.append("Web research: No web research available for this company.")

        # SAM.gov registration data
        sam = sam_entities.get(key) if sam_entities else None
        if sam:
            sam_parts = [
                f"SAM.gov UEI: {sam.uei}",
                f"Legal Business Name: {sam.legal_business_name}",
            ]
            if sam.dba_name:
                sam_parts.append(f"DBA Name: {sam.dba_name}")
            sam_parts.append(f"Registration Status: {sam.registration_status or 'Unknown'}")
            if sam.expiration_date:
                sam_parts.append(f"Registration Expiration: {sam.expiration_date}")
            if sam.entity_structure:
                sam_parts.append(f"Entity Structure: {sam.entity_structure}")
            if sam.business_type:
                sam_parts.append(f"Business Type: {sam.business_type}")
            if sam.naics_codes:
                sam_parts.append(f"NAICS Codes: {', '.join(sam.naics_codes)}")
            if sam.cage_code:
                sam_parts.append(f"CAGE Code: {sam.cage_code}")
            if sam.exclusion_status:
                sam_parts.append(f"Exclusion Status: {sam.exclusion_status}")
            context_parts.append("SAM.gov registration data:\n" + "\n".join(sam_parts))
        else:
            context_parts.append(
                "SAM.gov: No SAM.gov registration data found for this company. "
                "This may indicate the company is not registered as a federal "
                "contractor, or the lookup failed."
            )

        # USAspending federal awards with SBIR vs non-SBIR breakdown
        fed = company_federal_awards.get(key) if company_federal_awards else None
        if fed:
            fed_parts = [
                f"Total federal awards (USAspending): {fed.total_awards}",
                f"Total federal funding: ${fed.total_funding:,.0f}",
                f"SBIR/STTR awards: {fed.sbir_award_count} (${fed.sbir_funding:,.0f})",
                f"Non-SBIR federal awards (follow-on/Phase III signals): "
                f"{fed.non_sbir_award_count} (${fed.non_sbir_funding:,.0f})",
            ]
            if fed.non_sbir_agencies:
                fed_parts.append(f"Non-SBIR awarding agencies: {', '.join(fed.non_sbir_agencies)}")
            if fed.non_sbir_sample_descriptions:
                fed_parts.append("Sample non-SBIR awards:")
                for d in fed.non_sbir_sample_descriptions:
                    fed_parts.append(f"  - {d}")
            context_parts.append("USAspending federal award data:\n" + "\n".join(fed_parts))
        else:
            context_parts.append("USAspending: No federal award records found for this company.")

        # USAspending recipient profile (business types, parent company, totals)
        rcp = usa_recipients.get(key) if usa_recipients else None
        if rcp:
            rcp_parts = [
                f"USAspending recipient name: {rcp.name}",
            ]
            if rcp.parent_name:
                rcp_parts.append(f"Parent company: {rcp.parent_name}")
            if rcp.business_types:
                rcp_parts.append(f"Business types: {', '.join(rcp.business_types)}")
            rcp_parts.append(
                f"Total federal award history: {rcp.total_transactions} awards, "
                f"${rcp.total_transaction_amount:,.0f}"
            )
            if rcp.location_state:
                rcp_parts.append(f"State: {rcp.location_state}")
            if rcp.location_congressional_district:
                rcp_parts.append(
                    f"Congressional district: {rcp.location_state}-{rcp.location_congressional_district}"
                )
            context_parts.append("USAspending recipient profile:\n" + "\n".join(rcp_parts))

        # Congressional district (from ZIP code resolution)
        # Try both _company_key and raw upper name since dicts may use either
        if congressional_districts:
            district = congressional_districts.get(key) or congressional_districts.get(
                display_name.upper()
            )
            if district:
                context_parts.append(f"Congressional district: {district}")

        # BEA sector classification (from SAM.gov NAICS codes)
        # SAM entities may be keyed by raw upper name
        if not sam and sam_entities:
            sam = sam_entities.get(display_name.upper())
        if bea_sectors and sam:
            sector_parts = []
            for naics in (sam.naics_codes or [])[:3]:
                sector = bea_sectors.get(naics)
                if sector:
                    sector_parts.append(f"NAICS {naics} → {sector}")
            if sector_parts:
                context_parts.append("BEA economic sectors: " + "; ".join(sector_parts))

        # State corporation filings (OpenCorporates)
        oc = corporate_records.get(key) if corporate_records else None
        if oc:
            oc_parts = [
                f"State filing name: {oc.company_name}",
                f"Jurisdiction: {oc.jurisdiction}",
            ]
            if oc.incorporation_date:
                oc_parts.append(f"Incorporation date: {oc.incorporation_date}")
            if oc.status:
                oc_parts.append(f"State filing status: {oc.status}")
            if oc.company_type:
                oc_parts.append(f"Entity type: {oc.company_type}")
            if oc.dissolution_date:
                oc_parts.append(f"Dissolution date: {oc.dissolution_date}")
            if oc.agent_name:
                oc_parts.append(f"Registered agent: {oc.agent_name}")
            if oc.registered_address:
                oc_parts.append(f"Registered address: {oc.registered_address}")
            if oc.parent_company:
                oc_parts.append(
                    f"PARENT COMPANY: {oc.parent_company}"
                    + (f" ({oc.parent_jurisdiction})" if oc.parent_jurisdiction else "")
                )
            if oc.officers:
                for o in oc.officers[:5]:
                    oc_parts.append(
                        f"Officer: {o.name}"
                        + (f" ({o.position})" if o.position else "")
                        + (f" since {o.start_date}" if o.start_date else "")
                    )
            context_parts.append(
                "State corporation filing (OpenCorporates):\n" + "\n".join(oc_parts)
            )
        else:
            context_parts.append("State corporation filing: No OpenCorporates record found.")

        # Recent press releases (press wire feeds)
        pr_list = press_releases.get(key) if press_releases else None
        if pr_list:
            pr_parts = []
            for pr in pr_list[:5]:
                pr_parts.append(
                    f"- [{pr.source}] {pr.title}" + (f" ({pr.published})" if pr.published else "")
                )
            context_parts.append("Recent press releases:\n" + "\n".join(pr_parts))

        user = (
            "Write a one-paragraph due-diligence assessment for this "
            "SBIR/STTR awardee company.\n\n" + "\n\n".join(context_parts)
        )

        print(
            f"Generating company diligence {idx}/{total}: {display_name}...",
            file=sys.stderr,
        )
        result = _openai_chat(
            api_key,
            system,
            user,
            model=OPENAI_DILIGENCE_MODEL,
            temperature=0.4,
        )
        return key, result

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_build_and_generate, idx, key, co_awards): key
            for idx, (key, co_awards) in enumerate(company_items, 1)
        }
        for future in as_completed(futures):
            try:
                key, result = future.result()
                if result:
                    results[key] = result
            except Exception as e:
                print(f"Company diligence error for {futures[future]}: {e}", file=sys.stderr)

    return results


def generate_pi_diligence(
    api_key: str,
    awards: list[dict],
    pi_history: dict[str, dict] | None = None,
    company_research: dict[str, CompanyResearch] | None = None,
    pi_external_data: dict[str, dict] | None = None,
) -> dict[str, str]:
    """Generate a diligence paragraph for each unique Principal Investigator.

    Combines the PI's SBIR history, patent portfolio, academic publications,
    company federal award context, and web research to produce a comprehensive
    assessment.

    Returns a dict keyed by upper-cased PI name.
    """
    # Collect unique PIs
    pis: dict[str, list[dict]] = {}
    for a in awards:
        pi = str(a.get("PI Name", "")).strip()
        if not pi:
            continue
        key = pi.upper()
        pis.setdefault(key, []).append(a)

    pi_items = list(pis.items())
    if len(pi_items) > MAX_PIS_TO_DILIGENCE:
        print(
            f"Capping PI diligence at {MAX_PIS_TO_DILIGENCE} of {len(pi_items)} PIs",
            file=sys.stderr,
        )
        pi_items = pi_items[:MAX_PIS_TO_DILIGENCE]

    system = (
        "You are a due-diligence analyst evaluating Principal Investigators "
        "(PIs) who lead SBIR/STTR federal innovation projects. Write exactly "
        "one paragraph (4-6 sentences) assessing the PI. Cover:\n"
        "1. The PI's SBIR track record — number of awards, phase progression, "
        "breadth of agencies and topics\n"
        "2. Continuity — have they stayed with one company or moved between "
        "organizations? Is their research focus consistent or scattered? "
        "Cross-reference ORCID affiliations with SBIR company history to "
        "verify consistency.\n"
        "3. IP and publication output — patents filed as inventor, academic "
        "publications, and ORCID profile data demonstrate research "
        "productivity and domain expertise. Note h-index and citation count "
        "when available. ORCID research keywords and funding entries help "
        "confirm domain alignment. If patents are assigned to different "
        "entities than the current company, note that.\n"
        "4. Follow-on and commercialization — non-SBIR federal awards "
        "(contracts, grants) to the PI's company are the strongest signal "
        "of successful SBIR commercialization. These represent Phase III "
        "transitions where SBIR research led to production contracts or "
        "operational deployment. Compare the non-SBIR award descriptions "
        "to the PI's SBIR research topics — thematic alignment confirms "
        "genuine technology transition. A company with only SBIR awards "
        "and no follow-on federal work may indicate research that hasn't "
        "transitioned.\n"
        "5. Current project context — what are they working on now and how "
        "does it relate to their history and expertise?\n\n"
        "Be specific and analytical. Do not use bullet points or headers. "
        "Write in a professional, neutral tone. If the PI has no prior "
        "history, note that this is their first known SBIR award."
    )

    results: dict[str, str] = {}
    total = len(pi_items)

    def _build_and_generate_pi(idx: int, key: str, pi_awards: list[dict]) -> tuple[str, str | None]:
        display_name = pi_awards[0].get("PI Name", key)
        company = str(pi_awards[0].get("Company", ""))

        context_parts = [f"Principal Investigator: {display_name}"]
        if company:
            context_parts.append(f"Current company: {company}")

        # Current week's awards
        current_summaries = []
        for a in pi_awards:
            current_summaries.append(
                f"- {a.get('Award Title', 'N/A')} | {a.get('Company', '')} | "
                f"{a.get('Agency', '')} {a.get('Program', '')} {a.get('Phase', '')} | "
                f"{format_amount(str(a.get('Award Amount', '')))}"
            )
        context_parts.append(
            f"Current week's awards ({len(pi_awards)}):\n" + "\n".join(current_summaries)
        )

        # PI historical record
        hist = pi_history.get(key) if pi_history else None
        context_parts.append(f"Historical SBIR record as PI:\n{_pi_history_digest(key, hist)}")

        # External data: patents, publications, federal awards
        ext = pi_external_data.get(key) if pi_external_data else None
        context_parts.append(f"External research data:\n{_pi_external_digest(ext)}")

        # Company web research for context
        cr = None
        if company_research:
            cr = company_research.get(
                _normalize_name(company, remove_suffixes=True) or company.strip().upper()
            )
        if cr:
            context_parts.append(f"Company context ({company}):\n{cr.summary}")

        user = (
            "Write a one-paragraph assessment of this Principal Investigator's "
            "SBIR/STTR track record, research output, and current project.\n\n"
            + "\n\n".join(context_parts)
        )

        print(
            f"Generating PI diligence {idx}/{total}: {display_name}...",
            file=sys.stderr,
        )
        result = _openai_chat(
            api_key,
            system,
            user,
            model=OPENAI_DILIGENCE_MODEL,
            temperature=0.4,
        )
        return key, result

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_build_and_generate_pi, idx, key, pi_awards): key
            for idx, (key, pi_awards) in enumerate(pi_items, 1)
        }
        for future in as_completed(futures):
            try:
                key, result = future.result()
                if result:
                    results[key] = result
            except Exception as e:
                print(f"PI diligence error for {futures[future]}: {e}", file=sys.stderr)

    return results

"""Markdown rendering for the weekly awards report (pure functions)."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote


from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL as SBIR_AWARDS_URL
from sbir_etl.utils.date_utils import parse_date as _parse_date
from sbir_etl.utils.text_normalization import normalize_name as _normalize_name

from sbir_etl.reporting.weekly.debug import _debug
from sbir_etl.reporting.weekly.models import CompanyResearch


SBIR_AWARD_SEARCH_URL = "https://www.sbir.gov/awards"


SBIR_SOLICITATION_URL = "https://www.sbir.gov/awards"


USASPENDING_SEARCH_URL = "https://www.usaspending.gov/search"


def _escape_md_cell(value: str) -> str:
    """Escape a string for safe use inside a markdown table cell."""
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", "")


def format_amount(amount_str: str) -> str:
    """Format dollar amount for display."""
    try:
        amount = float(str(amount_str).replace(",", "").replace("$", ""))
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:.2f}M"
        if amount >= 1_000:
            return f"${amount / 1_000:.0f}K"
        return f"${amount:,.0f}"
    except (ValueError, AttributeError, TypeError):
        return str(amount_str) if amount_str else "N/A"


def _format_date(value) -> str:
    """Format a date value for display using the project's date parser."""
    parsed = _parse_date(value)
    if parsed:
        return parsed.isoformat()
    return str(value) if value else ""


def build_sbir_award_url(award: dict) -> str:
    """Build a link to the SBIR.gov award search page for this award."""
    contract = str(award.get("Contract", "")).strip()
    if contract:
        url = f"{SBIR_AWARD_SEARCH_URL}?keyword={quote(contract)}"
        _debug(f"SBIR award URL (contract='{contract}'): {url}")
        return url
    company = str(award.get("Company", "")).strip()
    if company:
        url = f"{SBIR_AWARD_SEARCH_URL}?keyword={quote(company)}"
        _debug(f"SBIR award URL (company='{company}', no contract): {url}")
        return url
    _debug("SBIR award URL: no contract or company — using base URL")
    return SBIR_AWARD_SEARCH_URL


def build_solicitation_url(award: dict) -> str | None:
    """Build a link to the SBIR.gov solicitation/topic page."""
    solicitation = str(award.get("Solicitation Number", "")).strip()
    topic_code = str(award.get("Topic Code", "")).strip()
    if solicitation:
        url = f"{SBIR_SOLICITATION_URL}?keyword={quote(solicitation)}"
        _debug(f"Solicitation URL (sol='{solicitation}'): {url}")
        return url
    if topic_code:
        url = f"{SBIR_SOLICITATION_URL}?keyword={quote(topic_code)}"
        _debug(f"Solicitation URL (topic='{topic_code}', no sol number): {url}")
        return url
    _debug(
        f"Solicitation URL: no solicitation number or topic code for '{award.get('Award Title', 'N/A')}'"
    )
    return None


def build_usaspending_url(award: dict) -> str | None:
    """Build a link to USAspending.gov search for this award's contract."""
    contract = str(award.get("Contract", "")).strip()
    if not contract:
        _debug(f"USAspending URL: no contract number for '{award.get('Award Title', 'N/A')}'")
        return None
    search_term = quote(contract)
    url = f'{USASPENDING_SEARCH_URL}?form_fields={{"search_term":"{search_term}"}}'
    _debug(f"USAspending URL (contract='{contract}'): {url}")
    return url


def generate_markdown(
    awards: list[dict],
    days: int,
    synopsis: str | None = None,
    descriptions: dict[int, str] | None = None,
    company_research: dict[str, CompanyResearch] | None = None,
    freshness_warnings: list[str] | None = None,
    company_diligence: dict[str, str] | None = None,
    pi_diligence: dict[str, str] | None = None,
    inflation_data: dict[str, float] | None = None,
) -> str:
    """Generate markdown report from filtered awards."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)

    lines = []
    lines.append("# SBIR Weekly Awards Report")
    lines.append("")
    lines.append(f"**Period:** {cutoff.strftime('%B %d, %Y')} - {now.strftime('%B %d, %Y')}")
    lines.append(f"**Total new awards:** {len(awards)}")
    lines.append("")

    # Data freshness warnings
    if freshness_warnings:
        lines.append("> **Data Freshness Warning**")
        lines.append(">")
        for w in freshness_warnings:
            lines.append(f"> - {w}")
        lines.append("")

    if not awards:
        lines.append("No new awards found for this period.")
        return "\n".join(lines)

    # Weekly synopsis at the very top
    if synopsis:
        lines.append(synopsis)
        lines.append("")

    # Summary statistics
    total_amount = 0.0
    agencies: dict[str, int] = {}
    programs: dict[str, int] = {}
    states: dict[str, int] = {}

    for a in awards:
        try:
            total_amount += float(str(a.get("Award Amount", "0")).replace(",", "").replace("$", ""))
        except (ValueError, AttributeError):
            pass
        agency = str(a.get("Agency", "Unknown"))
        agencies[agency] = agencies.get(agency, 0) + 1
        program = str(a.get("Program", "Unknown"))
        programs[program] = programs.get(program, 0) + 1
        state = str(a.get("State", ""))
        if state:
            states[state] = states.get(state, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Awards | {len(awards)} |")
    lines.append(f"| Total Funding | {format_amount(str(total_amount))} |")
    lines.append(f"| Avg Award Size | {format_amount(str(total_amount / len(awards)))} |")
    lines.append(f"| Agencies | {len(agencies)} |")
    lines.append(f"| States | {len(states)} |")
    if inflation_data and "adjusted_total" in inflation_data:
        base_yr = inflation_data.get("base_year", 2024)
        lines.append(
            f"| Inflation-Adjusted Total ({base_yr}$) | "
            f"{format_amount(str(inflation_data['adjusted_total']))} |"
        )
    lines.append("")

    # Breakdown by agency
    lines.append("## By Agency")
    lines.append("")
    lines.append("| Agency | Awards |")
    lines.append("|--------|--------|")
    for agency, count in sorted(agencies.items(), key=lambda x: -x[1]):
        lines.append(f"| {_escape_md_cell(agency)} | {count} |")
    lines.append("")

    # Breakdown by program/phase
    lines.append("## By Program & Phase")
    lines.append("")
    lines.append("| Program | Phase | Awards |")
    lines.append("|---------|-------|--------|")
    program_phase: dict[tuple[str, str], int] = {}
    for a in awards:
        key = (str(a.get("Program", "Unknown")), str(a.get("Phase", "Unknown")))
        program_phase[key] = program_phase.get(key, 0) + 1
    for (program, phase), count in sorted(program_phase.items(), key=lambda x: -x[1]):
        lines.append(f"| {_escape_md_cell(program)} | {_escape_md_cell(phase)} | {count} |")
    lines.append("")

    # Individual awards
    lines.append("## Awards")
    lines.append("")

    for i, a in enumerate(awards):
        date = _format_date(a.get("Proposal Award Date", ""))
        company = str(a.get("Company", ""))
        title = str(a.get("Award Title", ""))
        agency = str(a.get("Agency", ""))
        program = str(a.get("Program", ""))
        phase = str(a.get("Phase", ""))
        amount = format_amount(str(a.get("Award Amount", "")))
        state = str(a.get("State", ""))
        contract = str(a.get("Contract", "")).strip()
        solicitation = str(a.get("Solicitation Number", "")).strip()
        topic_code = str(a.get("Topic Code", "")).strip()
        pi_name = str(a.get("PI Name", "")).strip()

        # Build links
        sbir_url = build_sbir_award_url(a)
        solicitation_url = build_solicitation_url(a)
        usaspending_url = build_usaspending_url(a)

        # Look up company research
        cr = None
        if company_research:
            cr = company_research.get(
                _normalize_name(company, remove_suffixes=True) or company.strip().upper()
            )

        # Award header
        lines.append(f"### {i + 1}. {title}")
        lines.append("")
        lines.append(f"**{company}** | {agency} {program} {phase} | {amount} | {state} | {date}")
        lines.append("")

        # AI-generated description
        if descriptions and i in descriptions:
            lines.append(descriptions[i])
            lines.append("")

        # Company diligence paragraph
        if company_diligence:
            co_key = _normalize_name(company, remove_suffixes=True) or company.strip().upper()
            if co_key in company_diligence:
                lines.append(f"**Company Diligence — {company}:**")
                lines.append(company_diligence[co_key])
                lines.append("")

        # PI diligence paragraph
        if pi_diligence and pi_name:
            pi_key = pi_name.strip().upper()
            if pi_key in pi_diligence:
                lines.append(f"**Principal Investigator — {pi_name}:**")
                lines.append(pi_diligence[pi_key])
                lines.append("")

        # Details table
        lines.append("<details>")
        lines.append("<summary>Award details</summary>")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Company** | {_escape_md_cell(company)} |")
        lines.append(f"| **Award Date** | {date} |")
        lines.append(f"| **Amount** | {amount} |")
        lines.append(f"| **Agency** | {_escape_md_cell(agency)} |")
        lines.append(f"| **Program** | {_escape_md_cell(program)} |")
        lines.append(f"| **Phase** | {_escape_md_cell(phase)} |")
        if state:
            lines.append(f"| **State** | {_escape_md_cell(state)} |")
        if contract:
            lines.append(f"| **Contract** | `{_escape_md_cell(contract)}` |")
        if pi_name:
            lines.append(f"| **PI** | {_escape_md_cell(pi_name)} |")
        if solicitation:
            lines.append(f"| **Solicitation** | `{_escape_md_cell(solicitation)}` |")
        if topic_code:
            lines.append(f"| **Topic Code** | `{_escape_md_cell(topic_code)}` |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

        # Reference links
        link_parts = [f"[SBIR.gov Award]({sbir_url})"]
        if solicitation_url:
            link_parts.append(f"[Solicitation]({solicitation_url})")
        if usaspending_url:
            link_parts.append(f"[USAspending]({usaspending_url})")
        if cr and cr.source_urls:
            for url in cr.source_urls[:3]:
                domain = url.split("//")[-1].split("/")[0].replace("www.", "")
                link_parts.append(f"[{domain}]({url})")

        lines.append("**References:** " + " | ".join(link_parts))
        lines.append("")

    lines.append(
        f"---\n*Generated on {now.strftime('%Y-%m-%d %H:%M UTC')} from "
        f"[SBIR.gov]({SBIR_AWARDS_URL}) bulk data.*"
    )
    return "\n".join(lines)

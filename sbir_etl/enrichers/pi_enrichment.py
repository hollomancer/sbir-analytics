"""PI (Principal Investigator) enrichment functions.

Extracts patent, publication, and ORCID profile data for principal
investigators using external API clients. Each lookup function returns
a typed dataclass on success or ``None`` on failure, making them safe
to call unconditionally in enrichment pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from sbir_etl.enrichers.orcid_client import ORCIDClient
from sbir_etl.enrichers.patentsview import PatentsViewClient, RateLimiter
from sbir_etl.enrichers.lens_patents import LensPatentClient
from sbir_etl.enrichers.semantic_scholar import SemanticScholarClient
from sbir_etl.models.sbir_identification import classify_sbir_award

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PIPatentRecord:
    """Summary of a PI's patent portfolio from PatentsView."""

    total_patents: int
    sample_titles: list[str]
    assignees: list[str]
    date_range: tuple[str | None, str | None]


@dataclass
class PIPublicationRecord:
    """Summary of a PI's publication history from Semantic Scholar."""

    total_papers: int
    h_index: int | None
    citation_count: int
    sample_titles: list[str]
    affiliations: list[str]


@dataclass
class ORCIDRecord:
    """Key data from an ORCID researcher profile."""

    orcid_id: str
    given_name: str | None
    family_name: str | None
    affiliations: list[str]
    works_count: int
    sample_work_titles: list[str]
    funding_count: int
    keywords: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_pi_name(full_name: str) -> tuple[str, str]:
    """Split a PI name into (first, last) for API queries.

    SBIR data typically stores names as 'First Last' or 'Last, First'.
    """
    full_name = full_name.strip()
    if "," in full_name:
        parts = [p.strip() for p in full_name.split(",", 1)]
        return (parts[1], parts[0]) if len(parts) == 2 else (parts[0], "")
    parts = full_name.split()
    if len(parts) >= 2:
        return (parts[0], parts[-1])
    return (full_name, "")


def _is_sbir_award_type(description: str, cfda: str) -> bool:
    """Identify SBIR/STTR awards using ALN numbers and description keywords.

    Delegates to :func:`sbir_etl.models.sbir_identification.classify_sbir_award`.
    """
    result = classify_sbir_award(cfda_number=cfda, description=description)
    return result is not None


# ---------------------------------------------------------------------------
# External API lookups
# ---------------------------------------------------------------------------


def lookup_pi_patents(
    pi_name: str,
    company_name: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
) -> PIPatentRecord | None:
    """Query USPTO ODP for patents where the PI is a named inventor.

    Uses PatentsViewClient when available (rate limiting, caching, retry).
    Falls back to bare httpx calls otherwise.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    logger.debug("Using PatentsViewClient for '{}'", pi_name)
    try:
        client = PatentsViewClient()
        try:
            # Query by company name to get patents, then we'll have all
            # inventor/assignee data in the results
            patents = client.query_patents_by_assignee(
                company_name=company_name or last,
                max_patents=100,
            )
        finally:
            if hasattr(client, "close"):
                client.close()
        if not patents:
            return None

        titles = []
        assignees: set[str] = set()
        dates: list[str] = []
        for p in patents:
            t = p.get("patent_title", "")
            if t and t not in titles and len(titles) < 5:
                titles.append(t)
            org = p.get("assignee_organization", "")
            if org:
                assignees.add(org)
            d = p.get("grant_date") or p.get("patent_date", "")
            if d:
                dates.append(d)

        return PIPatentRecord(
            total_patents=len(patents),
            sample_titles=titles,
            assignees=sorted(assignees),
            date_range=(min(dates) if dates else None, max(dates) if dates else None),
        )
    except Exception as e:
        logger.debug("PatentsViewClient error for '{}': {}", pi_name, e)
        return None


def lookup_pi_patents_with_fallback(
    pi_name: str,
    company_name: str | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    lens_rate_limiter: RateLimiter | None = None,
) -> PIPatentRecord | None:
    """Try PatentsView first, fall back to Lens.org for patent lookups.

    Parameters match :func:`lookup_pi_patents` with an additional
    *lens_rate_limiter* for the fallback Lens.org client.
    """
    result = lookup_pi_patents(pi_name, company_name, rate_limiter=rate_limiter)
    if result is not None:
        return result

    logger.info(
        "No PatentsView data for '{}'; falling back to Lens.org", pi_name
    )

    try:
        with LensPatentClient(rate_limiter=lens_rate_limiter) as lens:
            if company_name:
                records = lens.search_patents_by_assignee(company_name)
            else:
                first, last = _split_pi_name(pi_name)
                if not last:
                    return None
                records = lens.search_patents_by_inventor(f"{first} {last}".strip())

        if not records:
            return None

        sample_titles = [r.title for r in records[:5] if r.title]

        assignees: set[str] = set()
        for r in records:
            if r.assignee:
                assignees.add(r.assignee)

        filing_dates = [r.filing_date for r in records if r.filing_date]
        date_range: tuple[str | None, str | None] = (
            min(filing_dates) if filing_dates else None,
            max(filing_dates) if filing_dates else None,
        )

        return PIPatentRecord(
            total_patents=len(records),
            sample_titles=sample_titles,
            assignees=sorted(assignees),
            date_range=date_range,
        )
    except Exception as e:
        logger.debug("Lens.org fallback error for '{}': {}", pi_name, e)
        return None


def lookup_pi_publications(
    pi_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> PIPublicationRecord | None:
    """Query Semantic Scholar for the PI's publication history.

    Uses :class:`SemanticScholarClient` when the library is available;
    falls back to inline httpx calls for standalone operation.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    search_query = f"{first} {last}".strip()

    with SemanticScholarClient(rate_limiter=rate_limiter) as s2:
        try:
            rec = s2.lookup_author(search_query)
        except Exception as e:
            logger.debug("Semantic Scholar API error for {}: {}", pi_name, e)
            return None
    if rec is None:
        return None
    return PIPublicationRecord(
        total_papers=rec.total_papers,
        h_index=rec.h_index,
        citation_count=rec.citation_count,
        sample_titles=rec.sample_titles,
        affiliations=rec.affiliations,
    )


def lookup_pi_orcid(
    pi_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
) -> ORCIDRecord | None:
    """Search the ORCID public API for a PI's researcher profile.

    Uses :class:`ORCIDClient` when the library is available;
    falls back to inline httpx calls for standalone operation.
    """
    first, last = _split_pi_name(pi_name)
    if not last:
        return None

    with ORCIDClient(rate_limiter=rate_limiter) as orcid:
        try:
            rec = orcid.lookup(pi_name)
        except Exception as e:
            logger.debug("ORCID API error for {}: {}", pi_name, e)
            return None
    if rec is None:
        return None
    return ORCIDRecord(
        orcid_id=rec.orcid_id,
        given_name=rec.given_name,
        family_name=rec.family_name,
        affiliations=rec.affiliations,
        works_count=rec.works_count,
        sample_work_titles=rec.sample_work_titles,
        funding_count=rec.funding_count,
        keywords=rec.keywords,
    )


# ---------------------------------------------------------------------------
# Cross-fallback wrappers
# ---------------------------------------------------------------------------


def lookup_pi_publications_with_fallback(
    pi_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
    orcid_rate_limiter: RateLimiter | None = None,
) -> PIPublicationRecord | None:
    """Try Semantic Scholar first, fall back to ORCID works data.

    Parameters match :func:`lookup_pi_publications` with an additional
    *orcid_rate_limiter* for the fallback ORCID client.
    """
    result = lookup_pi_publications(pi_name, rate_limiter=rate_limiter)
    if result is not None:
        return result

    logger.info(
        "No Semantic Scholar data for '{}'; falling back to ORCID works",
        pi_name,
    )
    orcid_rec = lookup_pi_orcid(pi_name, rate_limiter=orcid_rate_limiter)
    if orcid_rec is None:
        return None

    return PIPublicationRecord(
        total_papers=orcid_rec.works_count,
        h_index=None,
        citation_count=0,
        sample_titles=orcid_rec.sample_work_titles,
        affiliations=orcid_rec.affiliations,
    )


def lookup_pi_orcid_with_fallback(
    pi_name: str,
    *,
    rate_limiter: RateLimiter | None = None,
    semantic_scholar_rate_limiter: RateLimiter | None = None,  # noqa: ARG001
) -> ORCIDRecord | None:
    """Look up ORCID profile, returning None if not found.

    Accepts *semantic_scholar_rate_limiter* for API symmetry with the other
    ``_with_fallback`` wrappers, but does **not** synthesize a fake
    :class:`ORCIDRecord` from Semantic Scholar data — downstream code
    treats a non-None record as a real ORCID profile and would print an
    empty ORCID ID.
    """
    return lookup_pi_orcid(pi_name, rate_limiter=rate_limiter)

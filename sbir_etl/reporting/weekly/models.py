"""Shared dataclasses for the weekly awards report."""

from dataclasses import dataclass, field


@dataclass
class CompanyResearch:
    """Results of web research on an awardee company."""

    summary: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class SolicitationTopic:
    """Solicitation topic details from SBIR.gov API."""

    topic_code: str
    solicitation_number: str
    title: str
    description: str | None
    agency: str | None
    program: str | None

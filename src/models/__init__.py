"""Data models for the SBIR ETL pipeline."""

from .award import Award, RawAward
from .company import Company, CompanyMatch, RawCompany
from .patent import Patent, PatentCitation, RawPatent
from .quality import (
    DataQualitySummary,
    EnrichmentResult,
    QualityIssue,
    QualityReport,
    QualitySeverity,
)
from .researcher import RawResearcher, Researcher

__all__ = [
    # Awards
    "Award",
    "RawAward",
    # Companies
    "Company",
    "CompanyMatch",
    "RawCompany",
    # Patents
    "Patent",
    "PatentCitation",
    "RawPatent",
    # Researchers
    "Researcher",
    "RawResearcher",
    # Quality
    "QualityIssue",
    "QualityReport",
    "QualitySeverity",
    "EnrichmentResult",
    "DataQualitySummary",
]

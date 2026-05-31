"""Data models for the SBIR ETL pipeline — lazily imported to avoid heavy optional-dependency load at package import time."""

from importlib import import_module
from typing import Any


_LAZY_BY_MODULE: dict[str, tuple[str, ...]] = {
    "sbir_etl.models.award": ("Award", "RawAward"),
    "sbir_etl.models.cet_models": (
        "CETArea",
        "CETAssessment",
        "CETClassification",
        "ClassificationLevel",
        "CompanyCETProfile",
        "EvidenceStatement",
    ),
    "sbir_etl.models.company": ("Company", "CompanyMatch", "RawCompany"),
    "sbir_etl.models.organization": ("Organization", "OrganizationMatch"),
    "sbir_etl.models.patent": ("Patent", "PatentCitation", "RawPatent"),
    "sbir_etl.models.phase_iii_candidate": ("PhaseIIICandidate", "SignalClass"),
    "sbir_etl.models.researcher": ("Researcher", "RawResearcher"),
    "sbir_etl.models.quality": (
        "DataQualitySummary",
        "EnrichmentResult",
        "QualityIssue",
        "QualityReport",
        "QualitySeverity",
    ),
    "sbir_etl.models.sec_edgar": (
        "CompanyEdgarProfile",
        "EdgarCompanyMatch",
        "EdgarFiling",
        "EdgarFinancials",
        "EdgarFormDFiling",
        "EdgarMAEvent",
        "FilingType",
        "MAAcquisitionType",
    ),
    "sbir_etl.models.solicitation": ("Solicitation",),
    "sbir_etl.models.statistical_reports": (
        "ExecutiveSummary",
        "ModuleMetrics",
        "PerformanceMetrics",
        "PipelineMetrics",
        "ReportArtifact",
        "ReportCollection",
        "ReportFormat",
    ),
}

_LAZY_MAP: dict[str, str] = {
    symbol: module for module, symbols in _LAZY_BY_MODULE.items() for symbol in symbols
}

__all__: list[str] = sorted(_LAZY_MAP)


def __getattr__(name: str) -> Any:
    """Lazily import and cache the requested attribute."""
    module_path = _LAZY_MAP.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_path), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy-export names for tab completion."""
    return sorted(set(__all__) | set(globals().keys()))

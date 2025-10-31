"""
Data models for the SBIR ETL pipeline.

This module intentionally avoids importing heavy or environment-dependent submodules at
package import time. Importing submodules (which may require optional dependencies such
as `neo4j`, `duckdb`, or `dagster`) can cause import-time failures when running tests
or tooling in constrained environments.

Consumers can still access models via attribute access on the package, e.g.:

    from src.models import Award
    a = Award(...)

The attributes are loaded lazily on first access using importlib, which keeps the
package import lightweight and import-safe for environments that do not have all
optional dependencies available.
"""

from importlib import import_module
from typing import Any, Dict, List

# Public API exported by this package. Keep this list in sync with the lazy mapping below.
__all__: list[str] = [
    # Awards
    "Award",
    "RawAward",
    # CET Classification
    "CETArea",
    "CETAssessment",
    "CETClassification",
    "ClassificationLevel",
    "CompanyCETProfile",
    "EvidenceStatement",
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
    # Statistical Reports
    "PipelineMetrics",
    "ModuleMetrics",
    "ReportCollection",
    "ReportArtifact",
    "PerformanceMetrics",
    "ExecutiveSummary",
    "ReportFormat",
]

# Mapping of exported symbol -> (module_path, attribute_name)
# When a symbol is accessed on this package, the target module will be imported
# and the attribute will be resolved and cached in the module globals for future use.
_lazy_mapping: dict[str, tuple] = {
    # Award models
    "Award": ("src.models.award", "Award"),
    "RawAward": ("src.models.award", "RawAward"),
    # CET models
    "CETArea": ("src.models.cet_models", "CETArea"),
    "CETAssessment": ("src.models.cet_models", "CETAssessment"),
    "CETClassification": ("src.models.cet_models", "CETClassification"),
    "ClassificationLevel": ("src.models.cet_models", "ClassificationLevel"),
    "CompanyCETProfile": ("src.models.cet_models", "CompanyCETProfile"),
    "EvidenceStatement": ("src.models.cet_models", "EvidenceStatement"),
    # Company models
    "Company": ("src.models.company", "Company"),
    "CompanyMatch": ("src.models.company", "CompanyMatch"),
    "RawCompany": ("src.models.company", "RawCompany"),
    # Patent models
    "Patent": ("src.models.patent", "Patent"),
    "PatentCitation": ("src.models.patent", "PatentCitation"),
    "RawPatent": ("src.models.patent", "RawPatent"),
    # Researcher models
    "Researcher": ("src.models.researcher", "Researcher"),
    "RawResearcher": ("src.models.researcher", "RawResearcher"),
    # Quality models
    "DataQualitySummary": ("src.models.quality", "DataQualitySummary"),
    "EnrichmentResult": ("src.models.quality", "EnrichmentResult"),
    "QualityIssue": ("src.models.quality", "QualityIssue"),
    "QualityReport": ("src.models.quality", "QualityReport"),
    "QualitySeverity": ("src.models.quality", "QualitySeverity"),
    # Statistical Report models
    "ExecutiveSummary": ("src.models.statistical_reports", "ExecutiveSummary"),
    "ModuleMetrics": ("src.models.statistical_reports", "ModuleMetrics"),
    "PerformanceMetrics": ("src.models.statistical_reports", "PerformanceMetrics"),
    "PipelineMetrics": ("src.models.statistical_reports", "PipelineMetrics"),
    "ReportArtifact": ("src.models.statistical_reports", "ReportArtifact"),
    "ReportCollection": ("src.models.statistical_reports", "ReportCollection"),
    "ReportFormat": ("src.models.statistical_reports", "ReportFormat"),
}


def __getattr__(name: str) -> Any:
    """
    Lazily import and return the requested attribute.

    This function is invoked by Python when attribute `name` is not found in the
    module globals. It imports the underlying module and fetches the attribute,
    caching it in the package globals so subsequent accesses do not re-import.
    """
    if name in _lazy_mapping:
        module_path, attr_name = _lazy_mapping[name]
        module = import_module(module_path)
        try:
            value = getattr(module, attr_name)
        except AttributeError as exc:
            raise AttributeError(
                f"Module '{module_path}' does not define attribute '{attr_name}'"
            ) from exc
        # Cache for future lookups
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """
    Enhance completion by exposing defined __all__ items alongside module globals.
    """
    return sorted(list(__all__) + list(globals().keys()))

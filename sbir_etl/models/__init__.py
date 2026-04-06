"""
Data models for the SBIR ETL pipeline.

This module intentionally avoids importing heavy or environment-dependent submodules at
package import time. Importing submodules (which may require optional dependencies such
as `neo4j`, `duckdb`, or `dagster`) can cause import-time failures when running tests
or tooling in constrained environments.

Consumers can still access models via attribute access on the package, e.g.:

    from sbir_etl.models import Award
    a = Award(...)

The attributes are loaded lazily on first access using importlib, which keeps the
package import lightweight and import-safe for environments that do not have all
optional dependencies available.
"""

from importlib import import_module
from typing import Any


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
    # Organizations
    "Organization",
    "OrganizationMatch",
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
    # SEC EDGAR
    "CompanyEdgarProfile",
    "EdgarCompanyMatch",
    "EdgarFiling",
    "EdgarFinancials",
    "EdgarFormDFiling",
    "EdgarMAEvent",
    "FilingType",
    "MAAcquisitionType",
    # Solicitations
    "Solicitation",
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
_lazy_mapping: dict[str, tuple[str, str]] = {
    # Award models
    "Award": ("sbir_etl.models.award", "Award"),
    "RawAward": ("sbir_etl.models.award", "RawAward"),
    # CET models
    "CETArea": ("sbir_etl.models.cet_models", "CETArea"),
    "CETAssessment": ("sbir_etl.models.cet_models", "CETAssessment"),
    "CETClassification": ("sbir_etl.models.cet_models", "CETClassification"),
    "ClassificationLevel": ("sbir_etl.models.cet_models", "ClassificationLevel"),
    "CompanyCETProfile": ("sbir_etl.models.cet_models", "CompanyCETProfile"),
    "EvidenceStatement": ("sbir_etl.models.cet_models", "EvidenceStatement"),
    # Company models
    "Company": ("sbir_etl.models.company", "Company"),
    "CompanyMatch": ("sbir_etl.models.company", "CompanyMatch"),
    "RawCompany": ("sbir_etl.models.company", "RawCompany"),
    # Organization models
    "Organization": ("sbir_etl.models.organization", "Organization"),
    "OrganizationMatch": ("sbir_etl.models.organization", "OrganizationMatch"),
    # Patent models
    "Patent": ("sbir_etl.models.patent", "Patent"),
    "PatentCitation": ("sbir_etl.models.patent", "PatentCitation"),
    "RawPatent": ("sbir_etl.models.patent", "RawPatent"),
    # Researcher models
    "Researcher": ("sbir_etl.models.researcher", "Researcher"),
    "RawResearcher": ("sbir_etl.models.researcher", "RawResearcher"),
    # Quality models
    "DataQualitySummary": ("sbir_etl.models.quality", "DataQualitySummary"),
    "EnrichmentResult": ("sbir_etl.models.quality", "EnrichmentResult"),
    "QualityIssue": ("sbir_etl.models.quality", "QualityIssue"),
    "QualityReport": ("sbir_etl.models.quality", "QualityReport"),
    "QualitySeverity": ("sbir_etl.models.quality", "QualitySeverity"),
    # SEC EDGAR models
    "CompanyEdgarProfile": ("sbir_etl.models.sec_edgar", "CompanyEdgarProfile"),
    "EdgarCompanyMatch": ("sbir_etl.models.sec_edgar", "EdgarCompanyMatch"),
    "EdgarFiling": ("sbir_etl.models.sec_edgar", "EdgarFiling"),
    "EdgarFinancials": ("sbir_etl.models.sec_edgar", "EdgarFinancials"),
    "EdgarFormDFiling": ("sbir_etl.models.sec_edgar", "EdgarFormDFiling"),
    "EdgarMAEvent": ("sbir_etl.models.sec_edgar", "EdgarMAEvent"),
    "FilingType": ("sbir_etl.models.sec_edgar", "FilingType"),
    "MAAcquisitionType": ("sbir_etl.models.sec_edgar", "MAAcquisitionType"),
    # Solicitation models
    "Solicitation": ("sbir_etl.models.solicitation", "Solicitation"),
    # Statistical Report models
    "ExecutiveSummary": ("sbir_etl.models.statistical_reports", "ExecutiveSummary"),
    "ModuleMetrics": ("sbir_etl.models.statistical_reports", "ModuleMetrics"),
    "PerformanceMetrics": ("sbir_etl.models.statistical_reports", "PerformanceMetrics"),
    "PipelineMetrics": ("sbir_etl.models.statistical_reports", "PipelineMetrics"),
    "ReportArtifact": ("sbir_etl.models.statistical_reports", "ReportArtifact"),
    "ReportCollection": ("sbir_etl.models.statistical_reports", "ReportCollection"),
    "ReportFormat": ("sbir_etl.models.statistical_reports", "ReportFormat"),
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

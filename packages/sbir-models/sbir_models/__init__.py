"""Standalone SBIR data models package.

This package re-exports Pydantic models from ``sbir_etl.models`` so that
downstream projects can depend on ``sbir-models`` without pulling in the
full ETL pipeline and its heavy dependencies (Dagster, DuckDB, etc.).

Install standalone::

    pip install sbir-models

Or as part of the full pipeline::

    pip install sbir-analytics
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


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
    # Contracts
    "FederalContract",
    "CompetitionType",
    "ContractStatus",
    "VendorMatch",
    # Categorization
    "ContractClassification",
    "CompanyClassification",
    # Transitions
    "TransitionResult",
]

# Mapping of symbol -> (module_path, attribute_name)
# Uses sbir_etl.models as the canonical source.
_lazy_mapping: dict[str, tuple[str, str]] = {
    "Award": ("sbir_etl.models.award", "Award"),
    "RawAward": ("sbir_etl.models.award", "RawAward"),
    "CETArea": ("sbir_etl.models.cet_models", "CETArea"),
    "CETAssessment": ("sbir_etl.models.cet_models", "CETAssessment"),
    "CETClassification": ("sbir_etl.models.cet_models", "CETClassification"),
    "ClassificationLevel": ("sbir_etl.models.cet_models", "ClassificationLevel"),
    "CompanyCETProfile": ("sbir_etl.models.cet_models", "CompanyCETProfile"),
    "EvidenceStatement": ("sbir_etl.models.cet_models", "EvidenceStatement"),
    "Company": ("sbir_etl.models.company", "Company"),
    "CompanyMatch": ("sbir_etl.models.company", "CompanyMatch"),
    "RawCompany": ("sbir_etl.models.company", "RawCompany"),
    "Organization": ("sbir_etl.models.organization", "Organization"),
    "OrganizationMatch": ("sbir_etl.models.organization", "OrganizationMatch"),
    "Patent": ("sbir_etl.models.patent", "Patent"),
    "PatentCitation": ("sbir_etl.models.patent", "PatentCitation"),
    "RawPatent": ("sbir_etl.models.patent", "RawPatent"),
    "Researcher": ("sbir_etl.models.researcher", "Researcher"),
    "RawResearcher": ("sbir_etl.models.researcher", "RawResearcher"),
    "DataQualitySummary": ("sbir_etl.models.quality", "DataQualitySummary"),
    "EnrichmentResult": ("sbir_etl.models.quality", "EnrichmentResult"),
    "QualityIssue": ("sbir_etl.models.quality", "QualityIssue"),
    "QualityReport": ("sbir_etl.models.quality", "QualityReport"),
    "QualitySeverity": ("sbir_etl.models.quality", "QualitySeverity"),
    "FederalContract": ("sbir_etl.models.contract_models", "FederalContract"),
    "CompetitionType": ("sbir_etl.models.contract_models", "CompetitionType"),
    "ContractStatus": ("sbir_etl.models.contract_models", "ContractStatus"),
    "VendorMatch": ("sbir_etl.models.contract_models", "VendorMatch"),
    "ContractClassification": ("sbir_etl.models.categorization", "ContractClassification"),
    "CompanyClassification": ("sbir_etl.models.categorization", "CompanyClassification"),
    "TransitionResult": ("sbir_etl.models.transition_models", "TransitionResult"),
}


def __getattr__(name: str) -> Any:
    if name in _lazy_mapping:
        module_path, attr_name = _lazy_mapping[name]
        module = import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(__all__) + list(globals().keys()))

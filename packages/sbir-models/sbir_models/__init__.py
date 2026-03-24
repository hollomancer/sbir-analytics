"""Standalone SBIR data models package.

Pydantic models for SBIR analytics pipelines. This package is fully
standalone — it requires only ``pydantic`` and works without the full
``sbir_etl`` dependency tree (Dagster, DuckDB, spacy, etc.).

Install standalone::

    pip install sbir-models

Or as part of the ETL library::

    pip install sbir-etl
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
    "Transition",
    "TransitionProfile",
]

# Mapping of symbol -> (module_path, attribute_name)
# All paths are relative to this package (sbir_models.*).
_lazy_mapping: dict[str, tuple[str, str]] = {
    "Award": ("sbir_models.award", "Award"),
    "RawAward": ("sbir_models.award", "RawAward"),
    "CETArea": ("sbir_models.cet_models", "CETArea"),
    "CETAssessment": ("sbir_models.cet_models", "CETAssessment"),
    "CETClassification": ("sbir_models.cet_models", "CETClassification"),
    "ClassificationLevel": ("sbir_models.cet_models", "ClassificationLevel"),
    "CompanyCETProfile": ("sbir_models.cet_models", "CompanyCETProfile"),
    "EvidenceStatement": ("sbir_models.cet_models", "EvidenceStatement"),
    "Company": ("sbir_models.company", "Company"),
    "CompanyMatch": ("sbir_models.company", "CompanyMatch"),
    "RawCompany": ("sbir_models.company", "RawCompany"),
    "Organization": ("sbir_models.organization", "Organization"),
    "OrganizationMatch": ("sbir_models.organization", "OrganizationMatch"),
    "Patent": ("sbir_models.patent", "Patent"),
    "PatentCitation": ("sbir_models.patent", "PatentCitation"),
    "RawPatent": ("sbir_models.patent", "RawPatent"),
    "Researcher": ("sbir_models.researcher", "Researcher"),
    "RawResearcher": ("sbir_models.researcher", "RawResearcher"),
    "DataQualitySummary": ("sbir_models.quality", "DataQualitySummary"),
    "EnrichmentResult": ("sbir_models.quality", "EnrichmentResult"),
    "QualityIssue": ("sbir_models.quality", "QualityIssue"),
    "QualityReport": ("sbir_models.quality", "QualityReport"),
    "QualitySeverity": ("sbir_models.quality", "QualitySeverity"),
    "FederalContract": ("sbir_models.contract_models", "FederalContract"),
    "CompetitionType": ("sbir_models.contract_models", "CompetitionType"),
    "ContractStatus": ("sbir_models.contract_models", "ContractStatus"),
    "VendorMatch": ("sbir_models.contract_models", "VendorMatch"),
    "ContractClassification": ("sbir_models.categorization", "ContractClassification"),
    "CompanyClassification": ("sbir_models.categorization", "CompanyClassification"),
    "Transition": ("sbir_models.transition_models", "Transition"),
    "TransitionProfile": ("sbir_models.transition_models", "TransitionProfile"),
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

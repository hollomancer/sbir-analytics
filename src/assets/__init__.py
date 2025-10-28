"""Dagster assets package for SBIR ETL pipeline.

This package avoids importing asset modules at package import time to prevent
heavy optional dependencies (e.g., dagster, neo4j, duckdb) from causing import
errors during test collection or in constrained environments.

Consumers should import specific assets directly, for example:

    from src.assets.example_assets import raw_sbir_data

This module exposes a lazy import mechanism: accessing a symbol defined in
``__all__`` will dynamically import the underlying module and attribute on
first access and cache it for subsequent lookups.
"""

from importlib import import_module
from typing import Any, Dict, List, Tuple

# Public API exported by this package. Keep this list in sync with the lazy mapping below.
__all__: List[str] = [
    "raw_sbir_data",
    "validated_sbir_data",
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    "parsed_uspto_assignments",
    "parsed_uspto_assignees",
    "parsed_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    "uspto_assignments_parsing_check",
    "uspto_assignees_parsing_check",
    "uspto_assignors_parsing_check",
    "uspto_documentids_parsing_check",
    "uspto_conveyances_parsing_check",
    "validated_uspto_assignments",
    "uspto_rf_id_asset_check",
    "uspto_completeness_asset_check",
    "uspto_referential_asset_check",
    "transformed_patent_assignments",
    "transformed_patents",
    "transformed_patent_entities",
    "uspto_transformation_success_check",
    "uspto_company_linkage_check",
    "neo4j_patents",
    "neo4j_patent_assignments",
    "neo4j_patent_entities",
    "neo4j_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
    "uspto_ai_extract_to_duckdb",
    "uspto_ai_deduplicate",
    "uspto_ai_human_sample_extraction",
    "neo4j_cetarea_nodes",
    "neo4j_award_cet_enrichment",
    "neo4j_company_cet_enrichment",
    "neo4j_award_cet_relationships",
    "neo4j_company_cet_relationships",
    "contracts_sample",
    "vendor_resolution",
    "transition_scores_v1",
    "transition_evidence_v1",
    "transition_analytics",
]

# Map exported symbol -> (module_path, attribute_name).
# Module paths are package-qualified so importlib can resolve them.
_lazy_mapping: Dict[str, Tuple[str, str]] = {
    # example_assets
    "raw_sbir_data": ("src.assets.example_assets", "raw_sbir_data"),
    "validated_sbir_data": ("src.assets.example_assets", "validated_sbir_data"),
    # uspto_assets
    "raw_uspto_assignments": ("src.assets.uspto_assets", "raw_uspto_assignments"),
    "raw_uspto_assignees": ("src.assets.uspto_assets", "raw_uspto_assignees"),
    "raw_uspto_assignors": ("src.assets.uspto_assets", "raw_uspto_assignors"),
    "raw_uspto_documentids": ("src.assets.uspto_assets", "raw_uspto_documentids"),
    "raw_uspto_conveyances": ("src.assets.uspto_assets", "raw_uspto_conveyances"),
    "parsed_uspto_assignments": ("src.assets.uspto_assets", "parsed_uspto_assignments"),
    "parsed_uspto_assignees": ("src.assets.uspto_assets", "parsed_uspto_assignees"),
    "parsed_uspto_assignors": ("src.assets.uspto_assets", "parsed_uspto_assignors"),
    "parsed_uspto_documentids": ("src.assets.uspto_assets", "parsed_uspto_documentids"),
    "parsed_uspto_conveyances": ("src.assets.uspto_assets", "parsed_uspto_conveyances"),
    "uspto_assignments_parsing_check": (
        "src.assets.uspto_assets",
        "uspto_assignments_parsing_check",
    ),
    "uspto_assignees_parsing_check": ("src.assets.uspto_assets", "uspto_assignees_parsing_check"),
    "uspto_assignors_parsing_check": ("src.assets.uspto_assets", "uspto_assignors_parsing_check"),
    "uspto_documentids_parsing_check": (
        "src.assets.uspto_assets",
        "uspto_documentids_parsing_check",
    ),
    "uspto_conveyances_parsing_check": (
        "src.assets.uspto_assets",
        "uspto_conveyances_parsing_check",
    ),
    # uspto_validation_assets
    "validated_uspto_assignments": (
        "src.assets.uspto_validation_assets",
        "validated_uspto_assignments",
    ),
    "uspto_rf_id_asset_check": ("src.assets.uspto_validation_assets", "uspto_rf_id_asset_check"),
    "uspto_completeness_asset_check": (
        "src.assets.uspto_validation_assets",
        "uspto_completeness_asset_check",
    ),
    "uspto_referential_asset_check": (
        "src.assets.uspto_validation_assets",
        "uspto_referential_asset_check",
    ),
    # uspto_transformation_assets
    "transformed_patent_assignments": (
        "src.assets.uspto_transformation_assets",
        "transformed_patent_assignments",
    ),
    "transformed_patents": ("src.assets.uspto_transformation_assets", "transformed_patents"),
    "transformed_patent_entities": (
        "src.assets.uspto_transformation_assets",
        "transformed_patent_entities",
    ),
    "uspto_transformation_success_check": (
        "src.assets.uspto_transformation_assets",
        "uspto_transformation_success_check",
    ),
    "uspto_company_linkage_check": (
        "src.assets.uspto_transformation_assets",
        "uspto_company_linkage_check",
    ),
    # uspto_neo4j_loading_assets
    "neo4j_patents": ("src.assets.uspto_neo4j_loading_assets", "neo4j_patents"),
    "neo4j_patent_assignments": (
        "src.assets.uspto_neo4j_loading_assets",
        "neo4j_patent_assignments",
    ),
    "neo4j_patent_entities": ("src.assets.uspto_neo4j_loading_assets", "neo4j_patent_entities"),
    "neo4j_patent_relationships": (
        "src.assets.uspto_neo4j_loading_assets",
        "neo4j_patent_relationships",
    ),
    "patent_load_success_rate": (
        "src.assets.uspto_neo4j_loading_assets",
        "patent_load_success_rate",
    ),
    "assignment_load_success_rate": (
        "src.assets.uspto_neo4j_loading_assets",
        "assignment_load_success_rate",
    ),
    "patent_relationship_cardinality": (
        "src.assets.uspto_neo4j_loading_assets",
        "patent_relationship_cardinality",
    ),
    # uspto_ai_extraction_assets
    "uspto_ai_extract_to_duckdb": (
        "src.assets.uspto_ai_extraction_assets",
        "uspto_ai_extract_to_duckdb",
    ),
    "uspto_ai_deduplicate": (
        "src.assets.uspto_ai_extraction_assets",
        "uspto_ai_deduplicate",
    ),
    "uspto_ai_human_sample_extraction": (
        "src.assets.uspto_ai_extraction_assets",
        "uspto_ai_human_sample_extraction",
    ),
    # cet_neo4j_loading_assets
    "neo4j_cetarea_nodes": (
        "src.assets.cet_neo4j_loading_assets",
        "neo4j_cetarea_nodes",
    ),
    "neo4j_award_cet_enrichment": (
        "src.assets.cet_neo4j_loading_assets",
        "neo4j_award_cet_enrichment",
    ),
    "neo4j_company_cet_enrichment": (
        "src.assets.cet_neo4j_loading_assets",
        "neo4j_company_cet_enrichment",
    ),
    "neo4j_award_cet_relationships": (
        "src.assets.cet_neo4j_loading_assets",
        "neo4j_award_cet_relationships",
    ),
    "neo4j_company_cet_relationships": (
        "src.assets.cet_neo4j_loading_assets",
        "neo4j_company_cet_relationships",
    ),
    # transition_assets
    "contracts_sample": ("src.assets.transition_assets", "contracts_sample"),
    "vendor_resolution": ("src.assets.transition_assets", "vendor_resolution"),
    "transition_scores_v1": ("src.assets.transition_assets", "transition_scores_v1"),
    "transition_evidence_v1": ("src.assets.transition_assets", "transition_evidence_v1"),
    "transition_analytics": ("src.assets.transition_assets", "transition_analytics"),
    # transition asset checks
    "contracts_sample_quality_check": (
        "src.assets.transition_assets",
        "contracts_sample_quality_check",
    ),
    "vendor_resolution_quality_check": (
        "src.assets.transition_assets",
        "vendor_resolution_quality_check",
    ),
    "transition_scores_quality_check": (
        "src.assets.transition_assets",
        "transition_scores_quality_check",
    ),
    "transition_evidence_quality_check": (
        "src.assets.transition_assets",
        "transition_evidence_quality_check",
    ),
}


def __getattr__(name: str) -> Any:
    """
    Lazily import and return the requested attribute.

    This hook is invoked when an attribute is not found in module globals.
    It imports the underlying module and fetches the attribute, caching it
    in the module globals for future accesses.
    """
    if name in _lazy_mapping:
        module_path, attr_name = _lazy_mapping[name]
        module = import_module(module_path)
        try:
            value = getattr(module, attr_name)
        except AttributeError as exc:
            raise AttributeError(f"Module '{module_path}' does not define '{attr_name}'") from exc
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    """Expose a helpful completion list."""
    return sorted(list(__all__) + list(globals().keys()))

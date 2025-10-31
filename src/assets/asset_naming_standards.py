"""
Asset naming standards and conventions for the SBIR ETL pipeline.

This module defines the standardized naming conventions that should be applied
across all asset files to ensure consistency and clarity in the pipeline.

Naming Convention:
- Stage prefixes: raw_, validated_, enriched_, transformed_, loaded_
- Clear descriptive names indicating data type and purpose
- Consistent group names reflecting pipeline stages
"""

from enum import Enum
from typing import Dict, List


class PipelineStage(Enum):
    """Pipeline stages with corresponding prefixes and group names."""
    
    EXTRACTION = ("raw_", "extraction")
    VALIDATION = ("validated_", "validation") 
    ENRICHMENT = ("enriched_", "enrichment")
    TRANSFORMATION = ("transformed_", "transformation")
    LOADING = ("loaded_", "loading")


class AssetNamingStandards:
    """Standardized asset naming conventions."""
    
    # Stage prefixes for asset names
    STAGE_PREFIXES = {
        "extraction": "raw_",
        "validation": "validated_", 
        "enrichment": "enriched_",
        "transformation": "transformed_",
        "loading": "loaded_"
    }
    
    # Group names for logical pipeline organization
    GROUP_NAMES = {
        "extraction": "extraction",
        "validation": "validation",
        "enrichment": "enrichment", 
        "transformation": "transformation",
        "loading": "loading"
    }
    
    # Data entity types for consistent naming
    ENTITY_TYPES = [
        "sbir_awards",
        "usaspending_data",
        "uspto_patents", 
        "uspto_assignments",
        "uspto_entities",
        "cet_classifications",
        "companies",
        "contracts",
        "transitions"
    ]


def get_standardized_asset_name(stage: str, entity: str, suffix: str = "") -> str:
    """
    Generate a standardized asset name following conventions.
    
    Args:
        stage: Pipeline stage (extraction, validation, enrichment, transformation, loading)
        entity: Data entity type (sbir_awards, patents, etc.)
        suffix: Optional suffix for specialized assets
        
    Returns:
        Standardized asset name with proper prefix
    """
    prefix = AssetNamingStandards.STAGE_PREFIXES.get(stage, "")
    base_name = f"{prefix}{entity}"
    
    if suffix:
        return f"{base_name}_{suffix}"
    return base_name


def get_group_name(stage: str) -> str:
    """Get the standardized group name for a pipeline stage."""
    return AssetNamingStandards.GROUP_NAMES.get(stage, stage)


# Asset renaming mappings for existing assets
ASSET_RENAMING_MAP = {
    # SBIR assets
    "raw_sbir_awards": "raw_sbir_awards",  # Already correct
    "validated_sbir_awards": "validated_sbir_awards",  # Already correct
    "enriched_sbir_awards": "enriched_sbir_awards",  # Already correct
    
    # USAspending assets
    "usaspending_recipient_lookup": "raw_usaspending_recipients",
    "usaspending_transaction_normalized": "raw_usaspending_transactions", 
    "usaspending_dump_profile": "raw_usaspending_profile",
    
    # USPTO assets - raw discovery
    "raw_uspto_assignments": "raw_uspto_assignments",  # Already correct
    "raw_uspto_assignees": "raw_uspto_assignees",  # Already correct
    "raw_uspto_assignors": "raw_uspto_assignors",  # Already correct
    "raw_uspto_documentids": "raw_uspto_documentids",  # Already correct
    "raw_uspto_conveyances": "raw_uspto_conveyances",  # Already correct
    
    # USPTO assets - parsed
    "parsed_uspto_assignees": "validated_uspto_assignees",
    "parsed_uspto_assignors": "validated_uspto_assignors",
    "validated_uspto_assignments": "validated_uspto_assignments",  # Already correct
    
    # USPTO assets - transformed
    "transformed_patent_assignments": "transformed_patent_assignments",  # Already correct
    "transformed_patents": "transformed_patents",  # Already correct
    "transformed_patent_entities": "transformed_patent_entities",  # Already correct
    
    # USPTO assets - Neo4j loading
    "neo4j_patents": "loaded_patents",
    "neo4j_patent_assignments": "loaded_patent_assignments", 
    "neo4j_patent_entities": "loaded_patent_entities",
    "neo4j_patent_relationships": "loaded_patent_relationships",
    
    # CET assets
    "cet_taxonomy": "raw_cet_taxonomy",
    "cet_award_classifications": "enriched_cet_award_classifications",
    "cet_patent_classifications": "enriched_cet_patent_classifications",
    "cet_company_profiles": "transformed_cet_company_profiles",
    "cet_analytics": "transformed_cet_analytics",
    "cet_human_sampling": "raw_cet_human_sampling",
    "cet_iaa_report": "validated_cet_iaa_report",
    "cet_analytics_aggregates": "transformed_cet_analytics_aggregates",
    "cet_drift_detection": "validated_cet_drift_detection",
    
    # CET Neo4j loading
    "neo4j_cetarea_nodes": "loaded_cet_areas",
    "neo4j_award_cet_enrichment": "loaded_award_cet_enrichment",
    "neo4j_company_cet_enrichment": "loaded_company_cet_enrichment", 
    "neo4j_award_cet_relationships": "loaded_award_cet_relationships",
    "neo4j_company_cet_relationships": "loaded_company_cet_relationships",
    
    # Transition assets
    "contracts_ingestion": "raw_contracts",
    "contracts_sample": "validated_contracts_sample",
    "vendor_resolution": "enriched_vendor_resolution",
    "transition_scores_v1": "transformed_transition_scores",
    "transition_evidence_v1": "transformed_transition_evidence", 
    "transition_detections": "transformed_transition_detections",
    "transition_analytics": "transformed_transition_analytics",
    
    # Transition Neo4j loading
    "neo4j_transitions": "loaded_transitions",
    "neo4j_transition_relationships": "loaded_transition_relationships",
    "neo4j_transition_profiles": "loaded_transition_profiles",
    
    # USPTO AI assets
    "uspto_ai_ingest": "raw_uspto_ai_predictions",
    "uspto_ai_cache_stats": "validated_uspto_ai_cache_stats",
    "uspto_ai_human_sample": "raw_uspto_ai_human_sample",
    "uspto_ai_patent_join": "enriched_uspto_ai_patent_join",
    "uspto_ai_extract_to_duckdb": "raw_uspto_ai_extract",
    "uspto_ai_human_sample_extraction": "raw_uspto_ai_human_sample_extraction",
}

# Group name mappings for existing assets
GROUP_RENAMING_MAP = {
    "sbir_ingestion": "extraction",
    "usaspending_ingestion": "extraction", 
    "uspto": "extraction",
    "enrichment": "enrichment",
    "transition": "transformation",
    "ml": "enrichment",  # CET classification is enrichment
}
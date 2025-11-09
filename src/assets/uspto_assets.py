"""
Consolidated Dagster assets for USPTO patent data pipeline.

This module re-exports all USPTO assets from the modularized src.assets.uspto package.
For implementation details, see the individual modules in src/assets/uspto/:
- extraction.py: Raw file discovery
- parsing.py: File parsing and initial validation
- validation.py: Data quality validation and checks
- transformation.py: Data transformation and entity extraction
- loading.py: Neo4j graph database loading
- ai_extraction.py: AI-based entity extraction
- utils.py: Shared utilities and helpers

Pipeline Stages:
1. Extraction: Discover raw USPTO data files by table
2. Parsing: Parse raw files into structured data
3. Validation: Validate data quality, uniqueness, and integrity
4. Transformation: Transform into patent assignments and entities
5. Loading: Load into Neo4j graph database
6. AI Extraction: AI-based entity extraction (optional)

For backward compatibility, all assets are re-exported at the top level.
"""

from __future__ import annotations

# Import all assets from the modularized uspto package
from .uspto import (
    # Transformation
    JoinedRow,
    USPTOAssignmentJoiner,
    # Loading
    assignment_load_success_rate,
    # AI Extraction
    enriched_uspto_ai_patent_join,
    loaded_patent_assignments,
    loaded_patent_entities,
    loaded_patent_relationships,
    loaded_patents,
    # Backward compatibility aliases
    neo4j_patent_assignments,
    neo4j_patent_entities,
    neo4j_patent_relationships,
    neo4j_patents,
    # Parsing
    parsed_uspto_assignments,
    parsed_uspto_conveyances,
    parsed_uspto_documentids,
    patent_load_success_rate,
    patent_relationship_cardinality,
    raw_uspto_ai_extract,
    raw_uspto_ai_human_sample,
    raw_uspto_ai_human_sample_extraction,
    raw_uspto_ai_predictions,
    # Extraction
    raw_uspto_assignees,
    raw_uspto_assignments,
    raw_uspto_assignors,
    raw_uspto_conveyances,
    raw_uspto_documentids,
    transformed_patent_assignments,
    transformed_patent_entities,
    transformed_patents,
    uspto_ai_deduplicate,
    uspto_company_linkage_check,
    # Validation
    uspto_completeness_asset_check,
    uspto_referential_asset_check,
    uspto_rf_id_asset_check,
    uspto_transformation_success_check,
    validated_uspto_ai_cache_stats,
    validated_uspto_assignees,
    validated_uspto_assignments,
    validated_uspto_assignors,
)


__all__ = [
    # Extraction
    "raw_uspto_assignments",
    "raw_uspto_assignees",
    "raw_uspto_assignors",
    "raw_uspto_documentids",
    "raw_uspto_conveyances",
    # Parsing
    "parsed_uspto_assignments",
    "validated_uspto_assignees",
    "validated_uspto_assignors",
    "parsed_uspto_documentids",
    "parsed_uspto_conveyances",
    # Validation
    "validated_uspto_assignments",
    "uspto_rf_id_asset_check",
    "uspto_completeness_asset_check",
    "uspto_referential_asset_check",
    # Transformation
    "JoinedRow",
    "USPTOAssignmentJoiner",
    "transformed_patent_assignments",
    "transformed_patents",
    "transformed_patent_entities",
    "uspto_transformation_success_check",
    "uspto_company_linkage_check",
    # Loading
    "loaded_patents",
    "loaded_patent_assignments",
    "loaded_patent_entities",
    "loaded_patent_relationships",
    "patent_load_success_rate",
    "assignment_load_success_rate",
    "patent_relationship_cardinality",
    # AI Extraction
    "raw_uspto_ai_extract",
    "uspto_ai_deduplicate",
    "raw_uspto_ai_human_sample_extraction",
    "raw_uspto_ai_predictions",
    "validated_uspto_ai_cache_stats",
    "raw_uspto_ai_human_sample",
    "enriched_uspto_ai_patent_join",
    # Backward compatibility aliases
    "neo4j_patents",
    "neo4j_patent_assignments",
    "neo4j_patent_entities",
    "neo4j_patent_relationships",
]

"""USPTO (United States Patent and Trademark Office) assets package.

This package contains modularized Dagster assets for USPTO patent data processing,
including extraction, parsing, validation, transformation, and Neo4j loading.

Module Structure:
- utils: Shared utilities, helpers, and Dagster re-exports
- extraction: Raw file discovery assets
- parsing: File parsing and initial validation
- validation: Data quality validation and checks
- transformation: Data transformation and entity extraction
- loading: Neo4j graph database loading
- ai_extraction: AI-based entity extraction and predictions

Pipeline Stages:
1. Extraction: Discover raw USPTO data files by table
2. Parsing: Parse raw files into structured data
3. Validation: Validate data quality, uniqueness, and integrity
4. Transformation: Transform into patent assignments and entities
5. Loading: Load into Neo4j graph database
6. AI Extraction: AI-based entity extraction (optional)

Exported Assets:
- Raw: raw_uspto_assignments, raw_uspto_assignees, raw_uspto_assignors,
  raw_uspto_documentids, raw_uspto_conveyances
- Parsed: parsed_uspto_assignments, validated_uspto_assignees, validated_uspto_assignors,
  parsed_uspto_documentids, parsed_uspto_conveyances
- Validated: validated_uspto_assignments
- Transformed: transformed_patent_assignments, transformed_patents, transformed_patent_entities
- Loaded: loaded_patents, loaded_patent_assignments, loaded_patent_entities,
  loaded_patent_relationships
- AI: raw_uspto_ai_extract, uspto_ai_deduplicate, raw_uspto_ai_human_sample_extraction,
  raw_uspto_ai_predictions, validated_uspto_ai_cache_stats, raw_uspto_ai_human_sample,
  enriched_uspto_ai_patent_join
"""

from __future__ import annotations

# Extraction module
from .extraction import (
    raw_uspto_assignees,
    raw_uspto_assignments,
    raw_uspto_assignors,
    raw_uspto_conveyances,
    raw_uspto_documentids,
)

# Parsing module
from .parsing import (
    parsed_uspto_assignments,
    parsed_uspto_conveyances,
    parsed_uspto_documentids,
    validated_uspto_assignees,
    validated_uspto_assignors,
)

# Validation module
from .validation import (
    uspto_completeness_asset_check,
    uspto_referential_asset_check,
    uspto_rf_id_asset_check,
    validated_uspto_assignments,
)

# Transformation module
from .transformation import (
    JoinedRow,
    USPTOAssignmentJoiner,
    transformed_patent_assignments,
    transformed_patent_entities,
    transformed_patents,
    uspto_company_linkage_check,
    uspto_transformation_success_check,
)

# Loading module
from .loading import (
    assignment_load_success_rate,
    loaded_patent_assignments,
    loaded_patent_entities,
    loaded_patent_relationships,
    loaded_patents,
    patent_load_success_rate,
    patent_relationship_cardinality,
)

# AI Extraction module
from .ai_extraction import (
    enriched_uspto_ai_patent_join,
    raw_uspto_ai_extract,
    raw_uspto_ai_human_sample,
    raw_uspto_ai_human_sample_extraction,
    raw_uspto_ai_predictions,
    uspto_ai_deduplicate,
    validated_uspto_ai_cache_stats,
)

# Utility functions
from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetIn,
    MetadataValue,
    asset,
    asset_check,
)


# Backward compatibility aliases
neo4j_patents = loaded_patents
neo4j_patent_assignments = loaded_patent_assignments
neo4j_patent_entities = loaded_patent_entities
neo4j_patent_relationships = loaded_patent_relationships


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
    # Utility functions
    "asset",
    "asset_check",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "AssetIn",
    "MetadataValue",
]

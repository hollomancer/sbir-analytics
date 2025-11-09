"""CET (Critical & Emerging Technologies) assets package.

This package contains modularized Dagster assets for CET taxonomy processing,
classification, training, analytics, validation, company profiling, and Neo4j loading.

Module Structure:
- utils: Shared utilities (Dagster shims, I/O functions, metrics serialization)
- taxonomy: Taxonomy loading, validation, and checks
- classifications: Award and patent classification assets
- training: Classifier training and dataset generation assets
- analytics: Analytics computation and aggregation assets
- validation: Human sampling, IAA reports, and drift detection
- company: Company CET profile aggregation
- loading: Neo4j loading assets for CET data

Exported Assets:
- raw_cet_taxonomy, cet_taxonomy, cet_taxonomy_completeness_check
- enriched_cet_award_classifications, enriched_cet_patent_classifications
- cet_award_classifications_quality_check
- train_cet_patent_classifier, cet_award_training_dataset
- transformed_cet_analytics, transformed_cet_analytics_aggregates
- raw_cet_human_sampling, validated_cet_iaa_report, validated_cet_drift_detection
- transformed_cet_company_profiles, cet_company_profiles_check
- loaded_cet_areas, loaded_award_cet_enrichment, loaded_company_cet_enrichment
- loaded_award_cet_relationships, loaded_company_cet_relationships
"""

from __future__ import annotations

# Analytics module
from .analytics import transformed_cet_analytics, transformed_cet_analytics_aggregates

# Classifications module
from .classifications import (
    cet_award_classifications_quality_check,
    enriched_cet_award_classifications,
    enriched_cet_patent_classifications,
)

# Company module
from .company import cet_company_profiles_check, transformed_cet_company_profiles

# Loading module
from .loading import (
    loaded_award_cet_enrichment,
    loaded_award_cet_relationships,
    loaded_cet_areas,
    loaded_company_cet_enrichment,
    loaded_company_cet_relationships,
)

# Taxonomy module
from .taxonomy import (
    cet_taxonomy,
    cet_taxonomy_completeness_check,
    raw_cet_taxonomy,
    taxonomy_to_dataframe,
)

# Training module
from .training import cet_award_training_dataset, train_cet_patent_classifier

# Utility functions for use by other modules
from .utils import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    AssetKey,
    MetadataValue,
    Output,
    _read_parquet_or_ndjson,
    _serialize_metrics,
    asset,
    asset_check,
    save_dataframe_parquet,
)

# Validation module
from .validation import (
    raw_cet_human_sampling,
    validated_cet_drift_detection,
    validated_cet_iaa_report,
)


# Backward compatibility aliases
neo4j_cetarea_nodes = loaded_cet_areas
neo4j_award_cet_enrichment = loaded_award_cet_enrichment
neo4j_company_cet_enrichment = loaded_company_cet_enrichment
neo4j_award_cet_relationships = loaded_award_cet_relationships
neo4j_company_cet_relationships = loaded_company_cet_relationships


__all__ = [
    # Taxonomy
    "raw_cet_taxonomy",
    "cet_taxonomy",
    "cet_taxonomy_completeness_check",
    "taxonomy_to_dataframe",
    # Classifications
    "enriched_cet_award_classifications",
    "enriched_cet_patent_classifications",
    "cet_award_classifications_quality_check",
    # Training
    "train_cet_patent_classifier",
    "cet_award_training_dataset",
    # Analytics
    "transformed_cet_analytics",
    "transformed_cet_analytics_aggregates",
    # Validation
    "raw_cet_human_sampling",
    "validated_cet_iaa_report",
    "validated_cet_drift_detection",
    # Company
    "transformed_cet_company_profiles",
    "cet_company_profiles_check",
    # Loading
    "loaded_cet_areas",
    "loaded_award_cet_enrichment",
    "loaded_company_cet_enrichment",
    "loaded_award_cet_relationships",
    "loaded_company_cet_relationships",
    # Backward compatibility aliases
    "neo4j_cetarea_nodes",
    "neo4j_award_cet_enrichment",
    "neo4j_company_cet_enrichment",
    "neo4j_award_cet_relationships",
    "neo4j_company_cet_relationships",
    # Utility functions
    "save_dataframe_parquet",
    "_read_parquet_or_ndjson",
    "_serialize_metrics",
    # Dagster imports
    "asset",
    "asset_check",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "AssetExecutionContext",
    "AssetIn",
    "AssetKey",
    "MetadataValue",
    "Output",
]

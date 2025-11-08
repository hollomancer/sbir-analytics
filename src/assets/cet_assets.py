"""
Dagster assets for CET (Critical & Emerging Technologies) taxonomy.

This module re-exports all CET assets from the modularized src.assets.cet package.
For implementation details, see the individual modules in src/assets/cet/:
- taxonomy.py: Taxonomy loading and validation
- classifications.py: Award and patent classification
- training.py: Classifier training and dataset generation
- analytics.py: Analytics computation and aggregation
- validation.py: Human sampling, IAA reports, and drift detection
- company.py: Company CET profile aggregation
- loading.py: Neo4j loading assets
- utils.py: Shared utilities and Dagster shims

For backward compatibility, all assets are re-exported at the top level.
"""

from __future__ import annotations

# Import all assets from the modularized cet package
from .cet import (
    # Taxonomy
    cet_taxonomy,
    cet_taxonomy_completeness_check,
    raw_cet_taxonomy,
    taxonomy_to_dataframe,
    # Classifications
    cet_award_classifications_quality_check,
    enriched_cet_award_classifications,
    enriched_cet_patent_classifications,
    # Training
    cet_award_training_dataset,
    train_cet_patent_classifier,
    # Analytics
    transformed_cet_analytics,
    transformed_cet_analytics_aggregates,
    # Validation
    raw_cet_human_sampling,
    validated_cet_drift_detection,
    validated_cet_iaa_report,
    # Company
    cet_company_profiles_check,
    transformed_cet_company_profiles,
    # Loading
    loaded_award_cet_enrichment,
    loaded_award_cet_relationships,
    loaded_cet_areas,
    loaded_company_cet_enrichment,
    loaded_company_cet_relationships,
    # Backward compatibility aliases
    neo4j_award_cet_enrichment,
    neo4j_award_cet_relationships,
    neo4j_cetarea_nodes,
    neo4j_company_cet_enrichment,
    neo4j_company_cet_relationships,
    # Utility functions
    save_dataframe_parquet,
)

# Import helper functions for testing/mocking
from .cet.company import _get_neo4j_client
from .cet.utils import _read_parquet_or_ndjson


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
    "_get_neo4j_client",
    "_read_parquet_or_ndjson",
]

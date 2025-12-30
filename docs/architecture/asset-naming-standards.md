# Asset Naming Standards

## Overview

This document defines the standardized naming conventions for Dagster assets in the SBIR ETL pipeline. These conventions ensure consistency, clarity, and maintainability across all pipeline components.

## Naming Convention

### Stage Prefixes

All assets follow a consistent naming pattern based on their pipeline stage:

| Stage | Prefix | Group Name | Purpose |
|-------|--------|------------|---------|
| **Extraction** | `raw_` | `extraction` | Data extraction from sources |
| **Validation** | `validated_` | `validation` | Schema validation and quality checks |
| **Enrichment** | `enriched_` | `enrichment` | External data enrichment |
| **Transformation** | `transformed_` | `transformation` | Business logic and normalization |
| **Loading** | `loaded_` | `loading` | Database loading and relationship creation |

### Asset Name Structure

```text
{stage_prefix}{entity_type}[_{suffix}]
```

### Examples

- `raw_sbir_awards` - Raw SBIR award data
- `validated_uspto_assignments` - Validated USPTO assignment data
- `enriched_cet_award_classifications` - CET-enriched award classifications
- `transformed_patent_assignments` - Transformed patent assignment data
- `loaded_transitions` - Loaded transition data in Neo4j

### Entity Types

Common entity types used across the pipeline:

- `sbir_awards` - SBIR/STTR award data
- `usaspending_recipients` - USAspending recipient data
- `usaspending_transactions` - USAspending transaction data
- `uspto_patents` - USPTO patent data
- `uspto_assignments` - USPTO patent assignment data
- `uspto_entities` - USPTO patent entity data
- `cet_classifications` - CET classification data
- `companies` - Company profile data
- `contracts` - Federal contract data
- `transitions` - Technology transition data

## Group Organization

Assets are organized into logical groups that reflect pipeline stages:

### Extraction Group (`extraction`)

- Raw data extraction from CSV files, APIs, and databases
- File discovery and initial parsing
- Examples: `raw_sbir_awards`, `raw_uspto_assignments`

### Validation Group (`validation`)

- Schema validation and data quality checks
- Duplicate detection and data cleaning
- Examples: `validated_sbir_awards`, `validated_contracts_sample`

### Enrichment Group (`enrichment`)

- External API enrichment
- Fuzzy matching and entity resolution
- Classification and scoring
- Examples: `enriched_sbir_awards`, `enriched_cet_award_classifications`

### Transformation Group (`transformation`)

- Business logic application
- Data normalization and standardization
- Relationship preparation
- Examples: `transformed_patent_assignments`, `transformed_transition_scores`

### Loading Group (`loading`)

- Database loading operations
- Relationship creation
- Index and constraint management
- Examples: `loaded_patents`, `loaded_transitions`

## Change History

- **October 2025** – Standardized 47 asset function names and decorator parameters to follow the stage prefixes above.
- Updated 15 downstream dependencies to reference the renamed assets, ensuring Dagster dependency graphs remained intact.
- Consolidated group names (`sbir_ingestion`, `usaspending_ingestion`, `transition`, etc.) into the five-stage taxonomy (`extraction`, `validation`, `enrichment`, `transformation`, `loading`).
- Expanded `loaded_*` coverage to include Neo4j patent and transition loaders and aligned CET assets with the enrichment and transformation stages.

See project release notes for the full task breakdown and code references.

## Migration from Legacy Names

The following assets have been renamed to follow the new standards:

### SBIR Assets

- ✅ `raw_sbir_awards` (no change)
- ✅ `validated_sbir_awards` (no change)
- ✅ `enriched_sbir_awards` (no change)

### USAspending Assets

- `usaspending_recipient_lookup` → `raw_usaspending_recipients`
- `usaspending_transaction_normalized` → `raw_usaspending_transactions`

### USPTO Assets

- `parsed_uspto_assignees` → `validated_uspto_assignees`
- `parsed_uspto_assignors` → `validated_uspto_assignors`
- `neo4j_patents` → `loaded_patents`
- `neo4j_patent_assignments` → `loaded_patent_assignments`
- `neo4j_patent_entities` → `loaded_patent_entities`
- `neo4j_patent_relationships` → `loaded_patent_relationships`

### CET Assets

- `cet_taxonomy` → `raw_cet_taxonomy`
- `cet_award_classifications` → `enriched_cet_award_classifications`
- `cet_patent_classifications` → `enriched_cet_patent_classifications`
- `cet_company_profiles` → `transformed_cet_company_profiles`
- `neo4j_cetarea_nodes` → `loaded_cet_areas`
- `neo4j_award_cet_enrichment` → `loaded_award_cet_enrichment`
- `neo4j_company_cet_enrichment` → `loaded_company_cet_enrichment`
- `neo4j_award_cet_relationships` → `loaded_award_cet_relationships`
- `neo4j_company_cet_relationships` → `loaded_company_cet_relationships`

### Transition Assets

- `contracts_ingestion` → `raw_contracts`
- `contracts_sample` → `validated_contracts_sample`
- `vendor_resolution` → `enriched_vendor_resolution`
- `transition_scores_v1` → `transformed_transition_scores`
- `transition_evidence_v1` → `transformed_transition_evidence`
- `transition_detections` → `transformed_transition_detections`
- `transition_analytics` → `transformed_transition_analytics`
- `neo4j_transitions` → `loaded_transitions`
- `neo4j_transition_relationships` → `loaded_transition_relationships`
- `neo4j_transition_profiles` → `loaded_transition_profiles`

### USPTO AI Assets

- `uspto_ai_ingest` → `raw_uspto_ai_predictions`
- `uspto_ai_cache_stats` → `validated_uspto_ai_cache_stats`
- `uspto_ai_human_sample` → `raw_uspto_ai_human_sample`
- `uspto_ai_patent_join` → `enriched_uspto_ai_patent_join`
- `uspto_ai_extract_to_duckdb` → `raw_uspto_ai_extract`
- `uspto_ai_human_sample_extraction` → `raw_uspto_ai_human_sample_extraction`

## Group Name Changes

Legacy group names have been updated to reflect pipeline stages:

- `sbir_ingestion` → `extraction`
- `usaspending_ingestion` → `extraction`
- `uspto` → `extraction`
- `enrichment` → `enrichment` (no change)
- `transition` → `transformation`
- `ml` → `enrichment` (CET classification is enrichment)

## Benefits

### Clarity

- Asset names clearly indicate their position in the pipeline
- Stage prefixes make data flow obvious
- Consistent naming reduces cognitive load

### Maintainability

- Easier to locate assets by pipeline stage
- Consistent patterns simplify debugging
- Clear separation of concerns

### Scalability

- New assets follow established patterns
- Easy to extend pipeline stages
- Consistent documentation structure

## Implementation

The standardization was implemented using the `scripts/standardize_asset_names.py` script, which:

1. Applied consistent naming patterns across all asset files
2. Updated asset dependencies and references
3. Standardized group names
4. Updated job definitions to use new asset names

## Future Guidelines

When creating new assets:

1. **Follow the naming convention**: Use appropriate stage prefix and entity type
2. **Use correct group name**: Assign to the appropriate pipeline stage group
3. **Single responsibility**: Each asset should have one clear purpose
4. **Clear dependencies**: Use standardized asset names in dependencies
5. **Consistent descriptions**: Include clear, descriptive asset descriptions

## Validation

The naming standards can be validated using:

```bash

## Check for naming consistency

python scripts/standardize_asset_names.py --dry-run

## Validate asset definitions

dagster asset list

## Check group organization

dagster asset group list
```

## Related Documents

- [Pipeline Orchestration Patterns](../../.kiro/steering/pipeline-orchestration.md)
- [Code Structure Guidelines](../../.kiro/steering/structure.md)
- [Architecture Overview](detailed-overview.md)

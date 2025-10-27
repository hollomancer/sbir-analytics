# CET Neo4j Schema

This document describes the Neo4j data model used to represent the Crosscutting Emerging Technology (CET) taxonomy, award and company enrichment properties, and explicit relationships from awards and companies to CET areas.

Contents
- Overview
- Nodes
  - CETArea
  - Award enrichment properties
  - Company enrichment properties
- Relationships
  - Award APPLICABLE_TO CETArea
  - Company SPECIALIZES_IN CETArea
- Constraints and Indexes
- Loading assets and end-to-end job
- Input artifacts and contracts
- Idempotence, re-runs, and backfills
- Query examples


## Overview

The CET graph augments the core SBIR graph with:
- CETArea nodes for each taxonomy area
- Enrichment properties on Award and Company nodes reflecting model classifications
- Relationships connecting Awards and Companies to CETArea nodes

The model supports repeated runs and backfills using idempotent MERGE semantics. Properties carry a `taxonomy_version` allowing concurrent or sequential operation across taxonomy/model updates.


## Nodes

### CETArea

A node per CET taxonomy area.

Label
- CETArea

Required uniqueness
- `cet_id` (unique key; enforced by constraint)

Properties
- `cet_id` string (required, unique) — e.g., "artificial_intelligence"
- `name` string (required) — human-readable label
- `definition` string (optional) — descriptive definition
- `keywords` list<string> (optional) — normalized, lowercase keywords
- `taxonomy_version` string (required) — taxonomy release version, e.g., "TEST-2025Q1"

Operational notes
- Loader normalizes keywords to lowercase and deduplicates
- Idempotent upsert via MERGE on `cet_id`


### Award enrichment properties

Enrichment properties are merged onto existing Award nodes; they are not the primary key.

Label
- Award

Match key (pre-existing constraint)
- `award_id` (unique key; assumed to exist)

Properties (CET-related)
- `cet_primary_id` string (optional) — `cet_id` of the top classification
- `cet_primary_score` float (optional) — model score of the primary CET
- `cet_supporting_ids` list<string> (optional) — ordered unique list of supporting `cet_id`s
- `cet_taxonomy_version` string (optional) — taxonomy version used for classification
- `cet_classified_at` string (optional) — ISO-8601 timestamp when classification occurred
- `cet_model_version` string (optional) — classifier/model version used

Operational notes
- Enrichment is idempotent; properties are merged with MERGE on `award_id`
- Null or missing values are filtered out to avoid overwriting existing data with nulls


### Company enrichment properties

Enrichment properties are merged onto Company nodes; they are not the primary key.

Label
- Company

Match key (pre-existing constraint)
- `uei` (unique key; assumed to exist) — configurable; can use `company_id` instead

Properties (CET-related)
- `cet_dominant_id` string (optional) — dominant CET area for the company
- `cet_dominant_score` float (optional) — company-level dominant score (mean of award-level primary scores, or aggregator-defined)
- `cet_specialization_score` float (optional, 0..1) — HHI-like specialization metric
- `cet_areas` list<string> (optional) — distinct CET areas present across company awards
- `cet_taxonomy_version` string (optional) — taxonomy version used for aggregation
- `cet_profile_updated_at` string (required by loader) — ISO-8601 timestamp when profile was last updated (auto-filled if missing)

Operational notes
- Key is configurable via loader/asset (default `uei`, fallback `company_id`)
- Enrichment is idempotent; properties merged with MERGE on the key
- Null/missing values are filtered out to avoid null overwrites


## Relationships

The schema captures explicit relationships from Award and Company to CETArea, separate from the enrichment properties.

### (Award)-[:APPLICABLE_TO]->(CETArea)

Represents that an award is applicable to a CET area.

Type
- `APPLICABLE_TO`

Pattern
- `(a:Award {award_id})-[:APPLICABLE_TO]->(c:CETArea {cet_id})`

Properties
- `score` float (optional) — classification score for the linkage
- `primary` boolean (optional) — true for primary CET; false for supporting
- `role` string (optional) — "PRIMARY" or "SUPPORTING"
- `rationale` string (optional) — short rationale tag (e.g., evidence rationale); best-effort
- `classified_at` string (optional) — ISO-8601 classification time
- `taxonomy_version` string (optional) — taxonomy version

Operational notes
- Created with MERGE to ensure idempotent edge creation
- Properties are updated via `SET r += $properties` (non-destructive; nulls stripped)
- Source Award and target CETArea must exist; if either is missing, the relationship is skipped


### (Company)-[:SPECIALIZES_IN]->(CETArea)

Represents the dominant CET specialization for a company.

Type
- `SPECIALIZES_IN`

Pattern
- `(c:Company {uei or company_id})-[:SPECIALIZES_IN]->(a:CETArea {cet_id})`

Properties
- `score` float (optional) — dominant CET score (e.g., average of award-level scores)
- `specialization_score` float (optional) — HHI-like specialization metric
- `primary` boolean (optional) — always true for dominant link
- `role` string (optional) — "DOMINANT"
- `taxonomy_version` string (optional)

Operational notes
- Created with MERGE to ensure idempotent edge creation
- Only the dominant CET is linked per input profile row
- Source Company and target CETArea must exist; otherwise skipped


## Constraints and Indexes

The loaders attempt to create the following schema (IF NOT EXISTS):

Constraints
- `CREATE CONSTRAINT cetarea_cet_id IF NOT EXISTS FOR (c:CETArea) REQUIRE c.cet_id IS UNIQUE`
- `CREATE CONSTRAINT award_award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE`
- `CREATE CONSTRAINT company_uei IF NOT EXISTS FOR (c:Company) REQUIRE c.uei IS UNIQUE`

Indexes
- `CREATE INDEX cetarea_name_idx IF NOT EXISTS FOR (c:CETArea) ON (c.name)`
- `CREATE INDEX cetarea_taxonomy_version_idx IF NOT EXISTS FOR (c:CETArea) ON (c.taxonomy_version)`

Note: Depending on your environment, Company may also be matched by `company_id`. If so, consider adding an appropriate constraint or index for that property as well.


## Loading assets and end-to-end job

Dagster assets
- `cet_taxonomy` → writes taxonomy artifact
- `cet_award_classifications` → writes award-level classification results
- `cet_company_profiles` → writes company-level aggregation profiles
- `neo4j_cetarea_nodes` → upserts CETArea nodes from taxonomy artifact
- `neo4j_award_cet_enrichment` → merges Award enrichment properties onto Award nodes
- `neo4j_company_cet_enrichment` → merges Company enrichment properties onto Company nodes
- `neo4j_award_cet_relationships` → creates Award→CETArea APPLICABLE_TO edges
- `neo4j_company_cet_relationships` → creates Company→CETArea SPECIALIZES_IN edges

End-to-end job
- `cet_full_pipeline_job` orchestrates the full sequence:
  1) cet_taxonomy
  2) cet_award_classifications
  3) cet_company_profiles
  4) neo4j_cetarea_nodes
  5) neo4j_award_cet_enrichment
  6) neo4j_company_cet_enrichment
  7) neo4j_award_cet_relationships
  8) neo4j_company_cet_relationships


## Input artifacts and contracts

The loader assets expect the following inputs (parquet preferred; NDJSON fallback):

- Taxonomy: `data/processed/cet_taxonomy.parquet` (.json fallback)
  - Columns: `cet_id`, `name`, `definition`, `keywords`, `taxonomy_version`

- Award classifications: `data/processed/cet_award_classifications.parquet` (.json fallback)
  - Columns: `award_id`, `primary_cet`, `primary_score`, `supporting_cets`, `classified_at`, `taxonomy_version`, optionally `evidence` (list with `rationale`)

- Company profiles: `data/processed/cet_company_profiles.parquet` (.json fallback)
  - Columns: `company_id`, `company_name`, `dominant_cet`, `dominant_score`, `specialization_score`, `taxonomy_version`
  - The Company loader can alternatively read enrichment-style fields:
    - `cet_dominant_id`, `cet_dominant_score`, `cet_specialization_score`, `cet_taxonomy_version`
  - The Company key property is configurable; defaults to `uei`, with a safe fallback to `company_id` if `uei` is missing.


## Idempotence, re-runs, and backfills

- Node upserts use MERGE on key properties and `SET n += $properties` to update properties non-destructively.
- Relationship creation uses MERGE for the pattern and `SET r += $properties` to update properties non-destructively.
- Null values are filtered out before SET to avoid overwriting existing properties with nulls.
- `taxonomy_version` is included on CETArea nodes and on enrichment/relationship properties to allow multi-version operation and safe reprocessing during upgrades.
- Award/Company enrichment and relationships can be re-run safely; runs are additive with consistent keys.


## Query examples

List CET areas
```cypher
MATCH (c:CETArea)
RETURN c.cet_id AS cet_id, c.name AS name, c.taxonomy_version AS version
ORDER BY name
```

Find awards classified as AI (primary)
```cypher
MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(c:CETArea {cet_id: "artificial_intelligence"})
RETURN a.award_id, r.score, r.classified_at
ORDER BY r.score DESC
```

Company dominant CET and specialization
```cypher
MATCH (co:Company)-[r:SPECIALIZES_IN]->(c:CETArea)
RETURN co.uei AS uei, c.cet_id AS dominant_cet, r.score AS dominant_score, r.specialization_score
ORDER BY r.specialization_score DESC
```

Award enrichment snapshot
```cypher
MATCH (a:Award {award_id: $award_id})
RETURN a.cet_primary_id, a.cet_primary_score, a.cet_supporting_ids, a.cet_taxonomy_version, a.cet_classified_at
```

Traverse: Company → dominant CET → applicable awards in same CET
```cypher
MATCH (co:Company {uei: $uei})-[:SPECIALIZES_IN]->(c:CETArea)
MATCH (a:Award)-[r:APPLICABLE_TO {primary: true}]->(c)
RETURN c.cet_id, a.award_id, r.score
ORDER BY r.score DESC
```


## Appendix: property dictionary

CETArea
- `cet_id` (string, unique)
- `name` (string)
- `definition` (string, optional)
- `keywords` (list<string>, optional)
- `taxonomy_version` (string)

Award enrichment properties
- `cet_primary_id` (string, optional)
- `cet_primary_score` (float, optional)
- `cet_supporting_ids` (list<string>, optional)
- `cet_taxonomy_version` (string, optional)
- `cet_classified_at` (string, ISO-8601, optional)
- `cet_model_version` (string, optional)

Company enrichment properties
- `cet_dominant_id` (string, optional)
- `cet_dominant_score` (float, optional)
- `cet_specialization_score` (float, optional)
- `cet_areas` (list<string>, optional)
- `cet_taxonomy_version` (string, optional)
- `cet_profile_updated_at` (string, ISO-8601)

Relationships
- (Award)-[:APPLICABLE_TO]->(CETArea)
  - `score` (float, optional)
  - `primary` (boolean, optional)
  - `role` ("PRIMARY"|"SUPPORTING", optional)
  - `rationale` (string, optional)
  - `classified_at` (string, ISO-8601, optional)
  - `taxonomy_version` (string, optional)
- (Company)-[:SPECIALIZES_IN]->(CETArea)
  - `score` (float, optional)
  - `specialization_score` (float, optional)
  - `primary` (boolean, optional; always true)
  - `role` ("DOMINANT", optional)
  - `taxonomy_version` (string, optional)
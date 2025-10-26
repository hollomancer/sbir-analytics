# Implementation Tasks

## 1. Data Analysis & Schema Design

- [x] 1.1 Complete USPTO data structure analysis script
  - Notes: Added `scripts/uspto/analyze_uspto_structure.py` which samples USPTO .dta/.csv/.parquet files, produces per-file JSON summaries and a Markdown run summary, and writes reports to `reports/uspto-structure/`. The script was run locally to generate initial findings (see reports directory).
- [ ] 1.2 Document table schemas and relationships in detail
- [ ] 1.3 Generate data quality baseline report (completeness, duplicates, missing values)
- [ ] 1.4 Design Neo4j graph schema for patents and assignments
- [ ] 1.5 Map USPTO fields to graph node/relationship properties

## 2. Pydantic Models

- [x] 2.1 Create PatentAssignment model (rf_id, file_id, correspondent, dates, conveyance)
  - Notes: Implemented `src/models/uspto_models.py` with `PatentAssignment` and related models; includes `rf_id`, `file_id`, conveyance links, and normalization helpers.
- [x] 2.2 Create PatentAssignee model (rf_id, name, address fields)
  - Notes: `PatentAssignee` model added to `src/models/uspto_models.py` with address fields, identifier normalization, and metadata.
- [x] 2.3 Create PatentAssignor model (rf_id, name, execution/acknowledgment dates)
  - Notes: `PatentAssignor` model added with execution/acknowledgment date parsing and validation.
- [x] 2.4 Create PatentDocument model (rf_id, application/publication/grant numbers)
  - Notes: `PatentDocument` model added with application/publication/grant identifiers and date fields; includes normalization logic.
- [x] 2.5 Create PatentConveyance model (rf_id, type, employer_assign flag)
  - Notes: `PatentConveyance` model implemented with `ConveyanceType` enum and date parsing for recorded_date.
- [x] 2.6 Add validation rules for dates, document numbers, entity names
  - Notes: Validation and normalization helpers (`_parse_date`, `_normalize_identifier`, `_normalize_name`) included and used across the models. See `src/models/uspto_models.py` for details.

## 3. USPTO Extractor (Stage 1: Extract)

- [x] 3.1 Create USPTOExtractor class in src/extractors/uspto_extractor.py
  - Notes: Implemented `src/extractors/uspto_extractor.py` with `USPTOExtractor` providing `stream_rows(...)` and `stream_assignments(...)` generators, chunked reading for .dta/.csv/.parquet, and robust fallbacks.
- [x] 3.2 Implement Stata file reading with chunked iteration (10K rows/chunk)
  - Notes: The extractor uses pandas iterator and pyreadstat fallbacks to support chunked iteration and safe sampling; chunk_size is configurable.
- [x] 3.3 Add memory-efficient streaming for large files (documentid.dta: 1.5GB)
  - Notes: Streaming implemented with parquet/pyarrow row-group handling and chunked pandas/pyreadstat reads for large Stata files to avoid excessive memory use.
- [ ] 3.4 Handle Stata format variations (Release 117 vs 118)
- [ ] 3.5 Add error handling for corrupt or incomplete files
- [ ] 3.6 Log extraction progress with record counts and throughput metrics

## 4. Dagster Assets - Extraction

- [ ] 4.1 Create raw_uspto_assignments asset
- [ ] 4.2 Create raw_uspto_assignees asset
- [ ] 4.3 Create raw_uspto_assignors asset
- [ ] 4.4 Create raw_uspto_documentids asset
- [ ] 4.5 Create raw_uspto_conveyances asset
- [ ] 4.6 Add asset checks for file existence and basic parsing validation

## 5. Data Validation (Stage 2: Validate)

- [ ] 5.1 Create USPTO data quality validator in src/quality/uspto_validators.py
- [ ] 5.2 Validate rf_id uniqueness in assignment table (primary key)
- [ ] 5.3 Validate rf_id referential integrity across tables (foreign keys)
- [ ] 5.4 Check completeness of required fields (rf_id, dates, document numbers)
- [ ] 5.5 Validate date formats and ranges (1790-present)
- [ ] 5.6 Check for duplicate records within each table
- [ ] 5.7 Generate validation report with pass/fail rates

## 6. Dagster Assets - Validation

- [ ] 6.1 Create validated_uspto_assignments asset
- [ ] 6.2 Add asset checks for data quality thresholds (≥95% completeness)
- [ ] 6.3 Add asset checks for referential integrity
- [ ] 6.4 Output failed records to data/validated/fail/ for inspection

## 7. Patent Assignment Transformer (Stage 4: Transform)

- [ ] 7.1 Create PatentAssignmentTransformer in src/transformers/patent_transformer.py
- [ ] 7.2 Implement join logic to combine assignment + conveyance + assignee + assignor + documentid
- [ ] 7.3 Normalize entity names (trim whitespace, uppercase, remove special chars)
- [ ] 7.4 Standardize addresses (parse city, state, country, postcode)
- [ ] 7.5 Parse conveyance text for assignment types (license, sale, merger, security interest)
- [ ] 7.6 Extract structured dates from execution/acknowledgment fields
- [ ] 7.7 Link patents to SBIR companies via fuzzy matching on grant_doc_num
- [ ] 7.8 Calculate assignment chain metadata (hops, time spans)

## 8. Dagster Assets - Transformation

- [ ] 8.1 Create transformed_patent_assignments asset
- [ ] 8.2 Create transformed_patents asset
- [ ] 8.3 Create transformed_patent_entities asset (assignees + assignors)
- [ ] 8.4 Add asset checks for transformation success rate (≥98%)
- [ ] 8.5 Add asset checks for company linkage coverage (target: ≥60% of SBIR companies)

## 9. Neo4j Graph Loader (Stage 5: Load)

- [ ] 9.1 Create PatentLoader in src/loaders/patent_loader.py
- [ ] 9.2 Implement Patent node creation (grant_doc_num, title, dates, language)
- [ ] 9.3 Implement PatentAssignment node creation (rf_id, dates, type, correspondent)
- [ ] 9.4 Implement PatentEntity node creation (assignees and assignors)
- [ ] 9.5 Create ASSIGNED_FROM relationship (Patent ← PatentEntity via PatentAssignment)
- [ ] 9.6 Create ASSIGNED_TO relationship (Patent → PatentEntity via PatentAssignment)
- [ ] 9.7 Create GENERATED_FROM relationship (Patent → Award for SBIR-linked patents)
- [ ] 9.8 Create OWNS relationship (Company → Patent for current ownership)
- [ ] 9.9 Add temporal properties to relationships (effective_date, recorded_date)
- [ ] 9.10 Create indexes on grant_doc_num, rf_id, entity names

## 10. Dagster Assets - Loading

- [ ] 10.1 Create neo4j_patents asset
- [ ] 10.2 Create neo4j_patent_assignments asset
- [ ] 10.3 Create neo4j_patent_entities asset
- [ ] 10.4 Create neo4j_patent_relationships asset
- [ ] 10.5 Add asset checks for load success rate (≥99%)
- [ ] 10.6 Add asset checks for relationship counts (sanity checks)

## 11. Testing

- [ ] 11.1 Unit tests for USPTOExtractor (Stata parsing, chunking, error handling)
- [ ] 11.2 Unit tests for PatentAssignmentTransformer (joins, normalization, parsing)
- [ ] 11.3 Unit tests for PatentLoader (node/relationship creation, property mapping)
- [ ] 11.4 Integration test for extract → validate → transform → load workflow
- [ ] 11.5 End-to-end test with sample USPTO dataset (1000 assignments)
- [ ] 11.6 Test data quality validation edge cases (missing rf_id, invalid dates)
- [ ] 11.7 Test company linkage matching (fuzzy patent number matching)

## 12. Configuration & Documentation

- [ ] 12.1 Add USPTO configuration to config/base.yaml (file paths, chunk size, quality thresholds)
- [ ] 12.2 Document Neo4j graph schema in docs/schemas/patent-assignment-graph.md
- [ ] 12.3 Create data dictionary for USPTO fields
- [ ] 12.4 Add README for data/raw/uspto/ explaining data source and structure
- [ ] 12.5 Update main README with USPTO pipeline documentation

## 13. Deployment & Validation

- [ ] 13.1 Run full pipeline on development environment
- [ ] 13.2 Validate data quality metrics meet thresholds
- [ ] 13.3 Verify Neo4j graph queries for patent ownership chains
- [ ] 13.4 Test incremental update workflow with monthly USPTO releases
- [ ] 13.5 Generate evaluation report with coverage and quality metrics

# Implementation Tasks

## 1. Data Analysis & Schema Design

- [x] 1.1 Complete USPTO data structure analysis script
  - Notes: Added `scripts/uspto/analyze_uspto_structure.py` which samples USPTO .dta/.csv/.parquet files, produces per-file JSON summaries and a Markdown run summary, and writes reports to `reports/uspto-structure/`. The script was run locally to generate initial findings (see reports directory).
- [x] 1.2 Document table schemas and relationships in detail
  - Notes: Created `docs/schemas/patent-assignment-schema.md` with comprehensive documentation of all five USPTO tables (assignment, documentid, assignee, assignor, assignment_conveyance), their schemas, relationships, data quality issues, and SBIR integration strategy.
- [x] 1.3 Generate data quality baseline report (completeness, duplicates, missing values)
  - Notes: Generated `docs/uspto_data_quality_baseline.md` with detailed analysis of 100-row sample per table, including completeness metrics (97.6% aggregate), primary key uniqueness (100%), critical issues (30% NULL grant_doc_num), and recommendations for ETL pipeline.
- [x] 1.4 Design Neo4j graph schema for patents and assignments
  - Notes: Created `docs/schemas/patent-neo4j-schema.md` with complete Neo4j data model: 5 node types (Patent, PatentAssignment, PatentEntity, Award, Company), 6 relationship types (ASSIGNED_VIA, ASSIGNED_TO, ASSIGNED_FROM, FUNDED_BY, OWNS, CHAIN_OF), with indexes, constraints, and example queries for patent chains and SBIR linkage.
- [x] 1.5 Map USPTO fields to graph node/relationship properties
  - Notes: Created `docs/schemas/patent-field-mapping.md` with field-by-field mapping from USPTO Stata tables to Neo4j properties, including transformation logic (name normalization, date parsing, address standardization), validation rules, and implementation checklist.

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
- [x] 3.4 Handle Stata format variations (Release 117 vs 118)
  - Notes: Added `_detect_stata_release` helper and a pyreadstat metadata probe to detect file format/version. The extractor now uses a release heuristic to skip pandas iterator for newer Stata releases and falls back to pyreadstat row-limited reads or a conservative header sniff when needed. Detection is best-effort and non-fatal.
- [x] 3.5 Add error handling for corrupt or incomplete files
  - Notes: Enhanced error handling across readers: `stream_rows` honors `continue_on_error` and yields a record containing `_error` and `_file` when a file-level exception occurs. Individual format readers (CSV, DTA, Parquet) are wrapped with try/except and log structured exceptions; pyreadstat/pandas fallbacks are used to continue processing where possible.
- [x] 3.6 Log extraction progress with record counts and throughput metrics
  - Notes: Implemented periodic progress logging: `stream_rows` reports rows/sec and end-of-stream summary; `_stream_dta` now logs periodic progress for pyreadstat chunked reads (rows processed and percent when total_rows hint available). Frequency is controlled by `self.log_every`.

## 4. Dagster Assets - Extraction

- [x] 4.1 Create raw_uspto_assignments asset
  - Notes: Implemented in `src/assets/uspto_assets.py` with file discovery from configurable input directory.
- [x] 4.2 Create raw_uspto_assignees asset
  - Notes: Implemented in `src/assets/uspto_assets.py` with file discovery from configurable input directory.
- [x] 4.3 Create raw_uspto_assignors asset
  - Notes: Implemented in `src/assets/uspto_assets.py` with file discovery from configurable input directory.
- [x] 4.4 Create raw_uspto_documentids asset
  - Notes: Implemented in `src/assets/uspto_assets.py` with file discovery from configurable input directory.
- [x] 4.5 Create raw_uspto_conveyances asset
  - Notes: Implemented in `src/assets/uspto_assets.py` with file discovery from configurable input directory.
- [x] 4.6 Add asset checks for file existence and basic parsing validation
  - Notes: Implemented 5 parsing assets (`parsed_uspto_<table>`) and 5 corresponding asset checks (`uspto_<table>_parsing_check`) that validate each discovered file can be parsed. Checks use USPTOExtractor to sample 8-12 rows per file and report parsing success/failure with detailed error metadata. All assets and checks exported via `src/assets/__init__.py` and loaded in `src/definitions.py`. Dagster successfully loads 10 USPTO assets and 5 asset checks.

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

- [x] 7.1 Create PatentAssignmentTransformer in src/transformers/patent_transformer.py
  - Notes: Implemented `src/transformers/patent_transformer.py` with `PatentAssignmentTransformer` offering `transform_row` and `transform_chunk` APIs. The transformer builds `PatentAssignment` models (or returns raw rows with `_error` on failure).
- [x] 7.2 Implement join logic to combine assignment + conveyance + assignee + assignor + documentid
  - Notes: The transformer heuristically joins document, conveyance, assignee, and assignor fields present in the incoming row and maps them into the `PatentAssignment` model.
- [x] 7.3 Normalize entity names (trim whitespace, uppercase, remove special chars)
  - Notes: Name normalization routines implemented (`_normalize_name`) used by the transformer and Pydantic models for consistent matching.
- [ ] 7.4 Standardize addresses (parse city, state, country, postcode)
  - Notes: Address parsing/standardization not implemented yet; planned to use a lightweight address parsing utility or libpostal integration in a follow-up.
- [x] 7.5 Parse conveyance text for assignment types (license, sale, merger, security interest)
  - Notes: Conveyance inference heuristics implemented via `_infer_conveyance_type` in the transformer; detects assignments, licenses, security interest, mergers and flags employer-assign hints.
- [x] 7.6 Extract structured dates from execution/acknowledgment fields
  - Notes: Date parsing/validation helpers included and used by the transformer and Pydantic models (accepts ISO and common date formats).
- [x] 7.7 Link patents to SBIR companies via fuzzy matching on grant_doc_num
  - Notes: Basic grant-doc -> SBIR company linking implemented using an optional `sbir_company_grant_index` passed to the transformer; exact and fuzzy matching supported with configurable thresholds.
- [ ] 7.8 Calculate assignment chain metadata (hops, time spans)
  - Notes: Chain-level analytics and hop calculations remain to be implemented in a later pass (requires cross-record aggregation).

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

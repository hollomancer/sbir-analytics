# Add USPTO Patent Assignment ETL Pipeline

## Why

The USPTO patent assignment data (6.3GB across 10 files) contains critical intellectual property ownership transfer records that can be linked to SBIR award recipients. This data enables analysis of:

- **Patent ownership chains**: Track how patent rights transfer from inventors to companies
- **SBIR company innovation**: Link SBIR awards to patents and their subsequent assignments
- **Technology commercialization**: Identify when SBIR-funded inventions are licensed or sold
- **Company acquisition patterns**: Detect M&A activity through patent ownership transfers

Currently, the pipeline lacks patent data integration, limiting our ability to track the full lifecycle of SBIR-funded innovations from award to patent to commercialization.

## What Changes

- **Add USPTO patent assignment extraction** from Stata (.dta) format files
  - Extract 5 core relational tables: assignment, assignee, assignor, documentid, assignment_conveyance
  - Handle 6.3GB dataset with ~8-10M assignment records
  - Parse Stata binary format using pandas
- **Add patent assignment transformation logic**
  - Join related tables via rf_id (reel/frame identifier)
  - Normalize entity names and addresses for matching
  - Extract structured fields from free-text conveyance descriptions
  - Link patents to SBIR companies via grant document numbers
- **Add Neo4j graph model for patent assignments**
  - Create Patent, PatentAssignment, PatentAssignee, PatentAssignor nodes
  - Create ownership transfer relationships with temporal metadata
  - Link Patent nodes to existing Company and Award nodes
- **Add data quality validation for patent data**
  - Validate rf_id uniqueness and referential integrity
  - Check for missing patent numbers and dates
  - Validate address and entity name completeness
- **Add analysis script for initial data exploration**
  - Document table schemas and relationships
  - Generate data quality reports
  - Estimate processing requirements

## Impact

### Affected Specs
- **data-extraction**: Add USPTO Stata file extraction capability
- **data-transformation**: Add patent assignment join and normalization logic
- **data-loading**: Add Patent and PatentAssignment node/relationship loading

### Affected Code
- `src/extractors/`: New USPTO extractor for Stata files
- `src/transformers/`: New patent assignment transformer with entity resolution
- `src/loaders/`: New Neo4j loader for Patent graph model
- `src/models/`: New Pydantic models for patent assignment entities
- `src/assets/`: New Dagster assets for USPTO pipeline stages

### Data Volume & Performance Considerations
- **Input Size**: 6.3GB compressed Stata files (assignment: 744MB, documentid: 1.5GB, assignee: 851MB)
- **Estimated Records**: ~8-10M patent assignments with 20-30M related entities
- **Processing Strategy**: Chunked streaming (10K records/chunk) to manage memory
- **Load Time Estimate**: 2-4 hours for initial full load
- **Incremental Updates**: Monthly USPTO data releases (~100K new assignments/month)

### Dependencies
- pandas >= 2.2.0 (already installed, supports Stata 118 format)
- No new external dependencies required

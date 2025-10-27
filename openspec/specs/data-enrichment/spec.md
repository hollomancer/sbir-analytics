# data-enrichment Specification

## Purpose
TBD - created by archiving change add-initial-architecture. Update Purpose after archive.
## Requirements
### Requirement: Hierarchical Enrichment Fallback
The system SHALL implement a hierarchical enrichment strategy with multiple sources and fallback logic to maximize data coverage.

#### Scenario: Primary source success
- **WHEN** enrichment is attempted with the primary source (e.g., original data)
- **THEN** if the primary source provides valid data, it SHALL be used
- **AND** no fallback sources SHALL be attempted

#### Scenario: Fallback chain execution
- **WHEN** the primary enrichment source fails or returns no data
- **THEN** the system SHALL attempt the next source in the fallback chain
- **AND** this process SHALL continue until a source succeeds or all sources are exhausted

### Requirement: Enrichment Confidence Scoring
The system SHALL assign confidence scores to enriched data based on the source and match quality.

#### Scenario: High confidence enrichment
- **WHEN** data is enriched from a high-quality source (e.g., exact UEI match)
- **THEN** a confidence score ≥ 0.80 SHALL be assigned
- **AND** the confidence score SHALL be stored with the enriched data

#### Scenario: Low confidence enrichment
- **WHEN** data is enriched from a low-quality source (e.g., fuzzy name match)
- **THEN** a confidence score < 0.80 SHALL be assigned
- **AND** the low confidence SHALL be flagged for potential manual review

### Requirement: Enrichment Source Tracking
The system SHALL track which source provided each enriched data field for auditability and quality analysis.

#### Scenario: Source metadata capture
- **WHEN** a field is enriched
- **THEN** the enrichment source SHALL be recorded (e.g., "usaspending_api", "sam_gov_api", "fuzzy_match")
- **AND** the source information SHALL be available for reporting and analysis

### Requirement: Rate Limiting and Retry Logic
The system SHALL implement rate limiting and retry logic for external API calls to respect API limits and handle transient failures.

#### Scenario: Rate limit enforcement
- **WHEN** making API calls
- **THEN** the system SHALL enforce the configured rate limit (e.g., 10 requests/second)
- **AND** requests SHALL be throttled to stay within limits

#### Scenario: Transient failure retry
- **WHEN** an API call fails with a transient error (e.g., 503, timeout)
- **THEN** the system SHALL retry with exponential backoff
- **AND** after max retries, the enrichment SHALL fall back to the next source

### Requirement: Batch Enrichment
The system SHALL support batch enrichment to efficiently process multiple records with a single API call when supported by the source.

#### Scenario: Batch API call
- **WHEN** multiple records need enrichment from the same API
- **THEN** the system SHALL batch them into a single API call (up to configured batch size)
- **AND** the batch size SHALL be configurable per source

### Requirement: Enrichment Success Rate Tracking
The system SHALL track and report enrichment success rates by source for monitoring and optimization.

#### Scenario: Success rate calculation
- **WHEN** enrichment completes
- **THEN** the system SHALL calculate success rate per source (successful enrichments / total attempts)
- **AND** the success rates SHALL be logged and included in pipeline metrics

### Requirement: USAspending Enrichment Coverage Evaluation
The system SHALL quantify and report the achievable SBIR↔USAspending join rate using the mounted Postgres subset before enabling enrichment jobs.

#### Scenario: Measure join coverage vs. 70% target
- **WHEN** the profiled USAspending snapshot is available on the mounted drive
- **THEN** running `poetry run assess_usaspending_match_rate --usaspending-path /Volumes/X10\ Pro/usaspending-db-subset_20251006.zip --sbir-sample data/raw/sbir/sample.csv`
- **AND** the command attempts joins on UEI, DUNS, and PIID/FAIN keys (in priority order)
- **AND** it reports the overall match percentage and per-key breakdown in `reports/usaspending_subset_profile.md`
- **AND** if the overall match rate < 0.70, the command exits non-zero and flags the shortfall so enrichment assets will not proceed.

### Requirement: USAspending Transition Signal Mapping
The system SHALL enumerate and expose the USAspending fields required for SBIR enrichment and technology transition scoring before data is consumed downstream.

#### Scenario: Produce enrichment/transition field inventory
- **WHEN** the profiling workflow completes against the mounted snapshot
- **THEN** it emits a structured mapping (e.g., JSON + Markdown) that lists, for each required field, the USAspending table/column, the SBIR/transition consumer, and the planned transformation (e.g., `detached_award_procurement.piid → Award.award_number`)
- **AND** the mapping must include at least: recipient UEI/DUNS, awarding and funding agency codes, NAICS, PSC, action_date history, obligated_amount, competition type, and place of performance
- **AND** the documentation is versioned with the snapshot date so transition features can reference specific USAspending signal availability.

### Requirement: Enrichment Pipeline Performance Monitoring
The system SHALL collect and report performance metrics for enrichment operations including execution time, memory usage, and resource consumption.

#### Scenario: Asset-level performance metric collection
- **WHEN** enrichment assets execute in Dagster
- **THEN** the system SHALL collect execution time and memory usage metrics
- **AND** metrics SHALL be stored in asset metadata
- **AND** metrics SHALL be visible in Dagster UI run details

#### Scenario: Performance metric reporting
- **WHEN** enrichment operations complete
- **THEN** the system SHALL generate performance reports with timing breakdown by operation phase
- **AND** reports SHALL include peak memory usage and memory delta
- **AND** reports SHALL be exportable in JSON and Markdown formats

#### Scenario: Performance baseline tracking
- **WHEN** enrichment benchmark script executes
- **THEN** the system SHALL record baseline metrics (execution time, memory per dataset size)
- **AND** baselines SHALL be persisted for historical comparison
- **AND** metrics SHALL include dataset size and record count for normalization

### Requirement: Enrichment Quality Validation and Gates
The system SHALL enforce quality thresholds on enrichment operations and prevent poor-quality data from flowing downstream.

#### Scenario: Match rate quality gate enforcement
- **WHEN** enrichment assets complete
- **THEN** the system SHALL validate match rates against configured thresholds (target ≥70%)
- **AND** asset checks SHALL fail if thresholds not met
- **AND** downstream assets SHALL be blocked from executing on quality failure

#### Scenario: Quality metric visibility
- **WHEN** enrichment operations complete
- **THEN** the system SHALL report match rates (overall and by identifier type: UEI, DUNS, fuzzy)
- **AND** confidence score distributions SHALL be calculated
- **AND** quality metrics SHALL be included in Dagster asset metadata

#### Scenario: Quality regression detection
- **WHEN** enrichment operations complete
- **THEN** the system SHALL compare current match rates to historical baseline
- **AND** quality regressions (decrease > 5%) SHALL be flagged
- **AND** regression alerts SHALL include delta and affected identifier types

### Requirement: Full Dataset Enrichment Support
The system SHALL support processing enrichment operations against complete SBIR and USAspending datasets without exhausting available memory.

#### Scenario: Chunked enrichment processing
- **WHEN** processing datasets larger than available memory
- **THEN** the system SHALL divide recipient data into configurable chunks
- **AND** enrichment SHALL be performed per chunk independently
- **AND** results SHALL be combined correctly without data loss or duplication

#### Scenario: Memory-constrained degradation
- **WHEN** memory usage exceeds configured thresholds
- **THEN** the system SHALL reduce chunk sizes dynamically
- **AND** processing SHALL continue without failure
- **AND** performance degradation SHALL be logged for analysis

#### Scenario: Large dataset processing validation
- **WHEN** full dataset enrichment completes
- **THEN** the system SHALL validate that all records were processed
- **AND** match rates SHALL be calculated across the complete dataset
- **AND** processing statistics SHALL be recorded (records/sec, total time, peak memory)

### Requirement: Automated Performance Regression Detection
The system SHALL automatically detect and report on performance regressions in enrichment operations.

#### Scenario: Benchmark regression detection
- **WHEN** enrichment benchmark script executes
- **THEN** the system SHALL compare execution time and memory to historical baseline
- **AND** regressions (time +10% or memory +20%) SHALL be flagged as warnings
- **AND** significant regressions (time +25% or memory +50%) SHALL trigger alerts

#### Scenario: Performance regression analysis
- **WHEN** regressions are detected
- **THEN** the system SHALL report the performance delta and percent change
- **AND** regression reports SHALL be comparable across benchmark runs
- **AND** trend analysis SHALL identify performance trajectory (improving/degrading)

#### Scenario: Quality metrics reporting and dashboarding
- **WHEN** enrichment operations complete
- **THEN** the system SHALL generate reports with match rates and confidence distributions
- **AND** historical quality metrics SHALL be retrievable for trend analysis
- **AND** reports MAY include visualizations (charts, tables) for dashboard use

### Requirement: End-to-End Pipeline Validation
The system SHALL validate complete enrichment pipelines end-to-end from data ingestion through final output validation.

#### Scenario: Pipeline smoke test execution
- **WHEN** the enrichment pipeline is deployed or updated
- **THEN** automated tests SHALL materialize all enrichment assets in order
- **AND** all assets SHALL complete successfully
- **AND** output data SHALL meet quality thresholds and pass validation checks

#### Scenario: Pipeline failure handling
- **WHEN** any enrichment asset fails during pipeline execution
- **THEN** the system SHALL provide detailed error context and logs
- **AND** partial results SHALL NOT corrupt final output
- **AND** pipeline state SHALL be recoverable for retry/resume


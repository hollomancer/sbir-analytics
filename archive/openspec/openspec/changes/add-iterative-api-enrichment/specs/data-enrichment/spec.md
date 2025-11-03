# Data Enrichment - Iterative Refresh Delta

## ADDED Requirements

### Requirement: Iterative API Refresh Cadence

The enrichment layer SHALL execute iterative refresh loops for every external API referenced by the project (SBIR.gov awards API, USAspending v2, SAM.gov entity data, NIH RePORTER, PatentsView, and any additional APIs registered under `config.enrichment.*`) once the bulk load completes, honoring a per-source freshness SLA.

#### Scenario: USAspending daily refresh budget

- **WHEN** the last successful USAspending enrichment for an award is older than 24 hours
- **THEN** the iterative refresh loop SHALL enqueue that award for a USAspending API call within the next scheduler run
- **AND** the refresh SHALL respect the configured rate limit (<=120 requests/minute) while ensuring all queued awards finish inside the 24-hour SLA

#### Scenario: SAM.gov weekly refresh budget

- **WHEN** a company’s SAM.gov enrichment is older than 7 days or has a pending status change event
- **THEN** the iterative loop SHALL re-query SAM.gov within the same weekly window
- **AND** the loop SHALL batch UEIs into chunks no larger than the configured batch size to stay within 60 requests/minute

#### Scenario: NIH and PatentsView cadence coverage

- **WHEN** NIH RePORTER publishes weekly updates or PatentsView publishes monthly patent grants
- **THEN** all SBIR-linked projects/patents SHALL be re-enriched within 7 days (NIH) and 30 days (PatentsView)
- **AND** each loop SHALL mark any sources falling behind the SLA as “stale” so operators can intervene

#### Scenario: Additional API registration

- **WHEN** a new external API is added under `config.enrichment.<source>`
- **THEN** the system SHALL require a cadence + rate-limit definition before iterative refresh assets can run
- **AND** the new source SHALL automatically participate in the refresh scheduler without code changes beyond the connector

### Requirement: Enrichment Freshness Ledger

The system SHALL maintain a per-record, per-source freshness ledger capturing last attempt, last success, and SLA status for every enrichment source.

#### Scenario: Ledger update on success

- **WHEN** an iterative enrichment call succeeds
- **THEN** the ledger SHALL record `last_attempt_at`, `last_success_at`, the source payload hash, and the response status for that record/source pair
- **AND** the ledger entry SHALL be stored in both analytical storage (Parquet/DuckDB) and Neo4j node/relationship properties for downstream queries

#### Scenario: Detect and surface stale cohorts

- **WHEN** the ledger shows `now - last_success_at` exceeding the configured SLA for any source
- **THEN** the system SHALL flag the award/company as `stale` for that source and include it in daily metrics + alerting outputs
- **AND** the stale flag SHALL remain until a successful refresh clears the breach

### Requirement: Source Payload Delta Detection

The enrichment layer SHALL diff successive API payloads so unchanged responses are skipped while deltas generate explicit events for downstream consumers.

#### Scenario: Skip unchanged payloads

- **WHEN** the payload hash returned from USAspending, SAM.gov, NIH, PatentsView, or SBIR.gov matches the previously stored hash
- **THEN** the enrichment workflow SHALL skip rewriting the award/company record
- **AND** it SHALL still update the ledger with the new attempt timestamp while marking the operation as `unchanged`

#### Scenario: Emit enrichment delta event

- **WHEN** the payload hash differs (e.g., SAM.gov status flips to `Inactive`, NIH adds a new project year, PatentsView publishes a new grant date)
- **THEN** the workflow SHALL persist the new values, tag the ledger entry with `delta_detected`, and emit an `enrichment_event` describing the old vs new fields
- **AND** the event SHALL include the source identifier, timestamp, and confidence score so other stages can trigger follow-on processing

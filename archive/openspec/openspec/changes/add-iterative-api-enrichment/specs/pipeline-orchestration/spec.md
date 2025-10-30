# Pipeline Orchestration - Iterative Enrichment Delta

## ADDED Requirements

### Requirement: Iterative Enrichment Job and Sensor
The orchestration layer SHALL provide a Dagster job (and associated sensor/schedule) that runs iterative enrichment cycles only after the bulk enrichment assets succeed.

#### Scenario: Post-bulk activation
- **WHEN** the bulk enrichment assets finish successfully
- **THEN** the iterative enrichment sensor SHALL activate and schedule the `iterative_enrichment_refresh_job`
- **AND** the sensor SHALL pause automatically if any upstream enrichment asset fails until the issue is resolved

#### Scenario: Nightly default cadence with manual override
- **WHEN** no manual override is provided
- **THEN** the job SHALL run on its default nightly schedule
- **AND** operators SHALL be able to trigger an immediate run via CLI/Dagster UI with a specified source/partition window

### Requirement: Partitioned, Rate-Limited Execution
The job SHALL partition work by enrichment source and cohort window, enforcing per-source rate limits and batching rules defined in configuration.

#### Scenario: Source-partitioned runs
- **WHEN** the job materializes
- **THEN** it SHALL create partitions such as `sam_gov:uei_batch_0001`, `usaspending:award_year_2024`, `nih:project_week_2025-W12`, `patentsview:grant_month_2025-01`
- **AND** each partition SHALL inherit the per-source concurrency + rate limit settings so parallel ops never exceed configured quotas

#### Scenario: Dynamic partition backlog clearing
- **WHEN** SLA breaches are detected in the freshness ledger
- **THEN** the scheduler SHALL prioritize partitions containing stale cohorts before scheduling fresh ones
- **AND** it SHALL emit metadata in Dagster runs showing which partitions closed which SLA gaps

### Requirement: Checkpointed Resume and Idempotency
The iterative job SHALL persist checkpoints per partition so retries resume exactly where they left off without duplicating API calls or writes.

#### Scenario: Resume after failure
- **WHEN** a partition fails midway (e.g., network disruption)
- **THEN** rerunning that partition SHALL read the last saved cursor (pagination token, UEI offset, date window) and continue from the next unit of work
- **AND** previously completed slices SHALL be skipped to maintain idempotency

#### Scenario: Checkpoint validation
- **WHEN** a run completes successfully
- **THEN** the job SHALL write a checkpoint artifact (cursor, record counts, duration) to `data/state/enrichment_refresh_state.*`
- **AND** subsequent runs SHALL validate the checkpoint timestamp matches the freshness ledger before starting new work

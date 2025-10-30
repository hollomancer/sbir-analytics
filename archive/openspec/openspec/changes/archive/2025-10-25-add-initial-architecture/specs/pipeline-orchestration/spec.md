# Pipeline Orchestration Specification

## ADDED Requirements

### Requirement: Dagster Asset-Based Orchestration
The system SHALL use Dagster's asset-based design for pipeline orchestration, where each data entity is represented as a Dagster asset with explicit dependency declarations.

#### Scenario: Asset definition with dependencies
- **WHEN** a data entity (e.g., validated SBIR awards) depends on another entity (e.g., raw SBIR awards)
- **THEN** the dependency SHALL be declared explicitly in the asset function signature
- **AND** Dagster SHALL automatically resolve the execution order

#### Scenario: Asset materialization
- **WHEN** a user materializes an asset in the Dagster UI
- **THEN** Dagster SHALL materialize all upstream dependencies first
- **AND** the asset SHALL produce its output data

### Requirement: Pipeline Stage Tracking
The system SHALL track pipeline execution through five distinct stages: Extract, Validate, Enrich, Transform, and Load.

#### Scenario: Stage execution order
- **WHEN** the pipeline executes
- **THEN** assets SHALL be organized by stage (extract → validate → enrich → transform → load)
- **AND** each stage SHALL complete before dependent stages begin

#### Scenario: Stage execution context
- **WHEN** an asset executes
- **THEN** the execution context SHALL include the asset's stage identifier
- **AND** the stage identifier SHALL be logged for observability

### Requirement: Asset Check Quality Gates
The system SHALL implement asset checks at each pipeline stage to enforce data quality gates.

#### Scenario: Quality gate failure blocks downstream processing
- **WHEN** an asset check fails (e.g., completeness check shows <95% coverage)
- **THEN** the asset check SHALL report the failure
- **AND** downstream assets SHALL NOT execute until the issue is resolved

#### Scenario: Quality gate success allows continuation
- **WHEN** all asset checks pass for a stage
- **THEN** Dagster SHALL mark the checks as passed
- **AND** downstream assets SHALL be eligible for execution

### Requirement: Incremental Processing Support
The system SHALL support both full refresh and incremental processing modes.

#### Scenario: Full refresh mode
- **WHEN** the pipeline runs in full refresh mode
- **THEN** all assets SHALL be materialized from scratch
- **AND** existing data SHALL be replaced

#### Scenario: Incremental mode
- **WHEN** the pipeline runs in incremental mode
- **THEN** only new or modified source data SHALL be processed
- **AND** existing processed data SHALL be preserved

### Requirement: Run Tracking and Metadata
The system SHALL track pipeline run metadata including run ID, timestamp, and execution duration.

#### Scenario: Run metadata capture
- **WHEN** a pipeline run starts
- **THEN** a unique run ID SHALL be generated
- **AND** the run ID SHALL be accessible to all assets during execution
- **AND** the run timestamp and duration SHALL be recorded

#### Scenario: Asset execution metadata
- **WHEN** an asset completes execution
- **THEN** metadata about the execution (records processed, duration, throughput) SHALL be attached to the asset
- **AND** the metadata SHALL be visible in the Dagster UI

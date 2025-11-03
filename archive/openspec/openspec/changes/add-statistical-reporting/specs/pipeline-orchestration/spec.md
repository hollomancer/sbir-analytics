# pipeline-orchestration Spec Delta

## ADDED Requirements

### Requirement: Pipeline Artifact Reporting

The system SHALL generate statistical reports as pipeline artifacts for each run, making them accessible for review and historical analysis.

#### Scenario: Generate unified pipeline report

- **WHEN** a complete pipeline run finishes
- **THEN** the system SHALL generate a unified report aggregating:
  - All module-specific reports (SBIR, patents, transition, CET)
  - Overall pipeline statistics (records processed, duration, throughput)
  - Stage-by-stage quality metrics
  - Aggregate data hygiene scores
  - Cumulative changes made across all stages
- **AND** persist the report in `reports/` directory with timestamp

#### Scenario: Report as Dagster asset metadata

- **WHEN** an asset materializes and generates a report
- **THEN** the report location SHALL be attached as asset metadata
- **AND** key metrics (match rate, quality score, records processed) SHALL be attached as observations
- **AND** the Dagster UI SHALL display these metrics inline

#### Scenario: Historical report comparison

- **WHEN** viewing a pipeline run in Dagster
- **THEN** users SHALL be able to compare current run metrics to previous runs
- **AND** identify quality trends (improving, stable, degrading)
- **AND** access historical report artifacts

### Requirement: Module Report Orchestration

The system SHALL coordinate report generation across all pipeline modules and aggregate results into a cohesive summary.

#### Scenario: Module report collection

- **WHEN** the pipeline executes multiple modules (SBIR, patents, transition, CET)
- **THEN** each module SHALL generate its statistical report independently
- **AND** the orchestrator SHALL collect all module reports
- **AND** produce a unified summary report

#### Scenario: Report failure handling

- **WHEN** a module fails to generate its report
- **THEN** the failure SHALL be logged with details
- **AND** other modules SHALL continue report generation
- **AND** the unified report SHALL note missing module reports

### Requirement: Report Insights Aggregation

The system SHALL aggregate insights and recommendations from all modules into prioritized action items.

#### Scenario: Cross-module insights

- **WHEN** multiple modules generate insights
- **THEN** the system SHALL aggregate recommendations by priority
- **AND** identify cross-cutting issues (e.g., data quality affecting multiple modules)
- **AND** provide a prioritized action list in the unified report

#### Scenario: Quality gate enforcement

- **WHEN** insights indicate critical quality issues
- **THEN** the system SHALL optionally fail the pipeline run
- **AND** clearly communicate which quality gates were violated
- **AND** provide remediation steps

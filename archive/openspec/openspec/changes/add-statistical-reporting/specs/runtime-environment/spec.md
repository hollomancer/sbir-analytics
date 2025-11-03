# runtime-environment Spec Delta

## ADDED Requirements

### Requirement: CI Report Artifact Upload

The CI pipeline SHALL generate statistical reports during test runs and upload them as GitHub Actions artifacts for review.

#### Scenario: Generate reports in CI test runs

- **WHEN** CI tests execute (pytest, container tests)
- **THEN** statistical reports SHALL be generated for:
  - Test data validation results
  - Enrichment test coverage
  - Module-specific test statistics
- **AND** reports SHALL be saved to a designated artifacts directory

#### Scenario: Upload reports as GitHub artifacts

- **WHEN** CI completes (success or failure)
- **THEN** all generated reports SHALL be uploaded as artifacts
- **AND** artifacts SHALL be named with run ID and timestamp
- **AND** artifacts SHALL be retained for 30 days

#### Scenario: Report access from GitHub UI

- **WHEN** viewing a CI run in GitHub Actions
- **THEN** users SHALL find reports in the "Artifacts" section
- **AND** be able to download HTML, JSON, and Markdown reports
- **AND** review quality metrics without local environment setup

### Requirement: PR Comment Report Summaries

The CI pipeline SHALL post markdown report summaries as PR comments for quick review.

#### Scenario: Post summary on PR builds

- **WHEN** CI runs for a pull request
- **THEN** a markdown summary SHALL be posted as a PR comment with:
  - Overall pipeline quality score
  - Key metrics (match rate, validation pass rate, records processed)
  - Critical insights and warnings
  - Link to full report artifacts
- **AND** the comment SHALL be updated if the PR is re-run

#### Scenario: Quality gate status in PR

- **WHEN** quality thresholds are violated
- **THEN** the PR comment SHALL clearly indicate FAILED status
- **AND** highlight which metrics failed and by how much
- **AND** provide recommended actions

#### Scenario: Comparison to main branch

- **WHEN** PR build completes
- **THEN** the report SHALL compare metrics to the latest main branch run
- **AND** show improvements or regressions
- **AND** highlight significant changes (>5% delta)

### Requirement: Historical Report Storage

The system SHALL maintain historical reports for trend analysis and quality tracking over time.

#### Scenario: Persist reports locally

- **WHEN** a pipeline run completes in any environment
- **THEN** reports SHALL be saved to `reports/<module>/<timestamp>/`
- **AND** a metadata index file SHALL track all report runs
- **AND** old reports SHALL be retained according to configured policy (default: 90 days local, 30 days CI)

#### Scenario: Report metrics history

- **WHEN** generating new reports
- **THEN** the system SHALL load previous report metrics
- **AND** calculate trends (7-day, 30-day averages)
- **AND** detect anomalies based on historical patterns
- **AND** include trend visualizations in HTML reports

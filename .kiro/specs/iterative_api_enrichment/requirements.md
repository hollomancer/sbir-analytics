# Requirements Document

## Introduction

This specification implements Add Iterative API Enrichment Refresh Loop.

- The current enrichment stage performs a heavy, mostly one-off merge after SBIR bulk ingestion, so company, award, and patent metadata start to drift as soon as external systems publish corrections or new records.
- The external sources we already rely on (SBIR.gov awards API, USAspending v2, SAM.gov entity data, NIH RePORTER, PatentsView, plus the other APIs called out across docs/config) publish updated snapshots daily to monthly; without an iterative refresh we miss compliance actions, debarments, UEI/DUNS changes, new transitions, and patent grants that happen after the initial load.
- Downstream CET classification, transition detection, and commercialization analytics need fresh enrichment signals to remain trustworthy; manually kicking off another full enrichment run takes hours and wastes API quotas instead of incrementally refreshing only what changed.

## Glossary

- **PatentsView**: Technical component or system: PatentsView
- **API**: System component or technology referenced in the implementation
- **SBIR**: System component or technology referenced in the implementation
- **SAM**: System component or technology referenced in the implementation
- **NIH**: System component or technology referenced in the implementation
- **UEI**: System component or technology referenced in the implementation
- **DUNS**: System component or technology referenced in the implementation
- **CET**: System component or technology referenced in the implementation
- **SLA**: System component or technology referenced in the implementation
- **CLI**: System component or technology referenced in the implementation
- **iterative_enrichment_refresh_job**: Code component or file: iterative_enrichment_refresh_job
- **last_attempt_at**: Code component or file: last_attempt_at
- **last_success_at**: Code component or file: last_success_at
- **config.enrichment.***: Code component or file: config.enrichment.*
- **enrichment_events**: Code component or file: enrichment_events
- **poetry run refresh_enrichment --source sam_gov --window 2023-10-01:2023-10-07**: Code component or file: poetry run refresh_enrichment --source sam_gov --window 2023-10-01:2023-10-07
- **docs/enrichment/iterative-refresh.md**: Code component or file: docs/enrichment/iterative-refresh.md
- **Iterative enrichment scheduler**: Key concept: Iterative enrichment scheduler
- **Per-source refresh policies**: Key concept: Per-source refresh policies
- **Connector + delta upgrades**: Key concept: Connector + delta upgrades
- **Freshness telemetry + remediation**: Key concept: Freshness telemetry + remediation
- **Operator tooling & docs**: Key concept: Operator tooling & docs

## Requirements

### Requirement 1

**User Story:** As a developer, I want add iterative api enrichment refresh loop, so that - the current enrichment stage performs a heavy, mostly one-off merge after sbir bulk ingestion, so company, award, and patent metadata start to drift as soon as external systems publish corrections or new records.

#### Acceptance Criteria

1. THE System SHALL implement iterative api enrichment refresh loop
2. THE System SHALL validate the implementation of iterative api enrichment refresh loop

### Requirement 2

**User Story:** As a developer, I want **Iterative enrichment scheduler**, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support **iterative enrichment scheduler**
2. THE System SHALL ensure proper operation of **iterative enrichment scheduler**

### Requirement 3

**User Story:** As a developer, I want Add a Dagster job (`iterative_enrichment_refresh_job`) plus sensor that activates once bulk enrichment assets have succeeded and then runs on a rolling schedule (nightly by default), so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL implement a dagster job (`iterative_enrichment_refresh_job`) plus sensor that activates once bulk enrichment assets have succeeded and then runs on a rolling schedule (nightly by default)
2. THE System SHALL validate the implementation of a dagster job (`iterative_enrichment_refresh_job`) plus sensor that activates once bulk enrichment assets have succeeded and then runs on a rolling schedule (nightly by default)

### Requirement 4

**User Story:** As a developer, I want Partition work by API/source and record cohort (e.g., UEI batches for SAM.gov, award years for USAspending) so each run respects rate limits and can be retried independently, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support partition work by api/source and record cohort (e.g., uei batches for sam.gov, award years for usaspending) so each run respects rate limits and can be retried independently
2. THE System SHALL ensure proper operation of partition work by api/source and record cohort (e.g., uei batches for sam.gov, award years for usaspending) so each run respects rate limits and can be retried independently


# Data Enrichment - USAspending Dump Evaluation Delta

## ADDED Requirements

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

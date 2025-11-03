# data-enrichment Spec Delta

## ADDED Requirements

### Requirement: Enrichment Statistical Reporting

The system SHALL generate detailed statistical reports for enrichment operations, showing coverage, match rates, source breakdown, and before/after comparisons.

#### Scenario: SBIR enrichment statistics

- **WHEN** SBIR enrichment completes
- **THEN** a module-specific report SHALL be generated with:
  - Total awards processed
  - Match rate (percentage successfully enriched)
  - Match method breakdown (exact, fuzzy, API lookup, fallback)
  - Enrichment source breakdown (USAspending, SAM.gov, agency defaults)
  - Unmatched awards analysis (by phase, agency, amount range)
  - Field coverage metrics (NAICS, UEI, location, etc.)
- **AND** the report SHALL be available in JSON, HTML, and Markdown formats

#### Scenario: Patent analysis statistics

- **WHEN** patent analysis completes
- **THEN** a module-specific report SHALL be generated with:
  - Patents processed and validated
  - Loading statistics (nodes created, relationships established)
  - Validation pass/fail rates
  - Data quality scores
  - Coverage metrics for patent fields
- **AND** include visualizations of patent network statistics

#### Scenario: Transition classifier statistics

- **WHEN** transition detection completes
- **THEN** a module-specific report SHALL be generated with:
  - Classification distribution (transition types detected)
  - Confidence score distribution and statistics
  - Detection rate by award phase and agency
  - Quality metrics for transition signals
- **AND** include trend analysis if historical runs exist

#### Scenario: CET classifier statistics

- **WHEN** CET classification completes
- **THEN** a module-specific report SHALL be generated with:
  - Technology category distribution
  - Detection rates by category
  - Coverage metrics (percentage of awards with CET tags)
  - Top keywords/phrases by category
- **AND** include category co-occurrence analysis

### Requirement: Changes Made Tracking

The system SHALL track and report all changes made to the base dataset during enrichment and transformation.

#### Scenario: Before/after comparison

- **WHEN** enrichment modifies records
- **THEN** the system SHALL generate a changes summary showing:
  - Fields added (count and examples)
  - Fields modified (count and examples)
  - Records enriched vs unchanged
  - Enrichment coverage by field
- **AND** provide sample comparisons for manual review

#### Scenario: Field modification tracking

- **WHEN** enrichment updates existing fields
- **THEN** the report SHALL track:
  - Number of fields modified
  - Original vs enriched value distributions
  - Confidence scores for modifications
  - Rollback instructions if needed
- **AND** flag significant changes for manual verification

### Requirement: Enrichment Quality Insights

The system SHALL generate automated insights about enrichment quality and provide actionable recommendations.

#### Scenario: Match rate insights

- **WHEN** match rate falls below expected thresholds
- **THEN** the system SHALL recommend:
  - Reviewing matching logic for common failure patterns
  - Adjusting fuzzy match thresholds
  - Investigating data source quality
- **AND** provide examples of unmatched records for debugging

#### Scenario: Enrichment coverage insights

- **WHEN** critical fields have low enrichment coverage
- **THEN** the system SHALL alert with:
  - Which fields are under-enriched
  - Potential causes (API failures, missing source data)
  - Recommended actions to improve coverage

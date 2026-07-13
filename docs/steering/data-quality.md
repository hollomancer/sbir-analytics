# Data Quality Standards

## Overview

The system implements comprehensive data quality validation at every pipeline stage with configurable thresholds and severity-based actions. This document focuses on the quality framework, validation methods, and quality dimensions.

## Core Concepts

### Quality Dimensions

| Dimension | Definition | Validation Method | Target |
|-----------|------------|-------------------|--------|
| **Completeness** | Required fields populated | Not null checks, coverage % | ≥95% |
| **Uniqueness** | No duplicate records | Primary key constraints | 100% |
| **Validity** | Values within expected ranges | Type checks, regex, enums | ≥98% |
| **Consistency** | Data agrees across sources | Cross-reference validation | ≥90% |
| **Accuracy** | Data matches source of truth | Sample manual verification | ≥95% |
| **Timeliness** | Data is current and fresh | Timestamp checks | Daily updates |

### Severity-Based Actions

- **ERROR**: Block pipeline execution, prevent downstream processing
- **WARNING**: Log issue but continue processing
- **INFO**: Log for informational purposes only

## Implementation Patterns

### Schema Validation

- Required columns present
- Correct data types
- Primary key uniqueness
- Value range validation

### Data Quality Checks

- Completeness percentage calculation
- Duplicate detection and reporting
- Value range validation
- Cross-reference consistency

### Quality Reporting

- Detailed quality reports with issue type, severity, affected record counts
- Sample IDs for manual investigation
- Coverage metrics for key fields
- Historical quality trend tracking

## Configuration

Quality thresholds and validation rules are configured in YAML. See **[configuration.md](../configuration.md)** for complete configuration examples including:

- Completeness requirements by field
- Uniqueness constraints
- Validity ranges and limits
- Quality gate thresholds
- Severity-based action configuration

## Best Practices

### Quality Framework Design

- **Configurable thresholds**: All quality rules externalized to configuration
- **Severity-based actions**: Different responses based on issue severity
- **Comprehensive reporting**: Detailed quality reports with actionable information
- **Historical tracking**: Quality trends over time for regression detection

### Quality Validation Strategy

- **Early validation**: Catch issues as early as possible in the pipeline
- **Incremental validation**: Validate data at each pipeline stage
- **Contextual validation**: Different validation rules for different data types
- **Graceful degradation**: Continue processing when possible, log failures

## Standalone Analysis Script & Report Accuracy

The quality framework above governs the Dagster pipeline (`sbir_etl`). The one-off `scripts/data/*.py` analysis scripts that produce findings reports (e.g. `docs/nanotech_sbir_transition_findings.md`) sit outside it and need their own discipline — a full figure-by-figure audit of the nanotech report (105 checks, `scripts/data/nano_verify_report_figures.py`) surfaced three real errors, all from the same handful of failure modes:

- **A fixed generator doesn't fix its already-written output.** Patching a bug in a script that writes a CSV does nothing to CSVs it already wrote — every downstream consumer (including report prose typed by hand) keeps reading the stale file until someone reruns the generator. This produced two of the three errors found (Form D dollar stats in Finding 1, and a survival-analysis split in Policy #2 that consumed the same stale CSV through a second script). Tell: an output file's mtime predates the last fix to the script that writes it. Fix: after patching a data-generating script, regenerate every artifact it produces, not just the one you were debugging.
- **An `*_id` column is not necessarily a unique key.** SBIR `award_id` repeats across different-year continuation awards from the same agency (confirmed for DOE), the same trap as [[fpds-piid-not-a-key]] for FPDS PIIDs. Bare-ID set operations (`{r["award_id"] for r in rows}`) silently under- or over-count. Use a compound key (`award_id` + `company` + `award_year`, or whatever the source actually guarantees is unique) and dedupe explicitly before treating row count as entity count.
- **Match the population, not just the column names.** A script computed a firm's "first Phase II award year" by joining against a *different, more narrowly-scoped* cohort file than the one the statistic was actually about, because both files happened to have compatible `company`/`award_year` columns. The join ran without error and produced a plausible-looking but wrong number. When a stat is defined over population X, source every input for it from X's own data — a column with the same name in a sibling file may carry a different, incompatible population underneath.
- **Hand-typed, non-reproducible figures are the highest-risk category.** The one error with no backing script at all (Finding 2's acquisition-timing paragraph — a median and an outlier example, asserted directly in prose) was also the most wrong: not a rounding slip but the wrong firm identified as the outlier. A number nobody can rerun is a number nobody re-verifies. Prefer computing every reportable figure in a script, even a throwaway one; if a figure must be asserted by hand (e.g. reasoning about a small hand-curated table), say so explicitly in the text so it gets extra scrutiny during review.
- **Build the audit script alongside the report, not after.** `nano_verify_report_figures.py` recomputes every load-bearing number in the report from source and diffs it against the value actually printed in the markdown. Keep this pattern for any new findings report (the quantum/hypersonics generalization is a natural next user) — rerun it whenever an upstream script or source CSV changes, not just once at publication.

## Related Documents

- **[configuration.md](../configuration.md)** - Complete quality configuration examples
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Asset check implementation patterns
- **[quick-reference.md](quick-reference.md)** - Quality thresholds quick lookup

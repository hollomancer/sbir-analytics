# Data Quality Standards

## Quality Framework

The system implements comprehensive data quality validation at every pipeline stage with configurable thresholds and severity-based actions.

## Quality Dimensions

| Dimension | Definition | Validation Method | Target |
|-----------|------------|-------------------|--------|
| **Completeness** | Required fields populated | Not null checks, coverage % | ≥95% |
| **Uniqueness** | No duplicate records | Primary key constraints | 100% |
| **Validity** | Values within expected ranges | Type checks, regex, enums | ≥98% |
| **Consistency** | Data agrees across sources | Cross-reference validation | ≥90% |
| **Accuracy** | Data matches source of truth | Sample manual verification | ≥95% |
| **Timeliness** | Data is current and fresh | Timestamp checks | Daily updates |

## Quality Thresholds (Configurable)

### Completeness Requirements
```yaml
data_quality:
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
    award_amount: 0.98      # 98% required
    naics_code: 0.85        # 85% required (enrichment target)
```

### Uniqueness Requirements
```yaml
  uniqueness:
    award_id: 1.00          # No duplicates allowed
```

### Validity Ranges
```yaml
  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0  # $5M max for Phase II
    award_date_min: "1983-01-01"
    award_date_max: "2025-12-31"
```

### Quality Gates
```yaml
  thresholds:
    max_duplicate_rate: 0.10      # Block if >10% duplicates
    max_missing_rate: 0.15        # Warn if >15% missing
    min_enrichment_success: 0.90  # Target 90% enrichment
```

## Severity-Based Actions

- **ERROR**: Block pipeline execution, prevent downstream processing
- **WARNING**: Log issue but continue processing
- **INFO**: Log for informational purposes only

## Quality Validation Implementation

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

## Asset Check Integration

Quality validation is integrated into Dagster asset checks:
- Asset checks enforce quality thresholds
- Failed checks block downstream assets
- Quality metrics stored in asset metadata
- Quality trends visible in Dagster UI

## Configuration-Driven Quality

All quality thresholds are externalized to YAML configuration:
- Business users can adjust thresholds without code changes
- Environment-specific quality standards (dev vs prod)
- A/B testing of different quality rules
- Runtime configuration via environment variables
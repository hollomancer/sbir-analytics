# SBIR Data Ingestion

This document provides detailed technical documentation for the SBIR (Small Business Innovation Research) and STTR (Small Business Technology Transfer) data ingestion pipeline.

## Overview

The SBIR ingestion pipeline processes award data from the official SBIR.gov database, validates it against business rules, and prepares it for loading into the Neo4j graph database. The pipeline handles approximately 533,000 historical awards from 1983 to present.

## Data Source

### SBIR.gov Awards Database

- **URL**: https://www.sbir.gov/awards
- **Format**: CSV export
- **Columns**: 42 fields
- **Records**: ~533,000 awards
- **Update Frequency**: Monthly
- **Historical Coverage**: 1983-present
- **Agencies**: All federal agencies participating in SBIR/STTR

### Data Acquisition

```bash
# Download process (manual)
# 1. Visit https://www.sbir.gov/awards
# 2. Export complete awards database as CSV
# 3. Save as: data/raw/sbir/awards_data.csv
```

## CSV Field Descriptions

### Company Information (7 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Company | string | Yes | Legal company name | "Acme Innovations LLC" |
| Address1 | string | No | Primary street address | "123 Main Street" |
| Address2 | string | No | Suite/unit number | "Suite 200" |
| City | string | No | City name | "Anytown" |
| State | string | No | 2-letter state code | "CA" |
| Zip | string | No | ZIP code (5 or 9 digits) | "94105" or "94105-1234" |
| Company Website | string | No | Company website URL | "https://acme.example.com" |
| Number of Employees | integer | No | Total employee count | 50 |

### Award Details (7 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Award Title | string | Yes | Project title | "Next-Gen Rocket Fuel Development" |
| Abstract | string | No | Project description | "Research on high-efficiency rocket propellants..." |
| Agency | string | Yes | Federal agency | "NASA", "NSF", "DOD", "DOE", "HHS" |
| Branch | string | No | Agency subdivision | "Aerospace Research", "NIH", "Army" |
| Phase | string | Yes | SBIR/STTR phase | "Phase I", "Phase II", "Phase III" |
| Program | string | Yes | Program type | "SBIR", "STTR" |
| Topic Code | string | No | Solicitation topic | "RX-101", "BT-22" |

### Financial Information (2 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Award Amount | float | Yes | Award amount in USD | 150000.00 |
| Award Year | integer | Yes | Fiscal year of award | 2023 |

### Timeline Information (5 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Proposal Award Date | date | No | Date proposal awarded | "2023-06-15" |
| Contract End Date | date | No | Contract completion date | "2024-06-14" |
| Solicitation Close Date | date | No | Solicitation deadline | "2023-03-01" |
| Proposal Receipt Date | date | No | Date proposal received | "2023-02-15" |
| Date of Notification | date | No | Company notification date | "2023-06-01" |

### Tracking Information (4 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Agency Tracking Number | string | Yes | Agency's internal ID | "ATN-0001" |
| Contract | string | Yes | Contract/grant number | "C-2023-0001" |
| Solicitation Number | string | No | Solicitation identifier | "SOL-2023-01" |
| Solicitation Year | integer | No | Solicitation fiscal year | 2023 |

### Company Identifiers (2 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| UEI | string | No | Unique Entity Identifier (12 chars) | "A1B2C3D4E5F6" | <!-- pragma: allowlist secret -->
| Duns | string | No | DUNS number (9 digits) | "123456789" |

### Business Classifications (3 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| HUBZone Owned | boolean | No | HUBZone business | "Y" or "N" |
| Socially and Economically Disadvantaged | boolean | No | Disadvantaged business | "Y" or "N" |
| Woman Owned | boolean | No | Woman-owned business | "Y" or "N" |

### Contact Information (4 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| Contact Name | string | No | Primary contact name | "Jane Doe" |
| Contact Title | string | No | Contact job title | "CEO" |
| Contact Phone | string | No | Contact phone number | "555-123-4567" |
| Contact Email | string | No | Contact email address | "jane.doe@acme.example.com" |

### Principal Investigator (4 fields)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| PI Name | string | No | Principal Investigator name | "Dr. Alan Smith" |
| PI Title | string | No | PI job title | "Lead Scientist" |
| PI Phone | string | No | PI phone number | "555-987-6543" |
| PI Email | string | No | PI email address | "alan.smith@acme.example.com" |

### Research Institution (3 fields - STTR only)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| RI Name | string | No | Research Institution name | "Bio Research Institute" |
| RI POC Name | string | No | RI Point of Contact | "Alice Researcher" |
| RI POC Phone | string | No | RI POC phone | "410-555-0210" |

## Validation Rules

The pipeline applies comprehensive validation rules to ensure data quality:

### Required Field Validation
- Company name, Award Title, Agency, Phase, Program, Award Amount, Award Year
- Agency Tracking Number, Contract number

### Format Validation
- **UEI**: 12 alphanumeric characters (if present)
- **DUNS**: 9 digits (if present)
- **Email**: Valid email format
- **Phone**: US phone format (XXX-XXX-XXXX)
- **State**: 2-letter US state code
- **ZIP**: 5 or 9 digits
- **Dates**: YYYY-MM-DD format

### Business Logic Validation
- **Award Amount**: Positive, ≤ $10,000,000
- **Award Year**: 1983-2026
- **Phase**: Must be "Phase I", "Phase II", or "Phase III"
- **Program**: Must be "SBIR" or "STTR"
- **Date Consistency**: Proposal Award Date ≤ Contract End Date
- **Award Year Match**: Award Year should match Proposal Award Date year (warning)
- **Phase-Program Consistency**: All phases valid for both SBIR and STTR

### Quality Thresholds
- **Completeness**: ≥90% of required fields present
- **Validity**: ≥95% of records pass validation
- **Uniqueness**: ≥99% unique Contract IDs

## Pipeline Implementation

### Dagster Assets

The SBIR ingestion consists of three main Dagster assets:

#### 1. raw_sbir_awards
```python
@asset
def raw_sbir_awards(duckdb_client: DuckDBClient) -> pd.DataFrame:
    """Load raw SBIR awards from CSV into DuckDB."""
    extractor = SbirDuckDBExtractor(duckdb_client, config.sbir)
    return extractor.extract_all()
```

#### 2. validated_sbir_awards
```python
@asset
def validated_sbir_awards(raw_sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Validate and filter SBIR awards data."""
    report = validate_sbir_awards(raw_sbir_awards)
    # Filter to passing records only
    return raw_sbir_awards[report.passed_records]
```

#### 3. sbir_validation_report
```python
@asset
def sbir_validation_report(raw_sbir_awards: pd.DataFrame) -> QualityReport:
    """Generate comprehensive validation report."""
    return validate_sbir_awards(raw_sbir_awards)
```

### Configuration

```yaml
# config/base.yaml
sbir:
  csv_path: "data/raw/sbir/awards_data.csv"
  duckdb:
    database_path: ":memory:"
    table_name: "sbir_awards"
    batch_size: 10000

validation:
  sbir_awards:
    pass_rate_threshold: 0.95
    completeness_threshold: 0.90
    uniqueness_threshold: 0.99
```

## Example Queries

### Basic Award Analysis
```sql
-- Total awards by agency
SELECT Agency, COUNT(*) as award_count
FROM sbir_awards
GROUP BY Agency
ORDER BY award_count DESC;

-- Average award amounts by phase
SELECT Phase, AVG("Award Amount") as avg_amount
FROM sbir_awards
GROUP BY Phase;
```

### Company Analysis
```sql
-- Top companies by total funding
SELECT Company, SUM("Award Amount") as total_funding, COUNT(*) as award_count
FROM sbir_awards
GROUP BY Company
ORDER BY total_funding DESC
LIMIT 10;

-- Companies with multiple phases
SELECT Company, COUNT(DISTINCT Phase) as phase_count
FROM sbir_awards
GROUP BY Company
HAVING phase_count > 1
ORDER BY phase_count DESC;
```

### Temporal Analysis
```sql
-- Awards by year and agency
SELECT "Award Year", Agency, COUNT(*) as awards, SUM("Award Amount") as total
FROM sbir_awards
GROUP BY "Award Year", Agency
ORDER BY "Award Year" DESC, total DESC;

-- Phase progression analysis
SELECT Company, "Award Year", Phase, "Award Amount"
FROM sbir_awards
ORDER BY Company, "Award Year";
```

### Quality Analysis
```sql
-- Missing UEI analysis
SELECT "Award Year", COUNT(*) as total_awards,
       SUM(CASE WHEN UEI IS NULL OR UEI = '' THEN 1 ELSE 0 END) as missing_uei
FROM sbir_awards
GROUP BY "Award Year"
ORDER BY "Award Year";

-- Award amount distribution
SELECT
    COUNT(*) as total,
    AVG("Award Amount") as mean_amount,
    MEDIAN("Award Amount") as median_amount,
    MIN("Award Amount") as min_amount,
    MAX("Award Amount") as max_amount
FROM sbir_awards;
```

## Performance Considerations

### Memory Usage
- Full dataset: ~533K records × 42 columns
- DuckDB in-memory: ~500MB RAM
- Chunked processing: 10K batch size recommended

### Processing Time
- CSV import: ~30 seconds
- Validation: ~2 minutes
- Quality checks: ~10 seconds

### Optimization Strategies
- Use DuckDB for efficient columnar queries
- Process in chunks for large datasets
- Index on frequently queried columns (Award Year, Agency, Phase)

## Troubleshooting

### Common Issues

**CSV Import Errors**
- Check file encoding (should be UTF-8)
- Verify column headers match expected format
- Ensure date fields are properly formatted

**Validation Failures**
- Review quality report for specific issues
- Check for missing required fields
- Validate date formats and ranges

**Memory Issues**
- Use persistent DuckDB file instead of :memory:
- Reduce batch sizes in configuration
- Process data in smaller chunks

### Data Quality Monitoring

```python
# Check validation results
report = validate_sbir_awards(df)
print(f"Pass rate: {report.pass_rate:.1%}")
print(f"Total issues: {len(report.issues)}")

# Review specific issues
for issue in report.issues[:10]:
    print(f"{issue.field}: {issue.message}")
```

## Testing

### Unit Tests
```bash
# Run SBIR validator tests
poetry run pytest tests/unit/test_sbir_validators.py -v

# Run with sample data
poetry run pytest tests/integration/test_sbir_ingestion_assets.py
```

### Sample Data
- Location: `tests/fixtures/sbir_sample.csv`
- Records: 100 representative awards
- Includes edge cases and invalid records
- Use for development and testing

## API Reference

### SbirDuckDBExtractor

```python
class SbirDuckDBExtractor:
    def extract_all(self) -> pd.DataFrame:
        """Extract complete dataset."""

    def extract_by_year(self, start_year: int, end_year: int = None) -> pd.DataFrame:
        """Filter by award year."""

    def extract_by_agency(self, agencies: List[str]) -> pd.DataFrame:
        """Filter by agency."""

    def extract_by_phase(self, phases: List[str]) -> pd.DataFrame:
        """Filter by phase."""

    def extract_in_chunks(self, batch_size: int = 10000):
        """Yield DataFrames in chunks."""
```

### Validation Functions

```python
def validate_sbir_awards(df: pd.DataFrame, pass_rate_threshold: float = 0.95) -> QualityReport:
    """Validate DataFrame of SBIR awards."""

def validate_sbir_award_record(row: pd.Series, row_index: int) -> List[QualityIssue]:
    """Validate single award record."""
```

## Future Enhancements

- Real-time data ingestion from SBIR.gov API
- Incremental updates instead of full reloads
- Enhanced duplicate detection algorithms
- Machine learning-based data quality scoring
- Automated data dictionary updates
```
## Contributing

When modifying the SBIR ingestion pipeline:

1. Update validation rules in `src/validators/sbir_awards.py`
2. Add corresponding tests in `tests/unit/test_sbir_validators.py`
3. Update configuration schemas if needed
4. Regenerate sample data if field definitions change
5. Update this documentation

## References

- [SBIR.gov](https://www.sbir.gov/) - Official SBIR/STTR program website
- [SBIR Data Dictionary](docs/data-dictionaries/sbir_awards_data_dictionary.xlsx)
- [Federal Agency Codes](https://www.sbir.gov/agency-codes)
- [UEI System](https://www.sam.gov/uei) - Unique Entity Identifier
```
## Check CONTRIBUTING.md to see if it needs updates.

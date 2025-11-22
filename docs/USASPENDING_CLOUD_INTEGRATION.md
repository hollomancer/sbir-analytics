# USAspending Cloud Dataset Integration

This document describes the integration of USAspending.gov monthly database dumps with the SBIR Analytics cloud infrastructure for enriching SBIR award and company data.

## Overview

USAspending.gov provides monthly PostgreSQL database dumps containing federal spending data from FY2001 to present. The full database is over **1.5 TB** and includes transaction-level details for all federal awards.

This integration enables:
- **Monthly automated downloads** of USAspending database dumps to S3
- **Selective data extraction** using DuckDB to query only SBIR-relevant transactions
- **Neo4j enrichment** with transaction-level federal spending data
- **Cost-optimized storage** with intelligent tiering and archival policies

## Architecture

**Data Source Priority:**
1. **PRIMARY**: S3 database dump (from EC2 automation)
2. **FALLBACK**: USAspending API (limited - only for individual award lookups)
3. **FAIL**: If S3 unavailable and API cannot provide required data

```
┌─────────────────────────────────────────────────────────────────┐
│                        Monthly Workflow                          │
└─────────────────────────────────────────────────────────────────┘

1. EC2 Automation: download-usaspending-database (GitHub Actions)
   └─> Downloads monthly dump from files.usaspending.gov
   └─> Uploads to S3 with multipart upload
   └─> Computes SHA256 hash for change detection
   └─> Stores in: s3://bucket/raw/usaspending/database/YYYY-MM-DD/

2. S3: sbir-etl-production-data/raw/usaspending/database/
   └─> Stores dump with lifecycle policies:
       - Day 0-7: S3 Standard (immediate access)
       - Day 7-90: Intelligent Tiering (auto-optimization)
       - Day 90-365: Glacier Flexible Retrieval (80% cost savings)
       - After 365 days: Deleted

3. Dagster: sbir_relevant_usaspending_transactions asset
   └─> Downloads dump from S3 (or uses cached local copy)
   └─> Uses DuckDB postgres_scanner to query specific tables
   └─> Filters for SBIR-relevant agencies and NAICS codes
   └─> Extracts ~1M transactions (vs 100M+ in full database)

4. Dagster: sbir_company_usaspending_recipients asset
   └─> Matches recipients to SBIR companies using UEI/DUNS
   └─> Enriches with business type, parent company, etc.

5. Neo4j: Enhanced SBIR graph
   └─> Company → USAspending transactions relationships
   └─> Transaction → Agency relationships
   └─> Enables federal spending analytics for SBIR companies
```

## Components

### 1. EC2 Automation: `download-usaspending-database`

**Location:** `.github/workflows/usaspending-database-download.yml`

**Purpose:** Downloads USAspending PostgreSQL dumps and uploads to S3 using EC2

**Configuration:**
- Scheduled: Monthly on the 6th at 2 AM UTC
- Manual trigger: Available via GitHub Actions UI
- Database types: `full` or `test`
- Automatic file detection: Checks for new files before downloading

**Database Types:**
- `test`: Smaller subset database (~50-100 GB) for development/testing
- `full`: Complete database dump (~217 GB compressed, ~1.5+ TB uncompressed)

**Invocation:**
```bash
# Via GitHub Actions UI:
# Actions → USAspending Database Download → Run workflow
# Select database_type: "full" or "test"

# Or via GitHub CLI:
gh workflow run usaspending-database-download.yml \
  -f database_type=full \
  -f date=20251106
```

**Notes:**
- ✅ No authentication required - direct downloads work
- EC2 handles large files (no 15-minute timeout)
- Uses multipart upload to stream data directly from source to S3
- Computes SHA256 hash for integrity verification
- Automatically finds latest file in S3 for ingestion
- See: `docs/deployment/usaspending-ec2-automation.md` for setup

**Migration Note:** Lambda function removed - use EC2 automation instead

### 2. Data Source Priority

**PRIMARY: S3 Database Dump**
- All assets prioritize S3 database dumps
- Automatically finds latest dump file
- Format: `s3://bucket/raw/usaspending/database/YYYY-MM-DD/usaspending-db_YYYYMMDD.zip`

**FALLBACK: USAspending API**
- Only used if S3 dump unavailable
- Limited functionality (individual award lookups only)
- Not suitable for bulk transaction queries

**FAIL: If Both Unavailable**
- Assets will fail with clear error messages
- S3 dump is required for production workloads

### 3. DuckDB Extractor: Enhanced for S3

**Location:** `src/extractors/usaspending.py`

**Enhancements:**
- Supports S3 URLs (e.g., `s3://bucket/path/to/dump.zip`)
- Automatic download and caching using `cloudpathlib`
- **S3-first strategy**: Always tries S3 before local paths
- Automatically finds latest dump file in S3

**Usage:**
```python
from sbir_analytics.extractors.usaspending import DuckDBUSAspendingExtractor

# Works with S3 paths
extractor = DuckDBUSAspendingExtractor()
extractor.import_postgres_dump(
    "s3://sbir-etl-production-data/raw/usaspending/database/2025-11-06/dump.zip",
    table_name="transaction_normalized"
)

# Query specific data
df = extractor.query_awards(
    table_name="transaction_normalized",
    filters={"fiscal_year": 2024},
    limit=10000
)
```

### 3. Dagster Assets: SBIR-Relevant Data Extraction

**Location:** `src/assets/usaspending_database_enrichment.py`

#### Asset: `sbir_relevant_usaspending_transactions`

Extracts SBIR-relevant transactions from the database dump.

**Filtering Criteria:**
- **Agencies:** DOD, NASA, NSF, NIH, DOE, USDA, DHS, DOT, EPA, etc.
- **NAICS Codes:**
  - 5417XX - Scientific R&D services
  - 3254XX - Pharmaceutical manufacturing
  - 3341XX - Computer manufacturing
  - 3364XX - Aerospace product manufacturing
  - 5112XX - Software publishers
- **Award Size:** ≤ $2.5M (typical SBIR range)
- **Positive Obligations:** Excludes negative adjustments

**Output:** DataFrame with ~1M SBIR-relevant transactions

#### Asset: `sbir_company_usaspending_recipients`

Matches USAspending recipients to SBIR companies.

**Matching Strategy:**
1. Extract UEI and DUNS from `enriched_sbir_awards`
2. Query `recipient_lookup` table for matching records
3. Return recipient details (business types, parent companies, etc.)

**Output:** DataFrame with recipient enrichment data

### 4. S3 Storage Configuration

**Bucket:** `sbir-etl-production-data`

**Path Structure:**
```
s3://sbir-etl-production-data/
  └─ raw/usaspending/database/
      ├─ 2025-11-01/
      │   └─ usaspending-db-subset_20251101.zip
      ├─ 2025-12-01/
      │   └─ usaspending-db-subset_20251201.zip
      └─ latest/  (symlink or latest copy)
          └─ usaspending-db-subset.zip
```

**Lifecycle Policy:**
```yaml
- Day 0-7: S3 Standard ($0.023/GB/month)
- Day 7-90: Intelligent Tiering ($0.023-$0.0125/GB/month)
- Day 90-365: Glacier Flexible Retrieval ($0.0036/GB/month)
- After 365 days: Deleted
```

**Cost Estimate (500 GB compressed dump):**
- Month 1: ~$11.50 (S3 Standard)
- Month 2-3: ~$6-11 (Intelligent Tiering)
- Month 4-12: ~$1.80 (Glacier)
- **Total annual cost per dump:** ~$25-30

### 5. Configuration

**Location:** `config/base.yaml`

```yaml
paths:
  # Local fallback path
  usaspending_dump_file: "data/usaspending/usaspending-db_20251006.zip"

  # S3 path (takes precedence if S3 is configured)
  usaspending_dump_s3_path: "s3://sbir-etl-production-data/raw/usaspending/database/latest/usaspending-db-subset.zip"

s3:
  bucket: "sbir-etl-production-data"
  region: "us-east-1"
```

## Deployment

### 1. Deploy CDK Infrastructure

```bash
cd infrastructure/cdk

# Deploy storage stack (if not already deployed)
cdk deploy SbirEtlStorageStack

# Deploy Lambda stack with new function
cdk deploy SbirEtlLambdaStack
```

### 2. Trigger Monthly Download

**Option A: Manual Invocation**
```bash
aws lambda invoke \
  --function-name sbir-analytics-download-usaspending-database \
  --payload '{"database_type": "test"}' \
  response.json
```

**Option B: EventBridge Scheduled Rule (Recommended)**

Add to `infrastructure/cdk/stacks/step_functions_stack.py`:

```python
# Monthly USAspending database download (1st of each month at 2 AM UTC)
usaspending_monthly_rule = events.Rule(
    self,
    "USAspendingMonthlyDownload",
    schedule=events.Schedule.cron(
        minute="0",
        hour="2",
        day="1",  # 1st of month
        month="*",
        year="*"
    ),
)

usaspending_monthly_rule.add_target(
    targets.LambdaFunction(
        lambda_functions["download-usaspending-database"],
        event=events.RuleTargetInput.from_object({
            "database_type": "test",
            "s3_bucket": s3_bucket.bucket_name,
        }),
    )
)
```

### 3. Configure Dagster Assets

The new assets are automatically available in Dagster Cloud:
- `sbir_relevant_usaspending_transactions`
- `sbir_company_usaspending_recipients`

**Materialization:**
```bash
# Via Dagster UI
# Navigate to Assets > usaspending_database group > Materialize

# Via CLI
dagster asset materialize sbir_relevant_usaspending_transactions
```

## Usage Examples

### Extract SBIR Transactions for Specific Agency

```python
from sbir_analytics.extractors.usaspending import DuckDBUSAspendingExtractor

extractor = DuckDBUSAspendingExtractor()
extractor.import_postgres_dump(
    "s3://sbir-etl-production-data/raw/usaspending/database/latest/usaspending-db-subset.zip",
    "transaction_normalized"
)

# Query NASA SBIR awards
df = extractor.connect().execute("""
    SELECT
        recipient_name,
        award_description,
        federal_action_obligation,
        action_date
    FROM transaction_normalized
    WHERE awarding_agency_name = 'National Aeronautics and Space Administration'
      AND naics_code LIKE '5417%'
      AND federal_action_obligation <= 2500000
      AND federal_action_obligation > 0
    LIMIT 1000
""").fetchdf()

print(df.head())
```

### Enrich SBIR Company with Federal Spending History

```python
# Load SBIR awards
sbir_awards = pd.read_csv("data/raw/sbir_awards.csv")

# Get company UEI
company_uei = sbir_awards[sbir_awards["Company"] == "Acme Innovations"]["UEI"].iloc[0]

# Query all federal transactions for this company
extractor = DuckDBUSAspendingExtractor()
extractor.import_postgres_dump("s3://...", "transaction_normalized")

company_transactions = extractor.connect().execute(f"""
    SELECT
        action_date,
        awarding_agency_name,
        award_description,
        federal_action_obligation,
        naics_description
    FROM transaction_normalized
    WHERE recipient_uei = '{company_uei}'
    ORDER BY action_date DESC
    LIMIT 100
""").fetchdf()

total_federal_funding = company_transactions["federal_action_obligation"].sum()
print(f"Total federal funding: ${total_federal_funding:,.2f}")
```

## Performance Considerations

### Database Dump Sizes

| Database Type | Compressed Size | Uncompressed Size | Tables | Records |
|--------------|-----------------|-------------------|--------|---------|
| Test         | ~50-100 GB      | ~200-400 GB       | ~100   | ~10M    |
| Full         | ~500-800 GB     | ~1.5-2.5 TB       | ~100   | ~100M+  |

### Processing Times

| Operation | Test DB | Full DB |
|-----------|---------|---------|
| Lambda download (15min timeout) | ✅ Completes | ⚠️ May timeout |
| DuckDB import | ~10-30 min | ~2-6 hours |
| SBIR filter query | ~1-5 min | ~15-30 min |
| S3 download (cached) | ~5-15 min | ~1-3 hours |

### Recommendations

1. **Start with Test DB**: Use `database_type: "test"` for initial development and testing
2. **Monitor Lambda Timeouts**: For large downloads, consider AWS Batch or Fargate
3. **Use DuckDB Filtering**: Always filter data at query time to avoid loading entire tables
4. **Cache S3 Downloads**: `cloudpathlib` automatically caches downloads in `/tmp/sbir-analytics-s3-cache`
5. **Limit Query Results**: Use `LIMIT` clauses to prevent memory issues

## Troubleshooting

### Lambda Timeout During Download

**Problem:** Large database dumps exceed 15-minute Lambda timeout

**Solution:**
- Use `database_type: "test"` for smaller dumps
- Implement AWS Batch or Fargate task for full database downloads
- Break download into multiple parts if possible

### DuckDB Out of Memory

**Problem:** `DuckDB out of memory` error during import

**Solution:**
```python
# Reduce DuckDB memory limit in config
duckdb:
  memory_limit: "4GB"  # Adjust based on available RAM
  threads: 4
```

### S3 Download Slow

**Problem:** Downloading from S3 takes too long

**Solution:**
- Use S3 Transfer Acceleration (enable on bucket)
- Run Dagster assets on EC2 in same region as S3 bucket
- Consider keeping local cache of frequently-used dumps

### Missing Data After Filtering

**Problem:** Expected records not found after SBIR filtering

**Solution:**
- Verify NAICS code filters (some SBIR companies may use different codes)
- Check agency name variations (e.g., "DOD" vs "Department of Defense")
- Review award amount thresholds (some Phase II awards exceed $1.5M)

## Monitoring

### CloudWatch Metrics

Monitor these metrics for the Lambda function:
- `Duration`: Should be < 900000 ms (15 minutes)
- `Errors`: Should be 0
- `Throttles`: Should be 0
- `MemoryUtilization`: Should be < 80%

### Dagster Asset Checks

Implement asset checks for data quality:

```python
@asset_check(
    asset="sbir_relevant_usaspending_transactions",
    description="Verify sufficient SBIR transactions extracted"
)
def sbir_transactions_volume_check(
    sbir_relevant_usaspending_transactions: pd.DataFrame,
) -> AssetCheckResult:
    """Check that we extracted a reasonable number of transactions."""
    transaction_count = len(sbir_relevant_usaspending_transactions)

    if transaction_count < 10000:
        return AssetCheckResult(
            passed=False,
            description=f"Only {transaction_count} transactions found (expected >10K)",
        )

    return AssetCheckResult(
        passed=True,
        description=f"Extracted {transaction_count:,} SBIR-relevant transactions",
    )
```

## Cost Optimization

### Monthly Cost Breakdown

| Component | Cost |
|-----------|------|
| Lambda execution (15min, 2GB RAM) | ~$0.05 |
| S3 storage (500GB, month 1) | ~$11.50 |
| S3 storage (500GB, month 4+) | ~$1.80 |
| Data transfer out | ~$0-5.00 |
| DuckDB processing (EC2 t3.large) | ~$2.00 |
| **Total monthly cost** | **~$15-20** |

### Optimization Tips

1. **Use Test DB**: Unless you need the full history, the test database is sufficient
2. **Delete Old Dumps**: Lifecycle policy automatically deletes dumps after 1 year
3. **Regional Processing**: Run Dagster assets in the same region as S3 to avoid transfer costs
4. **Selective Extraction**: Only extract and store the data you need
5. **Compress Output**: Store filtered results as Parquet or compressed CSV

## Future Enhancements

- [ ] Incremental processing (only process new/changed data)
- [ ] AWS Batch integration for full database downloads
- [ ] Automated data quality checks and alerts
- [ ] Real-time USAspending API fallback for missing records
- [ ] Integration with other federal spending databases (SAM.gov, FPDS, etc.)
- [ ] Advanced analytics: spending trends, agency patterns, company growth trajectories

## References

- [USAspending.gov Database Download](https://www.usaspending.gov/download_center/database_download)
- [USAspending Database Setup Guide](https://files.usaspending.gov/database_download/usaspending-db-setup.pdf)
- [DuckDB PostgreSQL Scanner](https://duckdb.org/docs/extensions/postgres_scanner.html)
- [AWS S3 Lifecycle Policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)
- [Dagster Asset Documentation](https://docs.dagster.io/guides/build/assets/defining-assets)

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review CloudWatch logs for Lambda/Dagster errors
3. Open an issue on the GitHub repository
4. Contact the SBIR Analytics team

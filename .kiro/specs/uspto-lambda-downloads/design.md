# Design – USPTO Patent Data Lambda Downloads

## Overview

Implement AWS Lambda functions to download USPTO patent datasets (PatentsView, Patent Assignments, AI Patents) and store them in S3, triggered by scheduled GitHub Actions workflows. The design follows the existing pattern used for SBIR award data downloads but extends it to support multiple USPTO data sources with different formats and update frequencies.

## Architecture

```text
GitHub Actions Workflow (scheduled/manual)
    ↓
AWS Lambda Functions (3 functions)
    ↓
USPTO Data Sources (PatentsView, USPTO.gov)
    ↓
AWS S3 (raw/uspto/{dataset}/{date}/)
```

## Lambda Functions

### 1. download-uspto-patentsview

**Location:** `scripts/lambda/download_uspto_patentsview/lambda_handler.py`

**Purpose:** Download PatentsView bulk data tables

**Configuration:**

- Runtime: Python 3.11
- Memory: 1024 MB
- Timeout: 30 minutes
- Handler: `lambda_handler.lambda_handler`

**Event Parameters:**

```json
{
  "s3_bucket": "sbir-etl-production-data",
  "dataset_type": "patent",  // or "assignee", "inventor", etc.
  "table_name": "patent",    // optional, defaults to dataset_type
  "source_url": "https://...",  // optional, will construct if not provided
  "force_refresh": false
}
```

**S3 Output:**

- Key: `raw/uspto/patentsview/{YYYY-MM-DD}/{dataset_type}.tsv`
- Metadata: sha256, source_url, downloaded_at, dataset_type

### 2. download-uspto-assignments

**Location:** `scripts/lambda/download_uspto_assignments/lambda_handler.py`

**Purpose:** Download USPTO Patent Assignment Dataset

**Configuration:**

- Runtime: Python 3.11
- Memory: 1024 MB
- Timeout: 30 minutes
- Handler: `lambda_handler.lambda_handler`

**Event Parameters:**

```json
{
  "s3_bucket": "sbir-etl-production-data",
  "source_url": "https://...",  // optional
  "format": "csv",  // or "dta", "parquet"
  "force_refresh": false
}
```

**S3 Output:**

- Key: `raw/uspto/assignments/{YYYY-MM-DD}/patent_assignments.{ext}`
- Metadata: sha256, source_url, downloaded_at, format

### 3. download-uspto-ai-patents

**Location:** `scripts/lambda/download_uspto_ai_patents/lambda_handler.py`

**Purpose:** Download USPTO AI Patent Dataset

**Configuration:**

- Runtime: Python 3.11
- Memory: 1024 MB
- Timeout: 30 minutes
- Handler: `lambda_handler.lambda_handler`

**Event Parameters:**

```json
{
  "s3_bucket": "sbir-etl-production-data",
  "source_url": "https://...",  // optional
  "force_refresh": false
}
```

**S3 Output:**

- Key: `raw/uspto/ai_patents/{YYYY-MM-DD}/ai_patent_dataset.{ext}`
- Metadata: sha256, source_url, downloaded_at, dataset

## CDK Infrastructure

### Lambda Stack Updates

**File:** `infrastructure/cdk/stacks/lambda_stack.py`

**Changes:**

- Add three new functions to `layer_functions` list:
  - `download-uspto-patentsview`
  - `download-uspto-assignments`
  - `download-uspto-ai-patents`
- Configure these functions with:
  - Timeout: 30 minutes (vs 15 for other layer functions)
  - Memory: 1024 MB (vs 512 for other layer functions)
  - Same IAM role and environment variables as other functions

### IAM Permissions

Lambda functions require:

- `s3:PutObject` on `arn:aws:s3:::sbir-etl-production-data/raw/uspto/*`
- `s3:GetObject` (optional, for verification)
- `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch

## GitHub Actions Workflow

### Workflow File

**Location:** `.github/workflows/uspto-data-refresh.yml`

**Triggers:**

- Scheduled: `0 9 1 * *` (monthly on 1st at 9 AM UTC)
- Manual: `workflow_dispatch` with inputs:
  - `dataset`: all/patentsview/assignments/ai_patents
  - `force_refresh`: boolean
  - `format`: csv/dta/parquet (for assignments)

**Job Steps:**

1. Configure AWS credentials (OIDC)
2. Determine which datasets to download
3. Invoke Lambda functions via AWS CLI
4. Display download summary
5. Upload results as artifacts

**Concurrency:**

- Group: `uspto-data-refresh`
- Cancel in progress: false (let downloads complete)

## Configuration

### config/base.yaml

**Location:** `config/base.yaml` → `extraction.uspto.download`

**Structure:**

```yaml
extraction:
  uspto:
    download:
      patentsview:
        enabled: true
        base_url: "https://patentsview.org/download/data-download-tables"
        schedule: "monthly"
        tables: ["patent", "assignee", "inventor"]
        s3_prefix: "raw/uspto/patentsview"
      assignments:
        enabled: true
        base_url: "https://www.uspto.gov/learning-and-resources/fee-schedules/patent-assignment-data"
        format: "csv"
        schedule: "monthly"
        s3_prefix: "raw/uspto/assignments"
      ai_patents:
        enabled: true
        base_url: "https://www.uspto.gov/ip-policy/economic-research/research-datasets"
        schedule: "quarterly"
        s3_prefix: "raw/uspto/ai_patents"
```

## Data Flow

1. **Scheduled Trigger:** GitHub Actions workflow runs monthly
2. **Lambda Invocation:** Workflow invokes Lambda functions with event payloads
3. **Download:** Lambda functions download data from USPTO sources
4. **Upload:** Lambda functions upload to S3 with metadata
5. **Verification:** Workflow checks Lambda responses and displays summary
6. **Downstream Processing:** Existing ETL pipeline reads from S3 paths

## Error Handling

### Lambda Functions

- Catch all exceptions and return 500 status with error details
- Log full stack traces to CloudWatch
- Include error context in response body

### GitHub Actions Workflow

- Check Lambda response status codes
- Fail job if any download fails
- Display error messages in workflow summary
- Upload error responses as artifacts for debugging

## Future Enhancements

1. **Incremental Downloads:** Track last download date and only fetch new data
2. **Multi-table Support:** Download multiple PatentsView tables in parallel
3. **Data Validation:** Add schema validation after download
4. **Notification:** Send Slack/email notifications on download completion
5. **Cost Optimization:** Use S3 Transfer Acceleration for large files

## Dependencies

- AWS Lambda Python runtime 3.11
- boto3 (S3 client)
- urllib (HTTP downloads)
- Existing CDK infrastructure
- GitHub Actions OIDC authentication

## Testing

### Local Testing

```bash
# Test Lambda handler locally
cd scripts/lambda/download_uspto_patentsview
python -c "from lambda_handler import lambda_handler; print(lambda_handler({'s3_bucket': 'test-bucket', 'dataset_type': 'patent'}, None))"
```

### Integration Testing

- Deploy Lambda functions via CDK
- Invoke manually via AWS CLI
- Verify S3 uploads and metadata
- Test GitHub Actions workflow via manual dispatch

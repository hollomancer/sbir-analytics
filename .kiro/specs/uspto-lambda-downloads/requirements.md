# Requirements – USPTO Patent Data Lambda Downloads

## Purpose

Define the behavioral requirements for automatically downloading USPTO patent datasets (PatentsView, Patent Assignments, AI Patents) via AWS Lambda functions triggered by GitHub Actions workflows, storing the data in S3 for downstream ETL processing.

## Glossary

- **PatentsView** – Comprehensive patent dataset with 40+ years of data, available via API and bulk downloads
- **Patent Assignment Dataset** – USPTO dataset containing patent transfers, assignments, licenses, and conveyances
- **AI Patent Dataset** – USPTO dataset identifying patents containing AI technologies
- **Lambda Function** – AWS Lambda function that downloads data from USPTO sources and uploads to S3
- **GitHub Actions Workflow** – Scheduled workflow that invokes Lambda functions to download USPTO data
- **S3 Storage** – AWS S3 bucket where downloaded datasets are stored with date-based prefixes

## Functional Requirements (EARS)

### R1 – PatentsView data download

**WHEN** the PatentsView download Lambda function is invoked **THEN** it SHALL download the requested PatentsView table (patent, assignee, inventor, etc.) from the PatentsView bulk download endpoint, compute a SHA-256 hash, and upload the data to S3 with metadata.

Acceptance:
- Lambda function accepts `dataset_type` or `table_name` parameter to specify which table to download
- Downloads use HTTPS with proper User-Agent headers
- S3 key follows pattern: `raw/uspto/patentsview/{YYYY-MM-DD}/{table_name}.tsv`
- Metadata includes: source_url, downloaded_at, dataset_type, sha256 hash, file_size
- Function returns success/failure status with S3 location

### R2 – Patent Assignment dataset download

**WHEN** the Patent Assignment download Lambda function is invoked **THEN** it SHALL download the USPTO Patent Assignment Dataset in the specified format (CSV, DTA, or Parquet), compute a SHA-256 hash, and upload to S3 with metadata.

Acceptance:
- Lambda function accepts `format` parameter (csv, dta, parquet) with default "csv"
- S3 key follows pattern: `raw/uspto/assignments/{YYYY-MM-DD}/patent_assignments.{ext}`
- Content-Type header set appropriately based on format
- Handles large file downloads with extended timeout (up to 30 minutes)
- Metadata includes format, source_url, downloaded_at, sha256 hash, file_size

### R3 – AI Patent dataset download

**WHEN** the AI Patent download Lambda function is invoked **THEN** it SHALL download the USPTO AI Patent Dataset, compute a SHA-256 hash, and upload to S3 with metadata.

Acceptance:
- Lambda function determines file format from Content-Type header or URL extension
- S3 key follows pattern: `raw/uspto/ai_patents/{YYYY-MM-DD}/ai_patent_dataset.{ext}`
- Handles compressed formats (ZIP) if provided by USPTO
- Metadata includes dataset type, source_url, downloaded_at, sha256 hash, file_size

### R4 – Scheduled downloads via GitHub Actions

**WHEN** the scheduled GitHub Actions workflow executes **THEN** it SHALL invoke the appropriate Lambda functions to download all enabled USPTO datasets according to their schedule (monthly or quarterly).

Acceptance:
- Workflow runs monthly on the 1st at 9 AM UTC via cron: `0 9 1 * *`
- Supports manual dispatch with inputs: dataset (all/patentsview/assignments/ai_patents), force_refresh, format
- Workflow invokes Lambda functions via AWS SDK with proper IAM authentication
- Each download step reports success/failure and uploads results as artifacts
- Workflow displays summary of all downloads with S3 locations and file sizes

### R5 – Error handling and retries

**WHEN** a Lambda function encounters a download failure **THEN** it SHALL log detailed error information, return a 500 status code with error details, and allow the workflow to handle retries.

Acceptance:
- Lambda functions catch exceptions and include stack traces in logs
- Error responses include descriptive error messages
- GitHub Actions workflow fails the job if any download fails
- CloudWatch Logs contain full error context for debugging

### R6 – Configuration management

**WHEN** Lambda functions are deployed **THEN** they SHALL read configuration from environment variables and event parameters, with defaults from `config/base.yaml`.

Acceptance:
- S3 bucket name comes from `S3_BUCKET` environment variable or event parameter
- Source URLs can be overridden via event parameters
- Configuration in `config/base.yaml` documents default URLs and schedules
- Lambda functions use appropriate timeouts and memory based on dataset size

## Non-Functional Requirements

### NFR1 – Performance

- Lambda functions must complete downloads within 30 minutes (max Lambda timeout)
- Memory allocation: 1024 MB for USPTO download functions (vs 512 MB for other layer functions)
- Large file downloads should stream directly to S3 when possible

### NFR2 – Reliability

- Downloads must handle network timeouts and retries (handled by urllib/requests)
- S3 uploads use atomic operations to prevent partial writes
- SHA-256 hashes enable data integrity verification

### NFR3 – Security

- Lambda functions use IAM roles with minimal permissions (S3 write, CloudWatch Logs)
- GitHub Actions uses OIDC authentication to AWS (no long-lived credentials)
- S3 bucket policies restrict access appropriately

### NFR4 – Observability

- CloudWatch Logs capture all download operations with timestamps
- Lambda function responses include metadata for tracking
- GitHub Actions workflow artifacts store download results for 7 days


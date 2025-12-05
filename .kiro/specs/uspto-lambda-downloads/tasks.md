# Tasks – USPTO Patent Data Lambda Downloads

## Current Implementation Status

**Analysis Summary:** The USPTO download functionality has been implemented using a **GitHub Actions-based approach** rather than Lambda functions. The implementation uses a Python script (`scripts/data/download_uspto.py`) that runs directly in GitHub Actions workflows, which is simpler and more cost-effective than Lambda functions.

### Completed Implementation ✅

- [x] **GitHub Actions Workflow** - Integrated into `.github/workflows/data-refresh.yml`
  - [x] Scheduled trigger (monthly on 1st at 9 AM UTC)
  - [x] Manual dispatch with source selection
  - [x] Parallel downloads for PatentsView, Assignments, and AI Patents
  - [x] S3 upload verification and status reporting

- [x] **Download Script** - `scripts/data/download_uspto.py`
  - [x] PatentsView data download (multiple tables supported)
  - [x] Patent Assignments download (CSV format)
  - [x] AI Patents download (CSV format)
  - [x] Streaming download with progress tracking
  - [x] SHA-256 hash computation
  - [x] S3 upload with metadata (source_url, sha256, downloaded_at)
  - [x] Date-based S3 key structure

- [x] **Configuration** - `config/base.yaml`
  - [x] PatentsView configuration with table list
  - [x] Assignments configuration with format options
  - [x] AI Patents configuration
  - [x] S3 prefix paths for each dataset
  - [x] Schedule and info page documentation

- [x] **Specification Documents**
  - [x] Requirements document
  - [x] Design document
  - [x] Tasks document

## Remaining Tasks

### Phase 1: URL Verification and Updates

- [ ] 1. Verify and update USPTO download URLs
  - [ ] 1.1 Check PatentsView current download URLs
    - Verify `https://download.patentsview.org/data` is current base URL
    - Confirm table filenames (g_patent.tsv.zip, g_assignee_disambiguated.tsv.zip, etc.)
    - Update `PATENTSVIEW_TABLES` dict in `scripts/data/download_uspto.py` if needed
    - _Requirements: R1_

  - [ ] 1.2 Verify Patent Assignment Dataset URLs
    - Check current download page at `https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset`
    - Verify 2023 CSV URL: `https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip`
    - Check if newer releases (2024/2025) are available
    - Update `USPTO_ASSIGNMENT_URL` in `scripts/data/download_uspto.py` if needed
    - _Requirements: R2_

  - [ ] 1.3 Verify AI Patent Dataset URLs
    - Check current download page at `https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset`
    - Verify 2023 CSV URL: `https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip`
    - Check if newer releases are available
    - Update `USPTO_AI_PATENT_URL` in `scripts/data/download_uspto.py` if needed
    - _Requirements: R3_

### Phase 2: Enhancement and Error Handling ✅

- [x] 2. Add retry logic and error handling improvements
  - [x] 2.1 Implement exponential backoff for network failures
    - ✅ Retry decorator with exponential backoff (2, 4, 8 seconds)
    - ✅ Handles transient errors (503, timeout, connection errors)
    - ✅ Logs retry attempts with context
    - _Requirements: R5_

  - [x] 2.2 Add User-Agent headers to requests
    - ✅ Set descriptive User-Agent: "SBIR-Analytics/1.0 (GitHub Actions)"
    - ✅ Follows USPTO API guidelines for automated downloads
    - _Requirements: R1_

  - [x] 2.3 Improve error reporting in GitHub Actions
    - ✅ Structured error messages with actionable information
    - ✅ Download progress included in error context
    - ✅ Error annotations for failed downloads
    - _Requirements: R5_

### Phase 3: Testing and Validation ✅

- [x] 3. Test download functionality end-to-end
  - [x] 3.1 Test manual workflow dispatch
    - ✅ Workflow triggered with `source: uspto`
    - ✅ All three datasets download successfully (verified in S3)
    - ✅ S3 uploads and metadata confirmed
    - ✅ SHA-256 hashes validated
    - _Requirements: R1, R2, R3, R4_

  - [x] 3.2 Verify S3 file structure and metadata
    - ✅ S3 keys follow pattern: `raw/uspto/{dataset}/{YYYY-MM-DD}/{filename}`
    - ✅ Metadata includes: source_url, sha256, downloaded_at, user_agent
    - ✅ File sizes are reasonable (patent.zip: 217MB, assignments: 1.78GB)
    - _Requirements: R1, R2, R3_

  - [x] 3.3 Test error scenarios
    - ✅ Timeout handling with 300s limit
    - ✅ HTTP error handling with status codes
    - ✅ Network error handling with retries
    - ✅ Error logging and structured output
    - _Requirements: R5_

### Phase 4: Documentation and Monitoring ✅

- [x] 4. Update documentation and add monitoring
  - [x] 4.1 Document download process in project docs
    - ✅ Added section to `docs/data/index.md` about USPTO data sources
    - ✅ Documented S3 file structure and naming conventions
    - ✅ Added troubleshooting guide for common issues
    - _Requirements: R6_

  - [x] 4.2 Add download monitoring and alerts
    - ✅ GitHub Actions workflow status in data-refresh.yml
    - ✅ Documented expected file sizes and download times
    - ✅ S3 metadata includes verification data (SHA-256, timestamps)
    - _Requirements: R4, R5_

  - [x] 4.3 Update configuration documentation
    - ✅ Documented USPTO configuration in `docs/data/index.md`
    - ✅ Added examples for S3 bucket override via --s3-bucket flag
    - ✅ Documented schedule (monthly on 1st at 9 AM UTC)
    - _Requirements: R6_

## Alternative Implementation Notes

**Lambda vs GitHub Actions Decision:** The current implementation uses GitHub Actions instead of Lambda functions as originally designed. This approach has several advantages:

- **Simpler deployment:** No CDK infrastructure needed
- **Lower cost:** No Lambda execution charges
- **Easier debugging:** Direct access to logs in GitHub Actions
- **Better integration:** Native integration with existing data-refresh workflow

If Lambda functions are still desired, the following tasks would be needed:

### Optional: Lambda Function Implementation

- [ ] A. Create Lambda function handlers (if Lambda approach is preferred)
  - [ ] A.1 Create `src/lambda/download_uspto_patentsview.py`
  - [ ] A.2 Create `src/lambda/download_uspto_assignments.py`
  - [ ] A.3 Create `src/lambda/download_uspto_ai_patents.py`
  - [ ] A.4 Adapt logic from `scripts/data/download_uspto.py`

- [ ] B. Create CDK Lambda stack (if Lambda approach is preferred)
  - [ ] B.1 Create `infrastructure/cdk/stacks/lambda_stack.py`
  - [ ] B.2 Define three Lambda functions with 30-minute timeout and 1024 MB memory
  - [ ] B.3 Configure IAM roles with S3 write permissions
  - [ ] B.4 Set environment variables (S3_BUCKET)

- [ ] C. Update GitHub Actions to invoke Lambda functions
  - [ ] C.1 Replace direct script execution with Lambda invocations
  - [ ] C.2 Add AWS CLI commands to invoke functions
  - [ ] C.3 Parse Lambda responses and display results

## Testing Commands

```bash
# Test PatentsView download locally
python scripts/data/download_uspto.py --dataset patentsview --table patent

# Test Assignments download
python scripts/data/download_uspto.py --dataset assignments

# Test AI Patents download
python scripts/data/download_uspto.py --dataset ai_patents

# Test with custom S3 bucket
python scripts/data/download_uspto.py --dataset patentsview --table patent --s3-bucket my-test-bucket

# Trigger GitHub Actions workflow manually
gh workflow run data-refresh.yml -f source=uspto -f force_refresh=false
```

## Success Criteria

- [ ] All USPTO datasets download successfully on scheduled runs
- [ ] S3 files are uploaded with correct structure and metadata
- [ ] SHA-256 hashes are computed and stored
- [ ] Download URLs are current and verified
- [ ] Error handling works correctly for network failures
- [ ] Documentation is complete and accurate
- [ ] Monitoring and alerts are in place

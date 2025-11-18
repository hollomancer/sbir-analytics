# Tasks – USPTO Patent Data Lambda Downloads

## Implementation Checklist

### Phase 1: Lambda Functions ✅

- [x] Create `download_uspto_patentsview` Lambda handler
  - [x] Implement download logic with User-Agent headers
  - [x] Handle TSV/CSV format detection
  - [x] Upload to S3 with date-based key
  - [x] Compute and store SHA-256 hash
  - [x] Return structured response with metadata

- [x] Create `download_uspto_assignments` Lambda handler
  - [x] Support multiple formats (CSV, DTA, Parquet)
  - [x] Handle large file downloads
  - [x] Set appropriate Content-Type headers
  - [x] Upload to S3 with format-specific extension

- [x] Create `download_uspto_ai_patents` Lambda handler
  - [x] Detect file format from Content-Type or URL
  - [x] Handle compressed formats (ZIP)
  - [x] Upload to S3 with appropriate extension

### Phase 2: Infrastructure ✅

- [x] Update CDK Lambda stack
  - [x] Add three new functions to `layer_functions` list
  - [x] Configure timeout (30 minutes) and memory (1024 MB)
  - [x] Set environment variables (S3_BUCKET)

- [x] Verify IAM permissions
  - [x] Lambda role has S3 write permissions
  - [x] Lambda role has CloudWatch Logs permissions

### Phase 3: GitHub Actions Workflow ✅

- [x] Create `.github/workflows/uspto-data-refresh.yml`
  - [x] Add scheduled trigger (monthly on 1st)
  - [x] Add manual dispatch with inputs
  - [x] Implement Lambda invocation steps
  - [x] Add download summary display
  - [x] Upload results as artifacts

### Phase 4: Configuration ✅

- [x] Add USPTO download config to `config/base.yaml`
  - [x] PatentsView configuration
  - [x] Assignments configuration
  - [x] AI Patents configuration

### Phase 5: Documentation ✅

- [x] Create specification documents
  - [x] Requirements document
  - [x] Design document
  - [x] Tasks document

## Next Steps

### Phase 6: Deployment & Testing

- [ ] Deploy Lambda functions via CDK
  - [ ] Run `cdk deploy sbir-etl-lambda`
  - [ ] Verify functions appear in AWS Console
  - [ ] Check IAM roles and permissions

- [ ] Test Lambda functions manually
  - [ ] Invoke via AWS CLI with test payloads
  - [ ] Verify S3 uploads and metadata
  - [ ] Check CloudWatch Logs for errors

- [ ] Test GitHub Actions workflow
  - [ ] Trigger manual dispatch
  - [ ] Verify Lambda invocations
  - [ ] Check workflow artifacts
  - [ ] Verify S3 file locations

### Phase 7: URL Verification

- [ ] Verify actual USPTO download URLs
  - [ ] Check PatentsView bulk download page structure
  - [ ] Verify Patent Assignment Dataset download links
  - [ ] Confirm AI Patent Dataset download URL
  - [ ] Update Lambda handlers with correct URLs

### Phase 8: Integration with ETL Pipeline

- [ ] Update USPTO extractor to read from S3
  - [ ] Modify `USPTOExtractor` to support S3 paths
  - [ ] Add S3 client configuration
  - [ ] Test extraction from S3 files

- [ ] Update Dagster assets
  - [ ] Add assets for S3-based USPTO extraction
  - [ ] Configure asset dependencies
  - [ ] Test end-to-end pipeline

## Known Issues & TODOs

1. **URL Placeholders:** Lambda handlers contain placeholder URLs that need to be updated with actual USPTO download endpoints
2. **Format Detection:** PatentsView format detection may need refinement based on actual response headers
3. **Large File Handling:** For very large files (>5GB), consider using S3 multipart uploads
4. **Retry Logic:** Add exponential backoff retry logic for network failures
5. **Cost Monitoring:** Set up CloudWatch alarms for Lambda execution costs

## Testing Commands

```bash
# Test PatentsView download locally
aws lambda invoke \
  --function-name sbir-etl-download-uspto-patentsview \
  --payload '{"s3_bucket":"sbir-etl-production-data","dataset_type":"patent"}' \
  response.json

# Test Assignments download
aws lambda invoke \
  --function-name sbir-etl-download-uspto-assignments \
  --payload '{"s3_bucket":"sbir-etl-production-data","format":"csv"}' \
  response.json

# Test AI Patents download
aws lambda invoke \
  --function-name sbir-etl-download-uspto-ai-patents \
  --payload '{"s3_bucket":"sbir-etl-production-data"}' \
  response.json
```

## Deployment Checklist

- [ ] CDK stack deployed successfully
- [ ] Lambda functions visible in AWS Console
- [ ] IAM roles have correct permissions
- [ ] GitHub Actions workflow runs successfully
- [ ] S3 files uploaded with correct structure
- [ ] CloudWatch Logs show successful executions
- [ ] Configuration documented in `config/base.yaml`
- [ ] Specification documents complete


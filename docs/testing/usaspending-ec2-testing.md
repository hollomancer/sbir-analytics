# Testing USAspending EC2 Automation

This guide covers testing the EC2-based USAspending database download automation and S3-first integration.

## Test Overview

1. **File Detection** - Check if new files are available
2. **Download Script** - Test the download script locally
3. **S3 Integration** - Verify S3 upload and file discovery
4. **DuckDB Integration** - Test that assets can find and use S3 files
5. **GitHub Actions Workflow** - Test the full automation
6. **End-to-End** - Full pipeline test

## Prerequisites

```bash
# Install dependencies
uv sync

# Configure AWS credentials
aws configure

# Set environment variables (optional - script has defaults)
export S3_BUCKET="sbir-etl-production-data"  # or your test bucket
export AWS_REGION="us-east-2"

# Or use the config environment variable
export SBIR_ETL__S3_BUCKET="sbir-etl-production-data"
```

## 1. Test File Detection Script

Test the file availability checker:

```bash
# Check if a new file is available (test database) - auto-discovers latest
# Note: --s3-bucket is optional - script uses default if not provided
uv run python scripts/usaspending/check_new_file.py \
  --database-type test \
  --json

# Check full database - auto-discovers latest
uv run python scripts/usaspending/check_new_file.py \
  --database-type full \
  --json

# Check with specific date
uv run python scripts/usaspending/check_new_file.py \
  --database-type full \
  --date 20251106 \
  --json

# Override S3 bucket if needed (only if you want a different bucket)
uv run python scripts/usaspending/check_new_file.py \
  --database-type test \
  --s3-bucket sbir-etl-production-data \
  --json

# Expected output:
# {
#   "available": true,
#   "is_new": true,
#   "last_modified": "2025-11-06T00:00:00Z",
#   "content_length": 233661229756,
#   "source_url": "https://files.usaspending.gov/..."
# }
```

**Verify:**
- ✅ `available: true` if file exists at source
- ✅ `is_new: true` if file doesn't exist in S3 or is newer
- ✅ `content_length` shows file size (~217GB for full)

## 2. Test Download Script Locally

Test the download script before running on EC2:

**Note:** `--s3-bucket` is optional. The script uses a default (`sbir-etl-production-data`) if not provided. Only include `--s3-bucket` if you want to override the default.

```bash
# Test with test database (no date needed - auto-discovers latest)
# Script uses default S3 bucket if not specified
uv run python scripts/usaspending/download_database.py \
  --database-type test

# Or specify date explicitly
uv run python scripts/usaspending/download_database.py \
  --database-type test \
  --date 20251106

# Test full database (will take 2-3 hours)
uv run python scripts/usaspending/download_database.py \
  --database-type full \
  --date 20251106

# Test with force refresh
uv run python scripts/usaspending/download_database.py \
  --database-type full \
  --force-refresh

# Override S3 bucket if needed (only if you want a different bucket)
uv run python scripts/usaspending/download_database.py \
  --database-type test \
  --s3-bucket sbir-etl-production-data
```

**Verify:**
- ✅ Script downloads from source URL
- ✅ Uploads to S3 using multipart upload
- ✅ Computes SHA256 hash
- ✅ File appears in S3: `s3://$S3_BUCKET/raw/usaspending/database/YYYY-MM-DD/`

**Check S3:**
```bash
aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ --recursive
```

## 3. Test S3 File Discovery

Test that the `find_latest_usaspending_dump()` function works:

```python
# Test in Python REPL
from src.utils.cloud_storage import find_latest_usaspending_dump

# Find latest test database
latest = find_latest_usaspending_dump(
    bucket="sbir-etl-production-data",
    database_type="test"
)
print(f"Latest test dump: {latest}")

# Find latest full database
latest = find_latest_usaspending_dump(
    bucket="sbir-etl-production-data",
    database_type="full"
)
print(f"Latest full dump: {latest}")
```

**Verify:**
- ✅ Returns S3 URL of latest file
- ✅ Returns `None` if no files found
- ✅ Handles both test and full database types

## 4. Test DuckDB Integration

Test that DuckDB can find and use the S3 file:

```python
# Test script: test_usaspending_s3_integration.py
from src.extractors.usaspending import DuckDBUSAspendingExtractor
from src.utils.cloud_storage import find_latest_usaspending_dump
from src.utils.cloud_storage import resolve_data_path

# Find latest dump
s3_url = find_latest_usaspending_dump(
    bucket="sbir-etl-production-data",
    database_type="test"  # Use test for faster testing
)

if not s3_url:
    print("No S3 dump found - download one first")
    exit(1)

print(f"Using dump: {s3_url}")

# Resolve S3 path (downloads to temp if needed)
dump_path = resolve_data_path(s3_url)
print(f"Resolved to: {dump_path}")

# Initialize extractor
extractor = DuckDBUSAspendingExtractor(db_path=":memory:")

# Import a small table for testing
success = extractor.import_postgres_dump(
    dump_path,
    table_name="recipient_lookup"
)

if success:
    print("✅ Successfully imported recipient_lookup table")
    
    # Query a sample
    df = extractor.query_awards(
        table_name="recipient_lookup",
        limit=10
    )
    print(f"Sample rows: {len(df)}")
    print(df.head())
else:
    print("❌ Import failed")
```

**Run:**
```bash
python test_usaspending_s3_integration.py
```

**Verify:**
- ✅ Finds latest S3 file
- ✅ Downloads to temp location
- ✅ DuckDB can import the dump
- ✅ Can query data from imported tables

## 5. Test Dagster Assets

Test that assets can find and use S3 files:

```python
# Test script: test_usaspending_assets.py
from dagster import build_op_context
from src.assets.usaspending_database_enrichment import sbir_relevant_usaspending_transactions
from src.assets.usaspending_ingestion import raw_usaspending_recipients

# Test recipient ingestion asset
context = build_op_context()
try:
    result = raw_usaspending_recipients(context)
    print(f"✅ Recipient ingestion successful")
    print(f"   Rows: {len(result.value)}")
    print(f"   Metadata: {result.metadata}")
except Exception as e:
    print(f"❌ Recipient ingestion failed: {e}")

# Test transaction extraction asset
try:
    result = sbir_relevant_usaspending_transactions(context)
    print(f"✅ Transaction extraction successful")
    print(f"   Rows: {len(result.value)}")
    print(f"   Metadata: {result.metadata}")
except Exception as e:
    print(f"❌ Transaction extraction failed: {e}")
```

**Or use Dagster UI:**
```bash
# Start Dagster
dagster dev

# Navigate to: http://localhost:3000
# Go to Assets → usaspending_database group
# Materialize: sbir_relevant_usaspending_transactions
```

**Verify:**
- ✅ Assets find latest S3 dump automatically
- ✅ Assets fail with clear error if S3 dump not found
- ✅ No silent fallbacks to local files

## 6. Test GitHub Actions Workflow (Dry Run)

Test the workflow without actually running it:

```bash
# Check workflow syntax
act -l --workflows .github/workflows/usaspending-database-download.yml

# Dry run (requires act: https://github.com/nektos/act)
act workflow_dispatch \
  --workflows .github/workflows/usaspending-database-download.yml \
  --eventpath test-event.json

# Create test event file
cat > test-event.json << EOF
{
  "inputs": {
    "database_type": "test",
    "force_refresh": "false"
  }
}
EOF
```

**Or test manually via GitHub UI:**
1. Go to Actions → USAspending Database Download
2. Click "Run workflow"
3. Select `database_type: test` (smaller file)
4. Monitor execution

## 7. Test EC2 Automation (Full Test)

### Prerequisites
- EC2 instance created and configured
- `EC2_INSTANCE_ID` added to GitHub secrets
- IAM role with S3 write permissions attached to EC2

### Test Steps

1. **Verify EC2 instance is accessible:**
```bash
INSTANCE_ID="i-xxxxx"  # Your EC2 instance ID

# Check instance status
aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].State.Name'

# Test SSM connection
aws ssm send-command \
  --instance-ids $INSTANCE_ID \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=['echo Hello from EC2']" \
  --query 'Command.CommandId' \
  --output text
```

2. **Test file detection in workflow:**
   - Workflow should check for new files
   - Should skip download if file already exists (unless `force_refresh=true`)

3. **Test download execution:**
   - Workflow should start EC2 instance
   - Upload script via SSM
   - Execute download
   - Monitor progress
   - Stop instance when complete

4. **Verify S3 file:**
```bash
# Check file exists
aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ --recursive

# Check file metadata
aws s3 head-object \
  --bucket $S3_BUCKET \
  --key raw/usaspending/database/2025-11-20/usaspending-db_20251106.zip
```

## 8. Test S3-First Priority Logic

Test that assets prioritize S3 and fail appropriately:

```python
# Test script: test_s3_priority.py
import os
from src.assets.usaspending_database_enrichment import sbir_relevant_usaspending_transactions
from dagster import build_op_context

# Test 1: S3 bucket configured, file exists
os.environ["SBIR_ETL__S3_BUCKET"] = "sbir-etl-production-data"
context = build_op_context()
try:
    result = sbir_relevant_usaspending_transactions(context)
    print("✅ S3 file found and used")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 2: S3 bucket configured, file doesn't exist
# (Delete test file first or use non-existent bucket)
os.environ["SBIR_ETL__S3_BUCKET"] = "non-existent-bucket"
context = build_op_context()
try:
    result = sbir_relevant_usaspending_transactions(context)
    print("❌ Should have failed but didn't")
except ExtractionError as e:
    print(f"✅ Correctly failed with error: {e}")
except Exception as e:
    print(f"⚠️ Failed with unexpected error: {e}")

# Test 3: No S3 bucket configured
del os.environ["SBIR_ETL__S3_BUCKET"]
context = build_op_context()
try:
    result = sbir_relevant_usaspending_transactions(context)
    print("❌ Should have failed but didn't")
except ExtractionError as e:
    print(f"✅ Correctly failed with error: {e}")
```

**Verify:**
- ✅ Uses S3 when available
- ✅ Fails with clear error when S3 unavailable
- ✅ No silent fallbacks

## 9. Integration Test (Full Pipeline)

Test the complete flow:

```bash
# 1. Download database via EC2 automation (or manually)
# 2. Verify file in S3
aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ --recursive

# 3. Run Dagster asset that uses it
dagster asset materialize -m src.assets.usaspending_database_enrichment sbir_relevant_usaspending_transactions

# 4. Verify asset succeeded
# Check Dagster UI or logs
```

## 10. Performance Testing

Test download performance:

```bash
# Time the download
time python scripts/usaspending/download_database.py \
  --database-type test \
  --s3-bucket $S3_BUCKET

# Monitor S3 upload progress
watch -n 5 "aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ --recursive --human-readable"
```

**Expected:**
- Test database: ~30-60 minutes
- Full database: ~2-3 hours
- Upload speed: ~1.5 GB/min

## Troubleshooting

### File Detection Fails

**Problem:** `check_new_file.py` returns `available: false`

**Solutions:**
```bash
# Check if URL is accessible
curl -I "https://files.usaspending.gov/database_download/usaspending-db_20251106.zip"

# Try different date
python scripts/usaspending/check_new_file.py \
  --database-type full \
  --date $(date +%Y%m%d)  # Current date
```

### S3 File Not Found

**Problem:** `find_latest_usaspending_dump()` returns `None`

**Solutions:**
```bash
# List files in S3
aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ --recursive

# Check if files match expected pattern
aws s3 ls s3://$S3_BUCKET/raw/usaspending/database/ | grep "usaspending-db"
```

### DuckDB Import Fails

**Problem:** `import_postgres_dump()` returns `False`

**Solutions:**
```bash
# Verify file is accessible
aws s3 head-object \
  --bucket $S3_BUCKET \
  --key raw/usaspending/database/2025-11-20/usaspending-db_20251106.zip

# Check file integrity (SHA256)
# (Should be in S3 metadata)
```

### EC2 SSM Command Fails

**Problem:** SSM command times out or fails

**Solutions:**
```bash
# Check SSM agent status
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=$INSTANCE_ID"

# Check recent commands
aws ssm list-commands --instance-id $INSTANCE_ID

# View command output
aws ssm get-command-invocation \
  --command-id <COMMAND_ID> \
  --instance-id $INSTANCE_ID
```

## Test Checklist

- [ ] File detection script works
- [ ] Download script works locally
- [ ] S3 file discovery works
- [ ] DuckDB can import from S3
- [ ] Dagster assets find S3 files
- [ ] Assets fail appropriately when S3 unavailable
- [ ] GitHub Actions workflow runs successfully
- [ ] EC2 automation completes download
- [ ] File appears in correct S3 location
- [ ] End-to-end pipeline works

## Next Steps

After testing:
1. Set up EC2 instance (if not done)
2. Add `EC2_INSTANCE_ID` to GitHub secrets
3. Schedule monthly workflow
4. Monitor first production run


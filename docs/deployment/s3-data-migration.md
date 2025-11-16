# S3 Data Migration Guide

This guide documents the migration of raw data files from local storage to S3, and the implementation of S3-first data access with local fallback.

## Overview

The SBIR ETL pipeline now supports:
- **S3-first data access**: Automatically tries S3 before falling back to local files
- **Local fallback**: If S3 is unavailable or offline, uses local `data/raw/` directory
- **Automatic path resolution**: Builds S3 URLs from local paths when bucket is configured

## Architecture

### Components

1. **`src/utils/cloud_storage.py`**: Core utility for S3-first path resolution
   - `resolve_data_path()`: Resolves S3 URLs or local paths with fallback
   - `build_s3_path()`: Constructs S3 URLs from relative paths
   - `get_s3_bucket_from_env()`: Reads bucket name from environment

2. **`src/extractors/sbir.py`**: Updated to use cloud storage utilities
   - Automatically builds S3 path if bucket is configured
   - Resolves path with S3-first, local fallback strategy

3. **`src/config/schemas.py`**: Added S3 configuration options
   - `csv_path_s3`: Optional S3 URL (auto-built if bucket configured)
   - `use_s3_first`: Boolean flag to enable S3-first behavior

## Configuration

### Environment Variable

Set the S3 bucket name via environment variable:

```bash
export SBIR_ETL__S3_BUCKET=sbir-etl-production-data
```

Or in Dagster Cloud UI:
- Go to **Settings** → **Environment Variables**
- Add: `SBIR_ETL__S3_BUCKET` = `sbir-etl-production-data`

### Config File (`config/base.yaml`)

```yaml
extraction:
  sbir:
    csv_path: "data/raw/sbir/awards_data.csv"  # Local fallback path
    csv_path_s3: null  # Auto-built from csv_path if bucket configured
    use_s3_first: true  # Try S3 first, fallback to local
```

## Data Migration Steps

### 1. Upload Files to S3

```bash
# Upload SBIR CSV files
aws s3 sync data/raw/sbir/ s3://sbir-etl-production-data/data/raw/sbir/ \
  --exclude "*.gitkeep" \
  --exclude ".DS_Store"

# Upload USPTO CSV files (if needed)
aws s3 sync data/raw/uspto/ s3://sbir-etl-production-data/data/raw/uspto/ \
  --exclude "*.gitkeep" \
  --exclude ".DS_Store"
```

### 2. Verify Upload

```bash
# List files in S3
aws s3 ls s3://sbir-etl-production-data/data/raw/sbir/ --recursive

# Check specific file
aws s3 ls s3://sbir-etl-production-data/data/raw/sbir/awards_data.csv
```

### 3. Set Environment Variable

**Local Development:**
```bash
export SBIR_ETL__S3_BUCKET=sbir-etl-production-data
```

**Dagster Cloud:**
1. Go to https://sbir.dagster.cloud/prod/settings/environment-variables
2. Add environment variable:
   - Key: `SBIR_ETL__S3_BUCKET`
   - Value: `sbir-etl-production-data`
3. Save changes (will trigger code location reload)

## How It Works

### Path Resolution Flow

1. **If `SBIR_ETL__S3_BUCKET` is set:**
   - Builds S3 URL: `s3://sbir-etl-production-data/data/raw/sbir/awards_data.csv`
   - Tries to access S3 file
   - If S3 succeeds → downloads to temp cache and uses it
   - If S3 fails → falls back to local `data/raw/sbir/awards_data.csv`

2. **If `SBIR_ETL__S3_BUCKET` is not set:**
   - Uses local path directly (backward compatible)

3. **If `use_s3_first=False`:**
   - Prefers local even if S3 is available

### S3 File Caching

- S3 files are downloaded to `/tmp/sbir-etl-s3-cache/` (or system temp directory)
- Files are cached by MD5 hash of S3 path to avoid re-downloading
- Cache persists across runs within the same execution environment

## Testing

### Test S3 Access Locally

```bash
# Set environment variable
export SBIR_ETL__S3_BUCKET=sbir-etl-production-data

# Run extraction
uv run dagster asset materialize -m src.definitions raw_sbir_awards
```

### Test Local Fallback

```bash
# Unset environment variable (or set to empty)
unset SBIR_ETL__S3_BUCKET

# Should fall back to local files
uv run dagster asset materialize -m src.definitions raw_sbir_awards
```

### Test in Dagster Cloud

1. Set `SBIR_ETL__S3_BUCKET` environment variable in Dagster Cloud UI
2. Materialize `raw_sbir_awards` asset
3. Check logs for:
   - `"Using S3 file: s3://..."` (S3 success)
   - `"Using local fallback: ..."` (S3 failed, using local)
   - `"Downloaded awards_data.csv (X.XX MB)"` (S3 download)

## Troubleshooting

### S3 Access Denied

**Error:** `AccessDenied` or `403 Forbidden`

**Solution:**
- Verify AWS credentials are configured (via `aws configure` or IAM role)
- Check bucket policy allows read access
- Verify bucket name is correct

### File Not Found

**Error:** `FileNotFoundError: Neither S3 (...) nor local (...) file exists`

**Solution:**
- Verify file exists in S3: `aws s3 ls s3://sbir-etl-production-data/data/raw/sbir/awards_data.csv`
- Verify local fallback path exists: `ls data/raw/sbir/awards_data.csv`
- Check environment variable is set correctly

### Slow Performance

**Symptom:** S3 downloads are slow

**Solution:**
- Files are cached after first download
- Consider using AWS CloudFront or S3 Transfer Acceleration
- For very large files, consider using DuckDB's native S3 support (future enhancement)

## AWS Credentials

### Local Development

Configure AWS credentials:

```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
```

### Dagster Cloud

Dagster Cloud Serverless uses IAM roles for S3 access. Configure:

1. Go to **Settings** → **AWS Integration**
2. Attach IAM role with S3 read permissions:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:ListBucket"],
         "Resource": [
           "arn:aws:s3:::sbir-etl-production-data",
           "arn:aws:s3:::sbir-etl-production-data/*"
         ]
       }
     ]
   }
   ```

## Future Enhancements

- [ ] Direct S3 support in DuckDB (via `httpfs` extension)
- [ ] Support for other cloud storage (GCS, Azure Blob)
- [ ] Configurable cache directory and TTL
- [ ] Parallel S3 downloads for multiple files
- [ ] S3 path validation and health checks

## References

- [cloudpathlib documentation](https://cloudpathlib.drivendata.org/)
- [boto3 S3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [Dagster Cloud Environment Variables](https://docs.dagster.io/cloud/deployment/serverless/environment-variables)


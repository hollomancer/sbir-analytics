# USPTO Data Refresh Issue Analysis - 2025-11-29

## Summary

The USPTO data refresh workflow completed successfully but downloaded **placeholder/outdated files** instead of the full datasets. Two of three datasets show suspiciously small file sizes (16 KB) with identical SHA256 hashes.

## Evidence

### File Sizes from Workflow Output

| Dataset | File Size | Expected Size | Status |
|---------|-----------|---------------|--------|
| PatentsView | 227 MB | ~200-300 MB | ✅ OK |
| Patent Assignments | 16 KB | >100 MB | ❌ TOO SMALL |
| AI Patents | 16 KB | >10 MB | ❌ TOO SMALL |

### Duplicate SHA256 Hashes

Both Patent Assignments and AI Patents show identical hash:

```
7e30f3d0fb18872e5a3319a7e56e0b869cd26071e2925763789e4db3f519bae7
```

This is **impossible** for different files and indicates:

- Download failure with cached/placeholder data
- Wrong file being downloaded (error page, redirect, etc.)
- Hash calculation error

## Root Cause

The Lambda functions are downloading from **correct URLs** but the files being returned are **not the actual datasets**. Investigation reveals:

### Expected vs Actual File Sizes

| Dataset | Expected Size | Actual Downloaded | URL |
|---------|---------------|-------------------|-----|
| Patent Assignments (full) | 1.78 GB (CSV) | 16 KB | `ECORSEXC/2023/csv.zip` |
| AI Patents | 764 MB (CSV) | 16 KB | `ECOPATAI/2023/ai_model_predictions.csv.zip` |

### Possible Causes

1. **Network/CDN issues**: Files not properly uploaded to data.uspto.gov
2. **Access restrictions**: Lambda IP addresses may be blocked or rate-limited
3. **Redirect to error page**: URLs returning 200 status but serving error HTML
4. **Temporary outage**: USPTO data portal experiencing issues
5. **Authentication required**: New authentication requirements not documented

## Impact

- **Data freshness**: Missing 1-2 years of patent assignment and AI patent data
- **Silent failure**: Workflow reports success despite downloading wrong files
- **Downstream effects**: Any analysis using these datasets will be incomplete/incorrect

## Immediate Actions Taken

Added file size validation to both Lambda functions to detect placeholder files:

```python
# Validate file size (should be >1MB)
MIN_EXPECTED_SIZE = 1_000_000  # 1 MB
if len(data) < MIN_EXPECTED_SIZE:
    raise ValueError(
        f"Downloaded file is suspiciously small ({len(data)} bytes, expected >{MIN_EXPECTED_SIZE}). "
        f"This may be a placeholder or error page. "
        f"Check {USPTO_DATASET_PAGE} for the latest release URL."
    )
```

This will cause the Lambda to **fail loudly** instead of silently uploading bad data.

## Required Fixes

### 1. Investigate Download Failure (High Priority - URGENT)

The URLs are correct but downloads are failing. Need to:

**Test manually:**

```bash
# Test from local machine
curl -I "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip"
curl -I "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip"

# Check actual file size
curl -L "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip" | wc -c
```

**Check Lambda execution logs:**

- Review CloudWatch logs for HTTP response codes
- Check for redirects or error messages
- Verify User-Agent header is accepted
- Check for rate limiting or IP blocking

**Possible solutions:**

- Add retry logic with exponential backoff
- Use different User-Agent string
- Add authentication if required
- Download from alternative mirror/CDN
- Contact USPTO if data portal is down

### 2. Add Response Validation (High Priority)

Beyond file size, validate the response:

```python
# Check Content-Type header
if "text/html" in content_type:
    raise ValueError("Received HTML instead of ZIP file - likely an error page")

# Check ZIP file magic bytes
if not data.startswith(b'PK\x03\x04'):
    raise ValueError("Downloaded file is not a valid ZIP archive")
```

### 3. Enhanced Error Reporting (Medium Priority)

Capture more diagnostic information:

- HTTP response headers
- First 1KB of response body (for error messages)
- Response status code
- Redirect chain if any

## Testing Plan

1. **Manual URL verification**: Visit USPTO pages and find correct 2024/2025 URLs
2. **Local testing**: Test Lambda functions with updated URLs locally
3. **Staging deployment**: Deploy to staging and verify downloads
4. **Production deployment**: Update production Lambda functions
5. **Validation**: Run workflow and verify file sizes/hashes

## Prevention

To prevent this in the future:

1. **Quarterly URL review**: Check for new releases every quarter
2. **Automated discovery**: Implement URL discovery logic
3. **Size validation**: Keep minimum size thresholds updated
4. **Documentation**: Maintain list of expected file sizes per dataset
5. **Monitoring**: Alert on significant file size changes

## Next Steps

1. ✅ Add file size validation (COMPLETED - will now fail loudly)
2. ⏳ **URGENT**: Test URLs manually to determine why downloads are failing
3. ⏳ Check Lambda CloudWatch logs for HTTP response details
4. ⏳ Add ZIP file magic byte validation
5. ⏳ Add Content-Type header validation
6. ⏳ Deploy updated Lambda functions
7. ⏳ Re-run data refresh workflow
8. ⏳ If still failing, contact USPTO or find alternative download method

## Related Files

- `.github/workflows/data-refresh.yml` - Workflow definition
- `scripts/lambda/download_uspto_assignments/lambda_handler.py` - Assignments Lambda
- `scripts/lambda/download_uspto_ai_patents/lambda_handler.py` - AI Patents Lambda
- `scripts/lambda/download_uspto_patentsview/lambda_handler.py` - PatentsView Lambda (working correctly)

## References

- [USPTO Research Datasets](https://www.uspto.gov/ip-policy/economic-research/research-datasets)
- [Patent Assignment Dataset](https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset)
- [AI Patent Dataset](https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset)

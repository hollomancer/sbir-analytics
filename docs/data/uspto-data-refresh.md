---
Type: Process Documentation
Owner: data-team
Last-Reviewed: 2024-12-04
Status: active
---

# USPTO Data Refresh Process

This document describes the automated process for downloading USPTO patent datasets to S3 for use in the SBIR Analytics pipeline.

## Overview

The USPTO data refresh process downloads three key datasets:
1. **PatentsView** - Comprehensive patent data (grants, assignees, inventors, etc.)
2. **Patent Assignments** - Patent ownership transfers and assignments
3. **AI Patents** - USPTO's AI Patent Dataset identifying AI-related patents

**Implementation:** GitHub Actions workflow + Python script (not Lambda functions)

## Data Sources

### 1. PatentsView Dataset

**Source:** https://download.patentsview.org/data

**Last Verified:** December 2024

**Available Tables:**
- `patent` - Patent grants (g_patent.tsv.zip)
- `assignee` - Patent assignees (g_assignee_disambiguated.tsv.zip)
- `inventor` - Patent inventors (g_inventor_disambiguated.tsv.zip)
- `location` - Geographic locations (g_location_disambiguated.tsv.zip)
- `cpc` - CPC classifications (g_cpc_current.tsv.zip)
- `gov_interest` - Government interest statements (g_gov_interest.tsv.zip)

**Format:** TSV files compressed as ZIP

**Update Frequency:** Quarterly

**Documentation:** https://patentsview.org/download/data-download-tables

### 2. Patent Assignment Dataset

**Source:** https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-assignment-dataset

**Last Verified:** December 2024

**Latest Release:** 2023 (as of Dec 2024)

**Download URL:** https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip

**Size:** 1.78 GB (CSV format), 1.56 GB (DTA format)

**Contents:**
- `assignment.csv` - Assignment records (365 MB)
- `assignor.csv` - Assignor entities (287 MB)
- `assignee.csv` - Assignee entities (279 MB)
- `documentid.csv` - Patent document IDs (700 MB)
- `assignment_conveyance.csv` - Conveyance types (28.6 MB)
- `documentid_admin.csv` - Administrative data (163 MB)

**Coverage:** 10.5 million patent assignments since 1970, involving 18.8 million patents

**Update Frequency:** Monthly

**Citation:** Graham, SJH, Marco, AC, Myers, AF. Patent transactions in the marketplace: Lessons from the USPTO Patent Assignment Dataset. *J Econ Manage Strat*. 2018; 27: 343–371. https://doi.org/10.1111/jems.12262

### 3. AI Patent Dataset

**Source:** https://www.uspto.gov/ip-policy/economic-research/research-datasets/artificial-intelligence-patent-dataset

**Last Verified:** December 2024

**Latest Release:** 2023 (updated January 8, 2025)

**Download URL:** https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip

**Size:** 764 MB (CSV format)

**Coverage:** 15.4 million U.S. patent documents (1976-2023) with AI predictions

**Format:** CSV (2023 release), TSV (2020 release)

**Update Frequency:** Annually/Quarterly

**Citation:** Pairolero, N.A., Giczy, A.V., Torres, G., Islam Erana, T., Finlayson, M.A., & Toole, A.A. The artificial intelligence patent dataset (AIPD) 2023 update. J Technol Transf (2025).

**Release Notes:** The AIPD 2023 was updated on January 8, 2025 to fix a minor issue affecting the predict93* variables.

## Automated Refresh

### GitHub Actions Workflow

**File:** `.github/workflows/data-refresh.yml`

**Schedule:**
- **Monthly:** 1st of month at 9 AM UTC (`0 9 1 * *`)
- Runs as part of the unified data-refresh workflow

**Manual Trigger:**
```bash
gh workflow run data-refresh.yml -f source=uspto -f force_refresh=false
```

**Workflow Steps:**
1. Configure AWS credentials (OIDC)
2. Setup Python and UV
3. Download USPTO datasets in parallel:
   - PatentsView (patent table)
   - Patent Assignments (CSV format)
   - AI Patents (CSV format)
4. Upload to S3 with metadata
5. Display download summary
6. Upload results as artifacts

### Download Script

**File:** `scripts/data/download_uspto.py`

**Features:**
- Streaming downloads with progress tracking
- SHA-256 hash computation
- Exponential backoff retry logic (3 attempts)
- User-Agent header: `SBIR-Analytics/1.0 (GitHub Actions)`
- S3 upload with metadata (source_url, sha256, downloaded_at)
- Date-based S3 key structure

**Usage:**
```bash
# Download PatentsView patent table
python scripts/data/download_uspto.py --dataset patentsview --table patent

# Download Patent Assignments
python scripts/data/download_uspto.py --dataset assignments

# Download AI Patents
python scripts/data/download_uspto.py --dataset ai_patents

# Custom S3 bucket
python scripts/data/download_uspto.py --dataset patentsview --table assignee --s3-bucket my-bucket
```

## S3 Storage Structure

**Bucket:** `sbir-etl-production-data`

**Key Pattern:** `raw/uspto/{dataset}/{YYYY-MM-DD}/{filename}`

**Examples:**
```
raw/uspto/patentsview/2024-12-01/patent.zip
raw/uspto/patentsview/2024-12-01/assignee.zip
raw/uspto/assignments/2024-12-01/patent_assignments.zip
raw/uspto/ai_patents/2024-12-01/ai_patent_dataset.zip
```

**Metadata:**
- `source_url` - Original download URL
- `sha256` - File hash for integrity verification
- `downloaded_at` - ISO 8601 timestamp
- `user_agent` - Download client identifier

## Configuration

**File:** `config/base.yaml`

**Section:** `extraction.uspto.download`

```yaml
extraction:
  uspto:
    download:
      patentsview:
        enabled: true
        base_url: "https://download.patentsview.org/data"
        schedule: "monthly"
        tables: ["patent", "assignee", "inventor"]
        s3_prefix: "raw/uspto/patentsview"

      assignments:
        enabled: true
        download_url: "https://data.uspto.gov/ui/datasets/products/files/ECORSEXC/2023/csv.zip"
        format: "csv"
        release_year: 2023
        schedule: "monthly"
        s3_prefix: "raw/uspto/assignments"

      ai_patents:
        enabled: true
        download_url: "https://data.uspto.gov/ui/datasets/products/files/ECOPATAI/2023/ai_model_predictions.csv.zip"
        format: "csv"
        release_year: 2023
        schedule: "quarterly"
        s3_prefix: "raw/uspto/ai_patents"
```

## Error Handling

### Retry Logic

The download script implements exponential backoff retry logic:
- **Max Retries:** 3 attempts
- **Backoff Factor:** 2 (delays: 2s, 4s, 8s)
- **Retry Status Codes:** 429, 500, 502, 503, 504
- **Timeout:** 300 seconds per request

### Error Types

**Network Errors:**
- Connection timeouts
- DNS resolution failures
- SSL/TLS errors

**HTTP Errors:**
- 404 Not Found - URL may have changed
- 429 Too Many Requests - Rate limiting
- 500+ Server Errors - USPTO service issues

**S3 Errors:**
- Permission denied - Check IAM roles
- Bucket not found - Verify bucket name
- Upload failures - Check network/credentials

### Troubleshooting

**Download Fails:**
1. Verify URLs are current (check USPTO websites)
2. Check network connectivity
3. Review CloudWatch Logs for detailed errors
4. Try manual download to test URL

**S3 Upload Fails:**
1. Verify AWS credentials are configured
2. Check IAM role permissions
3. Verify S3 bucket exists and is accessible
4. Check S3 bucket policies

**Workflow Fails:**
1. Check GitHub Actions logs
2. Verify AWS OIDC authentication
3. Check environment variables (S3_BUCKET)
4. Review workflow artifacts for error details

## Monitoring

### Success Metrics

- Download completion time
- File sizes (verify against expected sizes)
- SHA-256 hashes (for integrity verification)
- S3 upload success rate

### Expected File Sizes

| Dataset | Size | Notes |
|---------|------|-------|
| PatentsView Patent | ~500 MB - 2 GB | Varies by table |
| Patent Assignments | 1.78 GB | Full 2023 CSV dataset |
| AI Patents | 764 MB | 2023 CSV release |

### Alerts

**GitHub Actions:**
- Workflow failure notifications
- Artifact upload for debugging

**CloudWatch (if using Lambda):**
- Execution duration
- Error rates
- Memory usage

## Downstream Processing

After download, the data is processed by:

1. **USPTO Extractors** (`src/extractors/uspto/`)
   - Parse CSV/TSV files
   - Validate schema
   - Extract relevant fields

2. **USPTO Transformers** (`src/transformers/uspto/`)
   - Normalize entity names
   - Detect conveyance types
   - Build assignment chains

3. **USPTO Loaders** (`src/loaders/neo4j/`)
   - Load patents to Neo4j
   - Create assignment relationships
   - Link to SBIR awards

## Verification

### Manual Verification

```bash
# List recent downloads
aws s3 ls s3://sbir-etl-production-data/raw/uspto/patentsview/ --recursive --human-readable

# Check file metadata
aws s3api head-object --bucket sbir-etl-production-data --key raw/uspto/patentsview/2024-12-01/patent.zip

# Download and verify hash
aws s3 cp s3://sbir-etl-production-data/raw/uspto/patentsview/2024-12-01/patent.zip - | sha256sum
```

### Automated Tests

**File:** `tests/integration/test_uspto_download.py`

**Tests:**
- Script help message
- Invalid dataset rejection
- Invalid table rejection
- Script exists and is executable
- Import dependencies

**Run Tests:**
```bash
pytest tests/integration/test_uspto_download.py -v
```

## URL Verification History

| Date | PatentsView | Assignments | AI Patents | Notes |
|------|-------------|-------------|------------|-------|
| 2024-12-04 | ✅ Valid | ✅ Valid (2023) | ✅ Valid (2023) | All URLs verified and working |

## Future Enhancements

1. **Incremental Downloads:** Track last download date and only fetch new data
2. **Multi-table Support:** Download multiple PatentsView tables in parallel
3. **Data Validation:** Add schema validation after download
4. **Notification:** Send Slack/email notifications on download completion
5. **Cost Monitoring:** Track S3 storage costs and download bandwidth

## Related Documentation

- [USPTO Patent Data Dictionary](dictionaries/uspto-patent-data-dictionary.md)
- [Patent Neo4j Schema](../schemas/patent-neo4j-schema.md)
- [Data Sources Overview](index.md)
- [Configuration Patterns](../../.kiro/steering/configuration-patterns.md)

## Contact

For questions about USPTO data refresh:
- **Email:** EconomicsData@uspto.gov (USPTO data questions)
- **GitHub Issues:** Use `data-refresh` label
- **Slack:** #data-engineering channel

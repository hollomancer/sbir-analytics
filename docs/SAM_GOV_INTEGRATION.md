# SAM.gov Bulk Data Integration

## Overview

The SAM.gov bulk data integration provides a parquet-first, API-fallback pattern for accessing SAM.gov entity records. This integration follows the same architecture pattern as the USAspending integration, providing efficient bulk data access with graceful fallback to API queries when needed.

## Architecture

### Data Source Priority

1. **PRIMARY**: Parquet file (S3 or local)
2. **FALLBACK**: SAM.gov API (for individual entity lookups)
3. **FAIL**: If both sources unavailable

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                    SAM.gov Integration                       │
└─────────────────────────────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐     ┌──────────┐
    │ Extractor│      │  Assets  │     │   API    │
    │          │      │          │     │  Client  │
    └──────────┘      └──────────┘     └──────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                    ┌───────┴────────┐
                    │                │
                    ▼                ▼
              ┌──────────┐    ┌──────────┐
              │   S3     │    │  Local   │
              │ Parquet  │    │ Parquet  │
              └──────────┘    └──────────┘
```

## File Structure

### Core Implementation

```
src/
├── extractors/
│   └── sam_gov.py                  # SAMGovExtractor class
├── assets/
│   └── sam_gov_ingestion.py        # Dagster asset for bulk ingestion
├── enrichers/
│   └── sam_gov/
│       ├── __init__.py
│       └── client.py                # SAMGovAPIClient (fallback)
├── utils/
│   └── cloud_storage.py            # S3 utilities (find_latest_sam_gov_parquet)
└── config/
    └── schemas/
        └── data_pipeline.py         # SamGovConfig schema
```

### Configuration

```
config/
└── base.yaml                        # SAM.gov extraction settings
```

### Tests

```
tests/
├── unit/
│   ├── extractors/
│   │   └── test_sam_gov_extractor.py
│   └── assets/
│       └── test_sam_gov_ingestion.py
└── integration/
    └── test_sam_gov_integration.py
```

## Configuration

### config/base.yaml

```yaml
extraction:
  sam_gov:
    parquet_path: "data/raw/sam_gov/sam_entity_records.parquet"  # Local fallback
    parquet_path_s3: null  # Auto-built if S3_BUCKET env var set
    use_s3_first: true     # Try S3 first, fallback to local
    batch_size: 10000      # Chunk size for processing
```

### Schema Definition

Located in `src/config/schemas/data_pipeline.py`:

```python
class SamGovConfig(BaseModel):
    """SAM.gov parquet extraction configuration."""

    parquet_path: str = Field(
        default="data/raw/sam_gov/sam_entity_records.parquet",
        description="Path to SAM.gov parquet file (local fallback path)",
    )
    parquet_path_s3: str | None = Field(
        default=None,
        description="S3 URL for SAM.gov parquet (auto-built if bucket configured)",
    )
    use_s3_first: bool = Field(
        default=True,
        description="If True, try S3 first, fallback to local parquet_path"
    )
    batch_size: int = Field(
        default=10000,
        description="Batch size for chunked processing"
    )
```

## Usage

### 1. Extractor (Parquet-based)

```python
from src.extractors.sam_gov import SAMGovExtractor

# Initialize extractor
extractor = SAMGovExtractor()

# Load parquet file (S3-first if configured, local fallback)
df = extractor.load_parquet()

# Or specify path explicitly
df = extractor.load_parquet(
    parquet_path="data/raw/sam_gov/sam_entity_records.parquet",
    use_s3_first=False
)

# Query by UEI
entity = extractor.get_entity_by_uei(df, "ABC123456789")

# Query by CAGE code
entity = extractor.get_entity_by_cage(df, "1ABC5")
```

### 2. Dagster Asset (Pipeline Integration)

```python
from dagster import asset
from src.assets.sam_gov_ingestion import raw_sam_gov_entities

# The asset automatically handles:
# 1. S3-first path resolution
# 2. Local fallback
# 3. Parquet loading
# 4. Metadata generation

@asset
def enrich_with_sam_gov(raw_sam_gov_entities):
    """Downstream asset that uses SAM.gov data."""
    # raw_sam_gov_entities is a pandas DataFrame
    # with all SAM.gov entity records
    return enriched_data
```

### 3. API Client (Fallback)

```python
from src.enrichers.sam_gov import SAMGovAPIClient
import asyncio

async def lookup_entity():
    client = SAMGovAPIClient()

    # Get entity by UEI
    entity = await client.get_entity_by_uei("ABC123456789")  # pragma: allowlist secret

    # Get entity by CAGE
    entity = await client.get_entity_by_cage("1ABC5")

    # Search entities
    results = await client.search_entities(
        legal_business_name="Acme Corporation",
        limit=10
    )

    await client.aclose()

# Run async function
asyncio.run(lookup_entity())
```

## Data Schema

### Parquet File Structure

The SAM.gov parquet file contains 839,466 entity records with 368 columns. Key columns include:

| Column | Description | Example |
|--------|-------------|---------|
| `unique_entity_id` | UEI (Unique Entity Identifier) | ABC123456789 |
| `cage_code` | CAGE code | 1ABC5 |
| `legal_business_name` | Legal business name | Acme Corporation |
| `dba_name` | DBA (Doing Business As) name | Acme |
| `physical_address_*` | Physical address fields | 123 Main St, Washington, DC |
| `primary_naics` | Primary NAICS code | 541512 |
| `naics_code_string` | All NAICS codes (comma-separated) | 541512,541519 |

### S3 Path Pattern

```
s3://{bucket}/data/raw/sam_gov/sam_entity_records.parquet        # Current static file
s3://{bucket}/data/raw/sam_gov/sam_entity_records_YYYYMMDD.parquet  # Future dated files
```

The `find_latest_sam_gov_parquet()` utility automatically finds the most recent file.

## S3 Integration

### Environment Variables

```bash
# S3 bucket for data storage
export SBIR_ETL__S3_BUCKET="your-bucket-name"
# or
export S3_BUCKET="your-bucket-name"

# AWS credentials (required for S3 access)
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"  # pragma: allowlist secret
export AWS_DEFAULT_REGION="us-east-1"
```

### S3 Path Resolution

The `resolve_data_path()` utility provides:

1. **S3 detection**: Recognizes `s3://` URLs
2. **Download caching**: Downloads S3 files to temp cache
3. **Local fallback**: Falls back to local path if S3 unavailable
4. **Prefer local**: Option to prefer local even if S3 available

```python
from src.utils.cloud_storage import resolve_data_path

# Resolve path with S3-first strategy
path = resolve_data_path(
    cloud_path="s3://bucket/data/raw/sam_gov/sam_entity_records.parquet",
    local_fallback=Path("data/raw/sam_gov/sam_entity_records.parquet"),
    prefer_local=False  # Try S3 first
)
```

## Differences from USAspending Integration

| Aspect | USAspending | SAM.gov |
|--------|-------------|---------|
| **Data Format** | PostgreSQL dump (.zip) | Parquet (.parquet) |
| **Import Method** | DuckDB postgres_scanner | pd.read_parquet() |
| **Complexity** | Complex (DB import required) | Simple (direct read) |
| **File Type** | Dated archives | Static + dated pattern support |
| **Primary Key** | Multiple table PKs | unique_entity_id (UEI) |
| **API Fallback** | Implemented for some tables | Available but not for bulk data |

## Performance Characteristics

### Parquet Loading

- **File Size**: ~500MB (compressed parquet)
- **Load Time**: ~5-10 seconds for full dataset
- **Memory Usage**: ~2GB for full dataset in memory
- **Records**: 839,466 entity records

### S3 Performance

- **Download Time**: ~1-2 minutes (first time)
- **Cache Hit**: ~5-10 seconds (subsequent loads)
- **Cache Location**: `/tmp/sbir-analytics-s3-cache/`

## Testing

### Unit Tests

```bash
# Test extractor
pytest tests/unit/extractors/test_sam_gov_extractor.py -v

# Test asset
pytest tests/unit/assets/test_sam_gov_ingestion.py -v
```

### Integration Tests

```bash
# Test full pipeline
pytest tests/integration/test_sam_gov_integration.py -v
```

### Test Coverage

- ✅ Extractor initialization
- ✅ Parquet loading (local and S3)
- ✅ Entity lookups (UEI, CAGE, DUNS)
- ✅ Dagster asset execution
- ✅ S3 path resolution
- ✅ Error handling (file not found, S3 unavailable)
- ✅ Metadata generation

## Future Enhancements

### Planned

1. **Incremental Updates**: Support for incremental parquet file updates
2. **Partitioned Parquet**: Split large file into partitions for faster loading
3. **DuckDB Integration**: Optional DuckDB import for SQL queries
4. **API Bulk Fallback**: Implement bulk API fetching if parquet unavailable

### Under Consideration

1. **Change Detection**: Track changes in entity records over time
2. **Entity Deduplication**: Merge duplicate entities across sources
3. **Historical Data**: Archive historical SAM.gov snapshots
4. **Real-time Updates**: Subscribe to SAM.gov API updates

## Troubleshooting

### Common Issues

#### 1. File Not Found

```
FileNotFoundError: SAM.gov parquet file not found
```

**Solution**: Ensure parquet file exists at configured path, or configure S3 access.

#### 2. S3 Access Denied

```
botocore.exceptions.NoCredentialsError
```

**Solution**: Set AWS credentials in environment variables.

#### 3. Memory Issues

```
MemoryError: Unable to allocate array
```

**Solution**: Reduce `batch_size` in configuration or use DuckDB for queries.

## References

- [SAM.gov Entity Information API](https://open.gsa.gov/api/entity-api/)
- [USAspending Cloud Integration](USASPENDING_CLOUD_INTEGRATION.md)
- [Cloud Storage Utilities](../src/utils/cloud_storage.py)
- [Configuration Schema](../src/config/schemas/data_pipeline.py)

## Changelog

### 2025-01-21 - Initial Implementation

- ✅ Created SAMGovExtractor class
- ✅ Implemented Dagster asset for bulk ingestion
- ✅ Added S3 path resolution utilities
- ✅ Created SAMGovAPIClient for fallback
- ✅ Added configuration schema
- ✅ Comprehensive unit and integration tests
- ✅ Documentation and examples


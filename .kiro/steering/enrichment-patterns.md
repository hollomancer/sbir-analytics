# Data Enrichment Patterns

## Hierarchical Enrichment Strategy

The system implements a multi-source enrichment strategy with documented fallback chains to maximize data coverage.

## Enrichment Architecture

```
Primary Source (Highest Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Secondary Source (Good Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Tertiary Source (Acceptable Quality)
    ↓ Success? → Continue
    ↓ Fail? → Fallback
Rule-Based Default (Lowest Quality)
    ↓
Log Enrichment Path & Confidence Score
```

## NAICS Code Enrichment Example

### 9-Step Enrichment Workflow

1. **Original SBIR data** (confidence: 0.95) - Use if valid
2. **USAspending.gov API** (confidence: 0.90) - Match by UEI/contract ID
3. **SAM.gov API** (confidence: 0.85) - Match by company DUNS/UEI
4. **Fuzzy name matching** (confidence: 0.65-0.80) - Company name similarity
5. **Proximity filtering** (confidence: varies) - Geographic validation
6. **Agency defaults** (confidence: 0.50) - DOD → manufacturing, NIH → biotech
7. **Sector fallback** (confidence: 0.30) - Default to "5415" R&D services

### Agency Default Mappings
```yaml
agency_defaults:
  DOD: "3364"    # Aerospace manufacturing
  HHS: "5417"    # Biotechnology R&D
  DOE: "5417"    # Energy R&D
  NASA: "5417"   # Space R&D
```

## Enrichment Confidence Scoring

### Confidence Levels
- **High Confidence** (≥0.80): Exact matches, API lookups
- **Medium Confidence** (0.60-0.79): Fuzzy matches, validated proximity
- **Low Confidence** (<0.60): Agency defaults, sector fallbacks

### Confidence Thresholds
```yaml
confidence_thresholds:
  high: 0.80
  medium: 0.60
  low: 0.40
```

## Source Tracking and Auditability

### Enrichment Metadata
Every enriched field includes:
- Source of enrichment (e.g., "usaspending_api", "sam_gov_api", "fuzzy_match")
- Confidence score (0.0-1.0)
- Enrichment timestamp
- Method-specific metadata (similarity scores, API response details)

### Enrichment Result Structure
```python
@dataclass
class EnrichmentResult:
    field_name: str
    enriched_value: Any
    original_value: Any
    confidence: float
    source: EnrichmentSource
    metadata: dict
    timestamp: datetime
```

## Rate Limiting and API Management

### Rate Limiting
- Configurable rate limits per API source
- Exponential backoff for transient failures
- Batch processing where supported by APIs
- Request throttling to stay within limits

### Retry Logic
- Transient error detection (503, timeout)
- Exponential backoff strategy
- Maximum retry attempts per source
- Fallback to next source after max retries

## Batch Processing

### Batch Configuration
```yaml
enrichment:
  batch_size: 100              # Records per API call
  max_retries: 3               # Retry attempts
  timeout_seconds: 30          # Request timeout
  rate_limit_per_second: 10.0  # API rate limit
```

### Batch Optimization
- Group records by enrichment source
- Single API calls for multiple records
- Configurable batch sizes per source
- Progress tracking for long-running batches

## Performance Monitoring

### Success Rate Tracking
- Enrichment success rate by source
- Coverage metrics (% of records enriched)
- Confidence score distributions
- Historical trend analysis

### Performance Metrics
- Execution time per enrichment source
- Memory usage during enrichment
- Throughput (records/second)
- API response times and error rates

## Quality Gates

### Enrichment Quality Thresholds
```yaml
enrichment_quality:
  min_success_rate: 0.90       # 90% enrichment target
  min_high_confidence: 0.75    # 75% high confidence target
  max_fallback_rate: 0.20      # Max 20% fallbacks
```

### Quality Validation
- Asset checks enforce enrichment success rates
- Block downstream processing on quality failures
- Alert on enrichment quality regressions
- Manual review workflows for low-confidence enrichments

## Configuration-Driven Enrichment

### Enrichment Source Configuration
```yaml
enrichment:
  sources:
    usaspending:
      enabled: true
      priority: 1
      confidence: 0.90
      rate_limit: 100
    sam_gov:
      enabled: true
      priority: 2
      confidence: 0.85
      api_key_env: "SAM_GOV_API_KEY"
    fuzzy_match:
      enabled: true
      priority: 3
      similarity_threshold: 0.80
      confidence_base: 0.70
```

### Fallback Rules
```yaml
fallback_rules:
  enable_agency_defaults: true
  enable_sector_fallback: true
  sector_fallback_code: "5415"
```

## Evidence-Based Enrichment

### Supporting Evidence
Each enrichment decision includes supporting evidence:
- Match method (exact, fuzzy, proximity)
- Similarity scores for fuzzy matches
- API response metadata
- Validation checks performed

### Manual Review Support
- Low-confidence enrichments flagged for review
- Evidence presented for manual validation
- Accept/reject workflows for questionable matches
- Audit trail of manual decisions
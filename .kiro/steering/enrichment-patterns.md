# Data Enrichment Patterns

## Overview

The system implements a multi-source enrichment strategy with documented fallback chains to maximize data coverage. This document focuses on the hierarchical enrichment strategy, confidence scoring, and evidence tracking patterns.

## Core Concepts

### Hierarchical Enrichment Strategy

```text
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

### Confidence Scoring

| Level | Range | Sources | Use Case |
|-------|-------|---------|----------|
| **High** | ≥0.80 | Exact matches, API lookups | Production ready |
| **Medium** | 0.60-0.79 | Fuzzy matches, validated proximity | Review recommended |
| **Low** | <0.60 | Agency defaults, sector fallbacks | Manual review required |

## Implementation Patterns

### NAICS Code Enrichment Example

### 9-Step Enrichment Workflow

1. **Original SBIR data** (confidence: 0.95) - Use if valid
2. **USAspending.gov API** (confidence: 0.90) - Match by UEI/contract ID
3. **SAM.gov API** (confidence: 0.85) - Match by company DUNS/UEI
4. **Fuzzy name matching** (confidence: 0.65-0.80) - Company name similarity
5. **Proximity filtering** (confidence: varies) - Geographic validation
6. **Agency defaults** (confidence: 0.50) - DOD → manufacturing, NIH → biotech
7. **Sector fallback** (confidence: 0.30) - Default to "5415" R&D services

### Source Tracking and Auditability

**Enrichment Metadata** - Every enriched field includes:

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

### Rate Limiting and API Management

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

### Evidence-Based Enrichment

**Supporting Evidence** - Each enrichment decision includes:

- Match method (exact, fuzzy, proximity)
- Similarity scores for fuzzy matches
- API response metadata
- Validation checks performed

### Manual Review Support

- Low-confidence enrichments flagged for review
- Evidence presented for manual validation
- Accept/reject workflows for questionable matches
- Audit trail of manual decisions

## Configuration

Enrichment sources, fallback rules, and quality thresholds are configured in YAML. See **[configuration-patterns.md](configuration-patterns.md)** for complete configuration examples including:

- Enrichment source configuration with priorities
- Batch processing settings
- Confidence thresholds
- Quality gates and success rate targets
- Agency default mappings
- Fallback rules

## Best Practices

### Enrichment Strategy Design

- **Hierarchical fallback**: Order sources by quality and confidence
- **Confidence scoring**: Transparent scoring for all enrichment decisions
- **Evidence tracking**: Maintain audit trail for all enrichment decisions
- **Quality gates**: Enforce minimum success rates and confidence levels

### API Management

- **Rate limiting**: Respect API limits and implement backoff strategies
- **Batch processing**: Optimize API usage with batching where possible
- **Error handling**: Graceful degradation with fallback sources
- **Monitoring**: Track API performance and success rates

## Related Documents

- **[configuration-patterns.md](configuration-patterns.md)** - Complete enrichment configuration examples
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Performance monitoring and asset integration
- **[data-quality.md](data-quality.md)** - Quality validation for enriched data
- **[quick-reference.md](quick-reference.md)** - Confidence levels and configuration quick lookup

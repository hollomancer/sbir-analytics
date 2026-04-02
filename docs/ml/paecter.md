# Embedding Model Integration Guide (ModernBERT-Embed)

## Overview

ModernBERT-Embed (`nomic-ai/modernbert-embed-base`) is a general-purpose embedding model built on the ModernBERT architecture. It generates 768-dimensional dense vector embeddings with an 8192-token context window, rotary positional embeddings, and Flash Attention for efficient long-document encoding.

This guide covers the integration of ModernBERT-Embed into the SBIR analytics pipeline for computing semantic similarity between SBIR awards and USPTO patents.

## Key Features

- **Dual Inference Modes**: API-based (HuggingFace) or local (sentence-transformers)
- **Long Context**: 8192-token context window (vs 512 for many older models)
- **Batch Processing**: Efficient processing of large datasets
- **Caching Support**: Optional caching to reduce redundant computations
- **Quality Gates**: Asset checks enforce embedding coverage thresholds
- **Dagster Integration**: Three core assets for embeddings and similarity computation

## Architecture

### Components

```text
┌─────────────────────────────────────────────────────────────┐
│                 Embedding Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  validated_sbir_awards ──┐                                 │
│                          │                                  │
│                          ├──> paecter_embeddings_awards     │
│                          │         (768-dim vectors)        │
│                          │                                  │
│  transformed_patents ────┼──> paecter_embeddings_patents   │
│                          │         (768-dim vectors)        │
│                          │                                  │
│                          └──> paecter_award_patent_similarity│
│                                    (cosine similarity)       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Dagster Assets

1. **`paecter_embeddings_awards`**
   - Generates embeddings for SBIR awards
   - Input: `validated_sbir_awards` DataFrame
   - Output: DataFrame with `award_id`, `embedding`, metadata
   - Text fields: solicitation_title, award_title, abstract

2. **`paecter_embeddings_patents`**
   - Generates embeddings for USPTO patents
   - Input: `transformed_patents` metadata (loads from JSONL or S3)
   - Output: DataFrame with `patent_id`, `embedding`, metadata
   - Text fields: title, abstract

3. **`paecter_award_patent_similarity`**
   - Computes cosine similarity between awards and patents
   - Input: Both embedding DataFrames
   - Output: DataFrame with `award_id`, `patent_id`, `similarity_score`
   - Filters: Top-10 matches per award, threshold-based filtering

## Configuration

### Basic Configuration

Embedding configuration is located in `config/base.yaml` under the `ml.paecter` section:

```yaml
ml:
  paecter:
    # Inference mode
    use_local: false  # false = API mode, true = local mode

    # API configuration (when use_local=false)
    api:
      token_env: "HF_TOKEN"
      batch_size: 32
      max_qps: 10
      timeout_seconds: 60
      max_retries: 5
      retry_backoff_seconds: 2.0

    # Local configuration (when use_local=true)
    local:
      model_name: "nomic-ai/modernbert-embed-base"
      device: "auto"  # "auto", "cpu", or "cuda"
      batch_size: 32

    # Similarity computation
    similarity_threshold: 0.80  # Minimum score to include
    top_k: 10  # Top matches per award

    # Quality thresholds
    coverage_threshold_awards: 0.95
    coverage_threshold_patents: 0.98
```

### Environment Variables

Override configuration using environment variables:

```bash
# Use local mode instead of API
export SBIR_ETL__ML__PAECTER__USE_LOCAL=true

# Adjust batch size
export SBIR_ETL__ML__PAECTER__API__BATCH_SIZE=64

# Change similarity threshold
export SBIR_ETL__ML__PAECTER__SIMILARITY_THRESHOLD=0.85

# Set HuggingFace token for API mode
export HF_TOKEN="your_huggingface_token"
```

## Usage

### Running via Dagster UI

1. Navigate to the Dagster UI (<http://localhost:3000>)
2. Go to **Assets** → **paecter** group
3. Select the assets you want to materialize:
   - `paecter_embeddings_awards`
   - `paecter_embeddings_patents`
   - `paecter_award_patent_similarity`
4. Click **Materialize**

### Running via CLI

```bash
# Materialize all embedding assets
dagster asset materialize -m sbir_etl.definitions --select "paecter*"

# Materialize specific asset
dagster asset materialize -m sbir_etl.definitions --select paecter_embeddings_awards

# Run the complete embedding job
dagster job execute -m sbir_etl.definitions -j paecter_job
```

### Programmatic Usage

```python
from sbir_ml.ml.paecter_client import PaECTERClient
from sbir_ml.ml.config import PaECTERClientConfig

# Initialize client (API mode)
client = PaECTERClient(config=PaECTERClientConfig(use_local=False))

# Prepare texts
award_texts = [
    client.prepare_award_text(
        solicitation_title="Advanced Manufacturing",
        abstract="Development of novel 3D printing methods..."
    )
]

patent_texts = [
    client.prepare_patent_text(
        title="Novel Solar Cell Design",
        abstract="This invention relates to improved solar cells..."
    )
]

# Generate embeddings
award_result = client.generate_embeddings(award_texts, batch_size=32)
patent_result = client.generate_embeddings(patent_texts, batch_size=32)

# Compute similarity
similarities = client.compute_similarity(
    award_result.embeddings,
    patent_result.embeddings
)

print(f"Similarity score: {similarities[0, 0]:.3f}")
```

## Inference Modes

### API Mode (Default)

**Advantages:**

- No local model download required
- No GPU needed
- Lower memory footprint
- Automatic model updates

**Requirements:**

- HuggingFace API token (set `HF_TOKEN` environment variable)
- Internet connectivity
- Respects rate limits (configurable)

**Configuration:**

```yaml
ml:
  paecter:
    use_local: false
    api:
      token_env: "HF_TOKEN"
      batch_size: 32
      max_qps: 10
```

### Local Mode

**Advantages:**

- No API rate limits
- Works offline
- Potentially faster for large batches
- No API token required

**Requirements:**

- Install sentence-transformers: `pip install sentence-transformers`
- ~1GB disk space for model download
- GPU recommended but not required

**Configuration:**

```yaml
ml:
  paecter:
    use_local: true
    local:
      model_name: "nomic-ai/modernbert-embed-base"
      device: "auto"  # or "cuda" for GPU
      batch_size: 32
```

## Quality Assurance

### Asset Checks

Two asset checks enforce quality thresholds:

1. **`paecter_awards_coverage_check`**
   - Validates that >=95% of awards have valid embeddings
   - Checks embedding dimension (768)
   - Severity: ERROR if threshold not met

2. **`paecter_patents_coverage_check`**
   - Validates that >=98% of patents have valid embeddings
   - Checks embedding dimension (768)
   - Severity: ERROR if threshold not met

### Monitoring

The pipeline includes performance monitoring:

```python
# Automatic monitoring in assets
with performance_monitor.monitor_block("paecter_generate_award_embeddings"):
    result = client.generate_embeddings(texts, batch_size=batch_size)
```

Metrics tracked:

- Generation time (seconds)
- Throughput (embeddings/second)
- Batch processing efficiency
- Memory usage

## Output Schema

### Award Embeddings

```python
{
    "award_id": str,           # Award identifier
    "embedding": List[float],  # 768-dimensional vector
    "model_version": str,      # "nomic-ai/modernbert-embed-base"
    "inference_mode": str,     # "api" or "local"
    "dimension": int           # 768
}
```

### Patent Embeddings

```python
{
    "patent_id": str,          # Patent identifier
    "embedding": List[float],  # 768-dimensional vector
    "model_version": str,      # "nomic-ai/modernbert-embed-base"
    "inference_mode": str,     # "api" or "local"
    "dimension": int           # 768
}
```

### Similarity Scores

```python
{
    "award_id": str,           # Award identifier
    "patent_id": str,          # Patent identifier
    "similarity_score": float  # Cosine similarity [0.0, 1.0]
}
```

## Migration from PaECTER

This pipeline previously used PaECTER (`mpi-inno-comp/paecter`, 1024-dim). Key differences with ModernBERT-Embed:

| Property | PaECTER | ModernBERT-Embed |
|----------|---------|------------------|
| Dimensions | 1024 | 768 |
| Max tokens | 512 | 8192 |
| Architecture | BERT-based | ModernBERT (RoPE, Flash Attention) |
| Domain | Patent-specific | General-purpose |
| Model size | ~500MB | ~400MB |

**Important:** Existing embeddings generated with PaECTER are **not compatible** with ModernBERT-Embed embeddings. All embeddings must be regenerated after switching models.

## Performance Considerations

### Batch Size

- **API mode**: 32 (default) - balances throughput and rate limits
- **Local mode**: 32-64 - depends on available memory and GPU

### Memory Usage

- **API mode**: ~100MB (minimal, no model in memory)
- **Local mode**: ~1.5GB (model loaded in memory)

### Processing Time

Approximate times for 10,000 documents:

- **API mode**: 10-20 minutes (depends on rate limits)
- **Local mode (CPU)**: 5-10 minutes
- **Local mode (GPU)**: 1-2 minutes

### Optimization Tips

1. **Use caching** for repeated computations:

   ```python
   config = PaECTERClientConfig(use_local=False, enable_cache=True)
   ```

2. **Increase batch size** for local mode with GPU:

   ```yaml
   ml:
     paecter:
       local:
         batch_size: 64
   ```

3. **Adjust rate limits** for API mode:

   ```yaml
   ml:
     paecter:
       api:
         max_qps: 20  # Increase if you have higher tier
   ```

## Troubleshooting

### Common Issues

#### API Mode: Rate Limit Errors

**Symptom:** `429 Too Many Requests` errors

**Solution:**

```yaml
ml:
  paecter:
    api:
      max_qps: 5  # Reduce queries per second
      max_retries: 10  # Increase retries
      retry_backoff_seconds: 5.0  # Longer backoff
```

#### Local Mode: Out of Memory

**Symptom:** `RuntimeError: CUDA out of memory`

**Solution:**

```yaml
ml:
  paecter:
    local:
      batch_size: 16  # Reduce batch size
      device: "cpu"   # Use CPU instead of GPU
```

#### Missing HuggingFace Token

**Symptom:** `No HuggingFace token provided` warning

**Solution:**

```bash
export HF_TOKEN="your_token_here"
```

Get a token from: <https://huggingface.co/settings/tokens>

#### Low Coverage Check Failures

**Symptom:** Asset check fails with low coverage percentage

**Possible causes:**

- Missing text fields (title, abstract)
- Empty or null text values
- Text preprocessing issues

**Solution:**

- Check input data quality
- Verify text field names match configuration
- Review logs for specific failures

## References

- **Model Card**: <https://huggingface.co/nomic-ai/modernbert-embed-base>
- **ModernBERT Paper**: <https://arxiv.org/abs/2412.13663>
- **Implementation**: `packages/sbir-ml/sbir_ml/ml/paecter_client.py`
- **Assets**: `packages/sbir-analytics/sbir_analytics/assets/paecter/embeddings.py`
- **Configuration**: `config/base.yaml` (ml.paecter section)

## Related Documentation

- [CET Classification](cet-integration.md) - Technology classification system
- [Transition Detection](../transition/) - Technology transition detection
- [ML Documentation Index](README.md) - Machine learning overview
- [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) - Configuration guide

---

**Last Updated:** 2026-04-02
**Status:** Active - Migrated from PaECTER to ModernBERT-Embed

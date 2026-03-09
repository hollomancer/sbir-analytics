# SPECTER2 Integration Guide

## Overview

SPECTER2 (Scientific Paper Embeddings using Citation-informed TransformERs v2) is a document embedding model developed by the Allen Institute for AI. It generates 768-dimensional dense vector embeddings optimized for scientific document similarity tasks, including patents.

This guide covers the integration of SPECTER2 into the SBIR analytics pipeline for computing semantic similarity between SBIR awards and USPTO patents.

## Key Features

- **Dual Inference Modes**: API-based (HuggingFace) or local (sentence-transformers)
- **Batch Processing**: Efficient processing of large datasets
- **Caching Support**: Optional caching to reduce redundant computations
- **Quality Gates**: Asset checks enforce embedding coverage thresholds
- **Dagster Integration**: Three core assets for embeddings and similarity computation

## Architecture

### Components

```text
┌─────────────────────────────────────────────────────────────┐
│                    SPECTER2 Pipeline                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  validated_sbir_awards ──┐                                 │
│                          │                                  │
│                          ├──> specter2_embeddings_awards     │
│                          │         (768-dim vectors)         │
│                          │                                  │
│  transformed_patents ────┼──> specter2_embeddings_patents   │
│                          │         (768-dim vectors)         │
│                          │                                  │
│                          └──> specter2_award_patent_similarity│
│                                    (cosine similarity)       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Dagster Assets

1. **`specter2_embeddings_awards`**
   - Generates embeddings for SBIR awards
   - Input: `validated_sbir_awards` DataFrame
   - Output: DataFrame with `award_id`, `embedding`, metadata
   - Text fields: solicitation_title, award_title, abstract

2. **`specter2_embeddings_patents`**
   - Generates embeddings for USPTO patents
   - Input: `transformed_patents` metadata (loads from JSONL or S3)
   - Output: DataFrame with `patent_id`, `embedding`, metadata
   - Text fields: title, abstract

3. **`specter2_award_patent_similarity`**
   - Computes cosine similarity between awards and patents
   - Input: Both embedding DataFrames
   - Output: DataFrame with `award_id`, `patent_id`, `similarity_score`
   - Filters: Top-10 matches per award, threshold-based filtering

## Configuration

### Basic Configuration

SPECTER2 configuration is located in `config/base.yaml` under the `ml.specter2` section:

```yaml
ml:
  specter2:
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
      model_name: "allenai/specter2"
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
export SBIR_ETL__ML__SPECTER2__USE_LOCAL=true

# Adjust batch size
export SBIR_ETL__ML__SPECTER2__API__BATCH_SIZE=64

# Change similarity threshold
export SBIR_ETL__ML__SPECTER2__SIMILARITY_THRESHOLD=0.85

# Set HuggingFace token for API mode
export HF_TOKEN="your_huggingface_token"
```

## Usage

### Running via Dagster UI

1. Navigate to the Dagster UI (<http://localhost:3000>)
2. Go to **Assets** -> **specter2** group
3. Select the assets you want to materialize:
   - `specter2_embeddings_awards`
   - `specter2_embeddings_patents`
   - `specter2_award_patent_similarity`
4. Click **Materialize**

### Running via CLI

```bash
# Materialize all SPECTER2 assets
dagster asset materialize -m src.definitions --select "specter2*"

# Materialize specific asset
dagster asset materialize -m src.definitions --select specter2_embeddings_awards

# Run the complete SPECTER2 job
dagster job execute -m src.definitions -j specter2_job
```

### Programmatic Usage

```python
from src.ml.specter2_client import Specter2Client
from src.ml.config import Specter2ClientConfig

# Initialize client (API mode)
client = Specter2Client(config=Specter2ClientConfig(use_local=False))

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
  specter2:
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
  specter2:
    use_local: true
    local:
      model_name: "allenai/specter2"
      device: "auto"  # or "cuda" for GPU
      batch_size: 32
```

## Quality Assurance

### Asset Checks

Two asset checks enforce quality thresholds:

1. **`specter2_awards_coverage_check`**
   - Validates that >=95% of awards have valid embeddings
   - Checks embedding dimension (768)
   - Severity: ERROR if threshold not met

2. **`specter2_patents_coverage_check`**
   - Validates that >=98% of patents have valid embeddings
   - Checks embedding dimension (768)
   - Severity: ERROR if threshold not met

### Monitoring

The pipeline includes performance monitoring:

```python
# Automatic monitoring in assets
with performance_monitor.monitor_block("specter2_generate_award_embeddings"):
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
    "model_version": str,      # "allenai/specter2"
    "inference_mode": str,     # "api" or "local"
    "dimension": int           # 768
}
```

### Patent Embeddings

```python
{
    "patent_id": str,          # Patent identifier
    "embedding": List[float],  # 768-dimensional vector
    "model_version": str,      # "allenai/specter2"
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

## Troubleshooting

### Common Issues

#### API Mode: Rate Limit Errors

**Symptom:** `429 Too Many Requests` errors

**Solution:**

```yaml
ml:
  specter2:
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
  specter2:
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

## References

- **Model Card**: <https://huggingface.co/allenai/specter2>
- **Research Paper**: <https://arxiv.org/abs/2211.13228>
- **Implementation**: `src/ml/specter2_client.py`
- **Assets**: `src/assets/specter2/embeddings.py`
- **Configuration**: `config/base.yaml` (ml.specter2 section)

## Related Documentation

- [CET Classification](cet-integration.md) - Technology classification system
- [Transition Detection](../transition/) - Technology transition detection
- [ML Documentation Index](README.md) - Machine learning overview
- [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) - Configuration guide

---

**Last Updated:** 2026-03-09
**Status:** Active - Migrated from PaECTER to SPECTER2

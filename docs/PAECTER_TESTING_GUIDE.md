# PaECTER Testing Guide

This guide explains how to test the PaECTER (Patent Embeddings using Citation-informed TransformERs) integration with your SBIR-ETL data.

## Overview

PaECTER is a patent-specific embedding model from HuggingFace (`mpi-inno-comp/paecter`) that generates 1024-dimensional dense vector embeddings optimized for patent similarity tasks. This implementation allows you to:

1. Generate semantic embeddings for SBIR awards and patents
2. Compute similarity scores between awards and patents
3. Identify technology transfer relationships
4. Discover related innovations across your data

## Two Modes of Operation

The PaECTER client supports two modes:

**API Mode (Default - Recommended)**
- Uses HuggingFace Inference API
- No model download required (~500MB saved)
- No local GPU/CPU compute needed
- Perfect for Dagster Cloud deployment
- Requires HuggingFace API token (free tier available)

**Local Mode (Optional)**
- Downloads and runs model locally
- Requires ~500MB disk space + ~1.5GB RAM
- Useful for offline work or high-volume batch processing
- Requires PyTorch and sentence-transformers

## Quick Start

### 1. Install Dependencies

**For API Mode (Default - Recommended):**
```bash
# Already included in base dependencies!
# huggingface-hub is installed automatically
```

**For Local Mode (Optional):**
```bash
# Install local model dependencies
uv pip install -e ".[paecter-local]"

# Or install manually
pip install sentence-transformers torch transformers
```

### 2. Set Up HuggingFace Token (API Mode)

Get a free token from [HuggingFace](https://huggingface.co/settings/tokens):

```bash
# Set environment variable
export HF_TOKEN="your_token_here"

# Or add to your .env file
echo "HF_TOKEN=your_token_here" >> .env
```

### 3. Run Quick Test

```bash
# API mode (default - requires HF_TOKEN)
export HF_TOKEN="your_token_here"
python scripts/test_paecter_quick.py

# Local mode (requires sentence-transformers)
python scripts/test_paecter_quick.py --local
```

### 4. Run Integration Tests

```bash
# Local mode tests (default - requires sentence-transformers)
pytest tests/integration/test_paecter_client.py -v

# API mode tests (requires HF_TOKEN)
export HF_TOKEN="your_token_here"
export USE_PAECTER_API=1
pytest tests/integration/test_paecter_client.py -v
```

### 5. Quick Examples

**API Mode (Default):**
```python
import os
from src.ml.paecter_client import PaECTERClient

# Set token (or use environment variable)
os.environ["HF_TOKEN"] = "your_token_here"

# Initialize client (uses API by default)
client = PaECTERClient()
# or explicitly: client = PaECTERClient(use_local=False)

# Prepare texts
award_text = client.prepare_award_text(
    solicitation_title="Advanced Manufacturing Technologies",
    abstract="This project develops novel 3D printing methods...",
    award_title="Innovative Additive Manufacturing"
)

# Generate embeddings via API (no model download!)
result = client.generate_embeddings([award_text])
print(f"Embedding shape: {result.embeddings.shape}")  # (1, 1024)
print(f"Mode: {result.inference_mode}")  # "api"
```

**Local Mode (Optional):**
```python
from src.ml.paecter_client import PaECTERClient

# Initialize client in local mode
client = PaECTERClient(use_local=True)

# Same API as above, but runs locally
result = client.generate_embeddings([award_text])
print(f"Mode: {result.inference_mode}")  # "local"
```

## Testing Approach: Simple to Complex

### Phase 1: Basic Functionality (CURRENT)

**Status:** ✅ Implemented

**What's included:**
- Basic PaECTER client (`src/ml/paecter_client.py`)
- Integration tests with sample data (`tests/integration/test_paecter_client.py`)
- Text preparation utilities for awards and patents
- Similarity computation
- Sample award and patent data in tests

**How to test:**
```bash
# Run all PaECTER tests
uv run pytest tests/integration/test_paecter_client.py -v

# Run specific test
uv run pytest tests/integration/test_paecter_client.py::TestPaECTERClient::test_award_patent_similarity -v -s
```

**Expected results:**
- Model loads successfully (1024-dimensional embeddings)
- Embeddings are unit-normalized
- Similar content gets higher similarity scores
- Award-patent matching shows sensible results

### Phase 2: Real Data Integration (NEXT STEP)

**Status:** 🔄 Ready to implement

**Objectives:**
- Test with real SBIR award data from your database
- Test with real USPTO patent data
- Generate embeddings for a sample dataset
- Save embeddings to Parquet files
- Evaluate quality on known similar pairs

**Implementation steps:**

1. Create test script for real data:

```python
# tests/integration/test_paecter_real_data.py
import pytest
import pandas as pd
from src.ml.paecter_client import PaECTERClient

@pytest.mark.integration
@pytest.mark.real_data
@pytest.mark.slow
def test_real_sbir_awards():
    """Test embedding generation on real SBIR awards."""
    # Load sample of real awards
    awards_df = pd.read_csv("data/raw/sbir/award_data.csv", nrows=100)

    client = PaECTERClient()

    # Prepare texts
    texts = [
        client.prepare_award_text(
            row.get('solicitation_title'),
            row.get('abstract'),
            row.get('award_title')
        )
        for _, row in awards_df.iterrows()
    ]

    # Generate embeddings
    result = client.generate_embeddings(texts, batch_size=16, show_progress_bar=True)

    # Save to Parquet
    embeddings_df = pd.DataFrame({
        'award_id': awards_df['award_id'],
        'embedding': list(result.embeddings)
    })
    embeddings_df.to_parquet("data/processed/paecter_embeddings_awards_sample.parquet")

    assert result.embeddings.shape == (100, 1024)
```

2. Run the test:

```bash
uv run pytest tests/integration/test_paecter_real_data.py -v -s
```

### Phase 3: Quality Validation

**Status:** 📋 Planned

**Objectives:**
- Validate embedding quality using cohesion metrics
- Test that embeddings cluster well by CET category
- Compare with baseline methods (TF-IDF, etc.)
- Establish quality gates and thresholds

**Key metrics:**
- **Coverage:** % of records with valid embeddings (target: >95%)
- **Cohesion:** Within-CET-group similarity vs. across-group (target: ratio > 1.3)
- **Stability:** Embedding consistency across model versions
- **Performance:** Embeddings/second throughput

### Phase 4: Dagster Pipeline Integration

**Status:** 📋 Planned

**Objectives:**
- Create Dagster assets for embedding generation
- Implement incremental updates
- Add quality checks and validation gates
- Integrate with existing CET classification

**Dagster assets to create:**
```python
# src/assets/paecter/embeddings.py

@asset(group_name="paecter", compute_kind="ml")
def paecter_embeddings_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
) -> pd.DataFrame:
    """Generate PaECTER embeddings for SBIR awards."""
    client = PaECTERClient()

    texts = [
        client.prepare_award_text(
            row.solicitation_title,
            row.abstract,
            row.award_title
        )
        for _, row in validated_sbir_awards.iterrows()
    ]

    result = client.generate_embeddings(texts, batch_size=32, show_progress_bar=True)

    context.log.info(f"Generated {result.input_count} embeddings in {result.generation_timestamp:.2f}s")

    return pd.DataFrame({
        'award_id': validated_sbir_awards['award_id'],
        'embedding': list(result.embeddings),
        'model_version': result.model_version,
        'timestamp': result.generation_timestamp,
    })
```

### Phase 5: Similarity Pipeline

**Status:** 📋 Planned

**Objectives:**
- Compute award-patent similarities at scale
- Implement FAISS for fast approximate search
- Load similarity edges to Neo4j
- Create visualization and analytics

### Phase 6: Bayesian MoE Enhancement (Advanced)

**Status:** 📋 Future work

**Objectives:**
- Implement LoRA-based expert pool
- Add Bayesian routing (Classification → Similarity → Embedding)
- Implement uncertainty quantification
- Dynamic expert pool expansion

See `.kiro/specs/paecter_analysis_layer/` for detailed design.

## Testing Patterns

### Unit Tests

Focus on individual components:

```python
# Test text preparation
def test_prepare_patent_text():
    text = PaECTERClient.prepare_patent_text(
        title="Solar Cell",
        abstract="High efficiency photovoltaic..."
    )
    assert "Solar Cell" in text
    assert "High efficiency" in text
```

### Integration Tests

Test with real model and sample data:

```python
@pytest.mark.integration
@pytest.mark.slow
def test_generate_embeddings(paecter_client):
    texts = ["Sample patent text"]
    result = paecter_client.generate_embeddings(texts)
    assert result.embeddings.shape == (1, 1024)
```

### End-to-End Tests

Test full pipeline with real data:

```python
@pytest.mark.e2e
@pytest.mark.real_data
def test_award_patent_matching_pipeline():
    # Load real data
    # Generate embeddings
    # Compute similarities
    # Validate results
    # Save to Neo4j
    pass
```

## Performance Considerations

### Mode Comparison

**API Mode:**
- **Setup time:** Instant (no model download)
- **Memory:** Minimal (~100MB for client)
- **Throughput:** Depends on API rate limits
- **Cost:** Free tier available, paid tiers for higher volume
- **Best for:** Development, testing, Dagster Cloud deployment

**Local Mode:**
- **Setup time:** ~2-5 minutes (model download on first run)
- **Model download:** ~500MB (one-time)
- **Memory:** ~1.5GB when loaded
- **Throughput:** CPU ~10-50 embeddings/s, GPU ~200-1000+ embeddings/s
- **Cost:** Free (uses your compute)
- **Best for:** High-volume batch processing, offline work

### Scaling Strategies

1. **Small scale (< 1K records):**
   - **Recommended:** API mode
   - Batch size: 16-32
   - Simple and fast

2. **Medium scale (1K-100K records):**
   - **Recommended:** API mode for development, local mode for production
   - If local: Use GPU if available
   - Batch size: 32-64
   - Save embeddings to Parquet for reuse

3. **Large scale (> 100K records):**
   - **Recommended:** Local mode with GPU
   - Implement FAISS for similarity search
   - Use incremental updates
   - Consider batching across multiple runs
   - Or: Use HuggingFace Inference Endpoints for dedicated API capacity

### Caching

The model automatically caches to `~/.cache/huggingface/` (or `HF_HOME` if set). Embeddings should be saved to Parquet files to avoid recomputation.

## Troubleshooting

### API Mode Issues

**Error: huggingface_hub not found**
```bash
pip install huggingface-hub
```

**Error: Missing HF_TOKEN or rate limited**
```bash
# Get a free token from https://huggingface.co/settings/tokens
export HF_TOKEN="your_token_here"

# Or add to .env file
echo "HF_TOKEN=your_token_here" >> .env
```

**API calls timing out or failing**
- Check your internet connection
- Verify your HF_TOKEN is valid
- Try reducing batch size (API may have limits)
- Consider switching to local mode for high-volume work

### Local Mode Issues

**Error: sentence-transformers not found**
```bash
pip install sentence-transformers torch transformers
# Or: uv pip install -e ".[paecter-local]"
```

**Model download fails (403 Forbidden)**
The model is public and shouldn't require authentication. Try:
```bash
# Clear cache and retry
rm -rf ~/.cache/huggingface/hub/models--mpi-inno-comp--paecter
```

**CUDA out of memory**
Reduce batch size:
```python
client = PaECTERClient(use_local=True)
result = client.generate_embeddings(texts, batch_size=8)  # Reduce from 32
```

Or force CPU usage:
```python
client = PaECTERClient(use_local=True, device='cpu')
```

**Slow embedding generation (local mode)**

**Expected performance:**
- CPU: ~10-50 embeddings/second
- GPU (T4): ~200-500 embeddings/second
- GPU (A100): ~1000+ embeddings/second

If performance is significantly slower:
1. Check if GPU is being used (local mode only)
2. Increase batch size: `batch_size=64`
3. Consider switching to API mode for simpler deployment

## Sample Data Included

The test file includes sample data for quick testing:

**Sample Awards:**
1. 3D printing for aerospace (Advanced Manufacturing)
2. Deep learning for drug discovery (AI/ML)
3. Perovskite solar cells (Renewable Energy)

**Sample Patents:**
1. Additive manufacturing method
2. Neural network for molecular prediction
3. High-performance photovoltaic device

These are intentionally matched to demonstrate similarity scoring.

## Next Steps

1. **Get HuggingFace token:** Sign up at https://huggingface.co/settings/tokens (free)
2. **Set token:** `export HF_TOKEN="your_token_here"`
3. **Run quick test:** `python scripts/test_paecter_quick.py`
4. **Run integration tests:** `USE_PAECTER_API=1 pytest tests/integration/test_paecter_client.py -v`
5. **Test with your data:** Create `test_paecter_real_data.py` (see Phase 2 above)
6. **Evaluate quality:** Check similarity scores make sense for known similar pairs
7. **Scale up:** Move to Dagster pipeline integration (Phase 4)

**Optional:** For local mode testing, install `uv pip install -e ".[paecter-local]"` and run without HF_TOKEN.

## References

- **Model:** https://huggingface.co/mpi-inno-comp/paecter
- **Paper:** https://arxiv.org/pdf/2402.19411
- **Sentence Transformers:** https://www.sbert.net/
- **PaECTER Spec:** `.kiro/specs/paecter_analysis_layer/`

## Questions?

Common questions and their answers:

**Q: Which mode should I use - API or local?**
A:
- **Start with API mode** - it's simpler and works great for testing and development
- **Switch to local mode** for high-volume batch processing or offline work
- **Use API mode in Dagster Cloud** - no model download or GPU management needed

**Q: Do I need a GPU?**
A:
- **API mode:** No, everything runs on HuggingFace servers
- **Local mode:** No, but GPU is 10-50x faster for large batches

**Q: How much does the API cost?**
A: HuggingFace offers a free tier. For high volume, you can:
- Upgrade to paid tiers (check HuggingFace pricing)
- Use HuggingFace Inference Endpoints for dedicated capacity
- Switch to local mode with your own GPU

**Q: Can I use a different model?**
A: Yes! The `PaECTERClient` accepts any compatible model:
```python
# API mode - any HuggingFace model with feature-extraction
client = PaECTERClient(model_name="AI-Growth-Lab/PatentSBERTa")

# Local mode - any sentence-transformers model
client = PaECTERClient(use_local=True, model_name="AI-Growth-Lab/PatentSBERTa")
```

**Q: How do I integrate with existing CET classification?**
A: PaECTER embeddings can be used alongside CET classification. In fact, the Bayesian MoE design (Phase 6) combines them: Classification → Similarity → Embedding.

**Q: What's the difference between PaECTER and PatentSBERTa?**
A: PaECTER is fine-tuned with examiner citations and optimized for prior art search. PatentSBERTa is a more general patent BERT model. Both work with our client.

**Q: Can I run this in Dagster Cloud?**
A: Yes! **Use API mode** (default) - it's perfect for serverless deployment:
```python
# In your Dagster asset
client = PaECTERClient()  # Uses API mode by default
result = client.generate_embeddings(texts)
```
Just set `HF_TOKEN` in your Dagster Cloud environment variables.

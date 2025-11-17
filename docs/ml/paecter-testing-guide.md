# PaECTER Testing Guide

This guide explains how to test the PaECTER (Patent Embeddings using Citation-informed TransformERs) integration with your SBIR-ETL data.

## Overview

PaECTER is a patent-specific embedding model from HuggingFace (`mpi-inno-comp/paecter`) that generates 1024-dimensional dense vector embeddings optimized for patent similarity tasks. This implementation allows you to:

1. Generate semantic embeddings for SBIR awards and patents
2. Compute similarity scores between awards and patents
3. Identify technology transfer relationships
4. Discover related innovations across your data

## Quick Start

### 1. Install Dependencies

The PaECTER functionality requires additional optional dependencies:

```bash
# Install PaECTER dependencies
uv pip install -e ".[paecter]"

# Or install manually
uv pip install sentence-transformers torch transformers
```

**Note:** The first time you use PaECTER, it will download the model (~500MB) from HuggingFace. This happens automatically and is cached for future use.

### 2. Run Basic Tests

```bash
# Run PaECTER integration tests
uv run pytest tests/integration/test_paecter_client.py -v

# Run with output showing similarity scores
uv run pytest tests/integration/test_paecter_client.py::TestPaECTERClient::test_award_patent_similarity -v -s
```

### 3. Quick Example

```python
from src.ml.paecter_client import PaECTERClient

# Initialize client
client = PaECTERClient()

# Prepare texts
award_text = client.prepare_award_text(
    solicitation_title="Advanced Manufacturing Technologies",
    abstract="This project develops novel 3D printing methods...",
    award_title="Innovative Additive Manufacturing"
)

patent_text = client.prepare_patent_text(
    title="Method for Additive Manufacturing",
    abstract="A system for layer-by-layer metal deposition..."
)

# Generate embeddings
award_emb = client.generate_embeddings([award_text])
patent_emb = client.generate_embeddings([patent_text])

# Compute similarity
similarity = client.compute_similarity(award_emb.embeddings, patent_emb.embeddings)
print(f"Similarity score: {similarity[0, 0]:.3f}")
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

### Model Size and Memory

- **Model download:** ~500MB (first run only)
- **Model in memory:** ~1.5GB
- **Batch processing:** Recommended batch size 16-32
- **CPU vs GPU:** GPU ~10-50x faster for large batches

### Scaling Strategies

1. **Small scale (< 10K records):**
   - Use CPU
   - Single process
   - Batch size: 16

2. **Medium scale (10K-100K records):**
   - Use GPU if available
   - Batch size: 32-64
   - Save embeddings to Parquet for reuse

3. **Large scale (> 100K records):**
   - Use GPU
   - Implement FAISS for similarity search
   - Use incremental updates
   - Consider batching across multiple runs

### Caching

The model automatically caches to `~/.cache/huggingface/` (or `HF_HOME` if set). Embeddings should be saved to Parquet files to avoid recomputation.

## Troubleshooting

### Import Error: sentence-transformers not found

```bash
uv pip install sentence-transformers
```

### Model download fails (403 Forbidden)

This can happen if HuggingFace is blocking the request. Try:

```bash
# Set HuggingFace token (if you have one)
export HF_TOKEN="your_token_here"

# Or try from Python
from huggingface_hub import login
login(token="your_token_here")
```

However, `mpi-inno-comp/paecter` is a public model and should not require authentication.

### CUDA out of memory

Reduce batch size:

```python
result = client.generate_embeddings(texts, batch_size=8)  # Reduce from 32
```

Or force CPU usage:

```python
client = PaECTERClient(device='cpu')
```

### Slow embedding generation

**Expected performance:**
- CPU: ~10-50 embeddings/second
- GPU (T4): ~200-500 embeddings/second
- GPU (A100): ~1000+ embeddings/second

If performance is significantly slower:
1. Check if GPU is being used: `client.model.device`
2. Increase batch size: `batch_size=64`
3. Profile with: `pytest --profile tests/integration/test_paecter_client.py`

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

1. **Install dependencies:** `uv pip install -e ".[paecter]"`
2. **Run basic tests:** `uv run pytest tests/integration/test_paecter_client.py -v`
3. **Test with your data:** Create `test_paecter_real_data.py` (see Phase 2 above)
4. **Evaluate quality:** Check similarity scores make sense for known similar pairs
5. **Scale up:** Move to Dagster pipeline integration (Phase 4)

## References

- **Model:** https://huggingface.co/mpi-inno-comp/paecter
- **Paper:** https://arxiv.org/pdf/2402.19411
- **Sentence Transformers:** https://www.sbert.net/
- **PaECTER Spec:** `.kiro/specs/paecter_analysis_layer/`

## Questions?

Common questions and their answers:

**Q: Do I need a GPU?**
A: No, but it's much faster. CPU works fine for testing and small datasets (< 10K records).

**Q: Can I use a different model?**
A: Yes! The `PaECTERClient` accepts any sentence-transformers compatible model:
```python
client = PaECTERClient(model_name="AI-Growth-Lab/PatentSBERTa")
```

**Q: How do I integrate with existing CET classification?**
A: PaECTER embeddings can be used alongside CET classification. In fact, the Bayesian MoE design (Phase 6) combines them: Classification → Similarity → Embedding.

**Q: What's the difference between PaECTER and PatentSBERTa?**
A: PaECTER is fine-tuned with examiner citations and optimized for prior art search. PatentSBERTa is a more general patent BERT model. Both work with our client.

**Q: Can I run this in Dagster Cloud?**
A: Yes, but you'll need to:
1. Ensure PyTorch is installed (might need CPU-only version)
2. Handle model caching (use persistent storage or embed model in deployment)
3. Consider using HuggingFace Inference API instead for serverless deployment

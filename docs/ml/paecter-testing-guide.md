# PaECTER Testing Guide

This guide explains how to test the PaECTER (Patent Embeddings using Citation-informed TransformERs) integration with your SBIR-Analytics data.

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

### Phase 2: Real Data Integration (IMPLEMENTED)

**Status:** ✅ Implemented

**Objectives:**
- Test with real SBIR award data from your database
- Test with real USPTO patent data
- Generate embeddings for a sample dataset
- Save embeddings to Parquet files
- Evaluate quality on known similar pairs

**Implementation:**

A test script is available at `scripts/test_paecter_real_data.py` that:

1. **Loads real SBIR data** from CSV (using DuckDB for efficient processing)
2. **Prepares award texts** from Award Title, Abstract, and Solicitation Title fields
3. **Generates embeddings** using PaECTER (API or local mode)
4. **Saves embeddings** to Parquet format for reuse
5. **Displays statistics** and summary information

**Usage:**

```bash
# API mode (default - requires HF_TOKEN)
export HF_TOKEN="your_token_here"
python scripts/test_paecter_real_data.py

# Local mode (requires sentence-transformers)
python scripts/test_paecter_real_data.py --local

# Process limited number of records
python scripts/test_paecter_real_data.py --limit 100

# Use specific CSV file
python scripts/test_paecter_real_data.py --csv data/raw/sbir/awards_data.csv

# Load from S3 (direct URL)
python scripts/test_paecter_real_data.py \
    --s3 s3://your-bucket-name/data/raw/sbir/awards_data.csv

# Load from S3 (using bucket env var)
export SBIR_ANALYTICS_S3_BUCKET=your-bucket-name
python scripts/test_paecter_real_data.py

# Load from S3 (using --s3-bucket flag)
python scripts/test_paecter_real_data.py \
    --s3-bucket your-bucket-name \
    --csv data/raw/sbir/awards_data.csv

# Custom output path and batch size
python scripts/test_paecter_real_data.py \
    --output data/processed/my_embeddings.parquet \
    --batch-size 64
```

**Output:**

The script generates a Parquet file with:
- `award_id`: Award identifier
- `embedding`: 1024-dimensional embedding vector (as list)
- `model_version`: Model version used
- `inference_mode`: "api" or "local"
- `dimension`: Embedding dimension (1024)

**Loading embeddings:**

```python
import pandas as pd
import numpy as np

# Load embeddings
df = pd.read_parquet("data/processed/paecter_embeddings_awards_sample.parquet")

# Convert to numpy array for similarity computation
embeddings = np.array([np.array(e) for e in df['embedding']])

# Use with PaECTER client for similarity
from src.ml.paecter_client import PaECTERClient
client = PaECTERClient()
similarities = client.compute_similarity(embeddings[:10], embeddings[10:20])
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

## Interpreting Similarity Scores

### Understanding Cosine Similarity

PaECTER embeddings use **cosine similarity** (range: -1 to 1, typically 0 to 1 for normalized embeddings):
- **0.95-1.0**: Very high similarity (likely related technologies)
- **0.85-0.95**: High similarity (possibly related, but review carefully)
- **0.70-0.85**: Moderate similarity (may share technical language patterns)
- **0.50-0.70**: Low similarity (likely unrelated)
- **< 0.50**: Very low similarity (clearly unrelated)

### Known Limitations

**High Similarity Between Unrelated Domains**

You may observe unexpectedly high similarity scores (e.g., 0.85-0.90) between clearly unrelated technologies. For example:
- "Deep Learning for Drug Discovery" ↔ "High-Performance Photovoltaic Device" might show ~0.87 similarity

**Why this happens:**
1. **Shared technical vocabulary**: Terms like "architecture", "materials", "efficiency", "stability" appear in many technical domains
2. **General language patterns**: Both texts describe advanced technology with similar sentence structures
3. **Model training data**: PaECTER is trained on patents, which share common technical language patterns across domains
4. **Embedding space compression**: High-dimensional embeddings can create spurious similarities

**This is expected behavior** and not necessarily a bug. The model captures semantic similarity at multiple levels, including:
- Domain-specific content (what you want)
- Technical language patterns (may create false positives)
- Structural similarities (sentence length, complexity)

### Recommendations

**1. Use Threshold-Based Filtering**

Set appropriate thresholds based on your use case:
```python
# Conservative: only very high similarities
high_confidence_threshold = 0.90

# Moderate: include high similarities with review
moderate_threshold = 0.85

# Aggressive: include moderate similarities (more false positives)
low_threshold = 0.75

# Filter results
top_matches = [
    (patent_id, score)
    for patent_id, score in similarities
    if score >= high_confidence_threshold
]
```

**2. Add Domain-Based Pre-Filtering**

Before computing similarities, filter by domain keywords or CET classifications:
```python
# Example: Only compare awards and patents in similar domains
def domain_match(award_domain: str, patent_domain: str) -> bool:
    """Check if award and patent are in compatible domains."""
    compatible_domains = {
        "AI/ML": ["AI/ML", "Software"],
        "Materials": ["Materials", "Manufacturing"],
        "Energy": ["Energy", "Materials"],
    }
    return patent_domain in compatible_domains.get(award_domain, [])
```

**3. Use Multi-Stage Filtering**

Combine multiple signals:
```python
# Stage 1: High similarity threshold
candidates = filter_by_similarity(similarities, threshold=0.85)

# Stage 2: Domain compatibility
candidates = filter_by_domain(candidates, award_domain, patent_domains)

# Stage 3: Keyword overlap
candidates = filter_by_keywords(candidates, min_keyword_overlap=3)
```

**4. Establish Baseline Thresholds**

Test with known similar and dissimilar pairs to establish domain-specific thresholds:
```python
# Known similar pairs should have similarity > 0.90
# Known dissimilar pairs should have similarity < 0.70
# Adjust your threshold based on your data distribution
```

**5. Review Top-K Results**

Instead of using a single threshold, consider top-k retrieval:
```python
# Get top 5 matches for each award
top_k = 5
for award_idx, award_id in enumerate(award_ids):
    top_indices = np.argsort(similarities[award_idx])[::-1][:top_k]
    top_scores = similarities[award_idx][top_indices]

    # Review all top-k, not just high-scoring ones
    for patent_idx, score in zip(top_indices, top_scores):
        if score >= 0.80:  # Still use a minimum threshold
            # Add to results for review
            pass
```

### Debugging High Similarity Scores

If you encounter unexpectedly high similarities, use the diagnostic script:

```bash
python scripts/debug_paecter_similarity.py
```

This script will:
- Show the actual prepared text being embedded
- Compute detailed similarity metrics
- Analyze word overlap between texts
- Compare with known similar/dissimilar pairs
- Provide recommendations for threshold adjustment

### Expected Similarity Distributions

Based on the PaECTER specification, you should expect:
- **Negative pairs** (unrelated): Mean cosine similarity ≤ 0.30
- **Positive pairs** (related): Mean cosine similarity ≥ 0.55

If your unrelated pairs show mean similarity > 0.30, consider:
- Adjusting your similarity thresholds upward
- Adding domain-based filtering
- Using additional signals beyond embeddings

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
5. **Test with your data:** `python scripts/test_paecter_real_data.py --limit 100`
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


---

# Quick Start

# PaECTER Testing Quick Start

## 🚀 Quick Test (5 minutes)

```bash
# 1. Set environment variables
export HF_TOKEN="your_huggingface_token"  # Get from https://huggingface.co/settings/tokens
export SBIR_ANALYTICS_S3_BUCKET="sbir-analytics-production-data"

# 2. Run combined test script
python scripts/test_paecter_combined_s3.py --limit-sbir 10 --limit-uspto 10
```

## 📋 What Was Created

### 1. Combined Test Script
**File**: `scripts/test_paecter_combined_s3.py`

Tests both SBIR and USPTO data from S3:
- Loads SBIR awards from S3
- Loads USPTO patents from S3 (PatentsView)
- Generates PaECTER embeddings for both
- Computes similarity scores
- Saves results to Parquet files

### 2. Dagster Assets
**Directory**: `src/assets/paecter/`

Three new assets:
- `paecter_embeddings_awards`: Embeddings for SBIR awards
- `paecter_embeddings_patents`: Embeddings for USPTO patents
- `paecter_award_patent_similarity`: Similarity scores between awards and patents

### 3. Dagster Job
**File**: `src/assets/jobs/paecter_job.py`

Job to materialize all PaECTER assets in one run.

### 4. Configuration
**File**: `config/base.yaml`

Added `ml.paecter` section with:
- API/local mode settings
- Batch size and rate limiting
- Similarity thresholds
- Coverage validation thresholds

## 🧪 Testing Options

### Option 1: Combined Script (Recommended for Testing)
```bash
# Basic test
python scripts/test_paecter_combined_s3.py

# With limits (faster)
python scripts/test_paecter_combined_s3.py --limit-sbir 100 --limit-uspto 50

# Local mode (no API required)
python scripts/test_paecter_combined_s3.py --local
```

### Option 2: Dagster Assets (Recommended for Production)
```bash
# Start Dagster UI
uv run dagster dev

# Materialize prerequisites first
uv run dagster asset materialize validated_sbir_awards transformed_patents

# Then run PaECTER job
uv run dagster asset materialize -m src.assets.jobs.paecter_job paecter_job
```

## 📊 Output Files

All outputs are saved to `data/processed/paecter/`:

- `paecter_embeddings_sbir.parquet` - Award embeddings
- `paecter_embeddings_uspto.parquet` - Patent embeddings
- `award_patent_similarities.parquet` - Similarity scores

## 🔧 Configuration

Edit `config/base.yaml` to customize:

```yaml
ml:
  paecter:
    use_local: false  # Set to true for local mode
    api:
      batch_size: 32
      max_qps: 10
    similarity_threshold: 0.80
```

## 📚 Full Documentation

See [paecter-s3-testing-guide.md](./paecter-s3-testing-guide.md) for:
- Detailed troubleshooting
- Performance optimization
- Advanced configuration
- Integration examples

## ✅ Verification Checklist

- [ ] AWS credentials configured (`aws s3 ls` works)
- [ ] S3 bucket set (`echo $SBIR_ANALYTICS_S3_BUCKET`)
- [ ] HuggingFace token set (`echo $HF_TOKEN`)
- [ ] Data exists in S3 (check Lambda downloads)
- [ ] Test script runs successfully
- [ ] Output files generated in `data/processed/paecter/`

## 🆘 Common Issues

**S3 Access Denied**: Check AWS credentials
**401 Unauthorized**: Verify HF_TOKEN is valid
**No data found**: Run Lambda functions to download data first
**Memory error**: Use `--limit` flags or reduce batch size

For detailed troubleshooting, see the full guide.


---

# S3 Testing

# PaECTER S3 Testing Guide

This guide provides comprehensive instructions for testing PaECTER (Patent Embeddings) integration with SBIR and USPTO data stored in S3.

## Prerequisites

1. **AWS Credentials**: Configure AWS credentials with access to your S3 bucket
   ```bash
   export AWS_ACCESS_KEY_ID="your_access_key"  # pragma: allowlist secret
     export AWS_SECRET_ACCESS_KEY="your_secret_key"  # pragma: allowlist secret
   export AWS_DEFAULT_REGION="us-east-2"  # or your region
   ```

2. **S3 Bucket Configuration**: Set the S3 bucket name
   ```bash
   export SBIR_ANALYTICS_S3_BUCKET="sbir-analytics-production-data"
   ```

3. **HuggingFace Token** (for API mode):
   ```bash
   export HF_TOKEN="your_huggingface_token"
   ```
   Get a free token from: https://huggingface.co/settings/tokens

4. **Python Environment**: Ensure dependencies are installed
   ```bash
   uv sync
   ```

## Quick Start: Combined Test Script

The easiest way to test PaECTER with both SBIR and USPTO data from S3 is using the combined test script:

### Basic Usage (API Mode)

```bash
# Set required environment variables
export HF_TOKEN="your_token_here"
export SBIR_ANALYTICS_S3_BUCKET="sbir-analytics-production-data"

# Run the combined test
python scripts/test_paecter_combined_s3.py
```

### Local Mode (No API Required)

```bash
# Use local sentence-transformers model
python scripts/test_paecter_combined_s3.py --local
```

### Advanced Options

```bash
# Limit records for faster testing
python scripts/test_paecter_combined_s3.py \
    --limit-sbir 100 \
    --limit-uspto 50

# Use specific S3 paths
python scripts/test_paecter_combined_s3.py \
    --sbir-s3 s3://sbir-analytics-production-data/raw/sbir/award_data.csv \
    --uspto-s3 s3://sbir-analytics-production-data/raw/uspto/patentsview/2025-11-18/patent.zip

# Custom output directory and similarity threshold
python scripts/test_paecter_combined_s3.py \
    --output-dir data/processed/paecter_test \
    --similarity-threshold 0.85 \
    --batch-size 64
```

### Script Output

The script generates:
- `paecter_embeddings_sbir.parquet`: SBIR award embeddings
- `paecter_embeddings_uspto.parquet`: USPTO patent embeddings
- `award_patent_similarities.parquet`: Similarity scores between awards and patents

All files are saved to `data/processed/paecter/` by default (or `--output-dir` if specified).

## Testing with Dagster Assets

### 1. Materialize Prerequisites

Before running PaECTER assets, ensure the following assets are materialized:

```bash
# Start Dagster UI
uv run dagster dev

# In Dagster UI, materialize:
# - validated_sbir_awards
# - transformed_patents
```

### 2. Run PaECTER Job

```bash
# Materialize all PaECTER assets
uv run dagster asset materialize -m src.assets.jobs.paecter_job paecter_job

# Or materialize individual assets
uv run dagster asset materialize \
    paecter_embeddings_awards \
    paecter_embeddings_patents \
    paecter_award_patent_similarity
```

### 3. View Results

Results are saved as Parquet files:
- `data/processed/paecter_embeddings_awards.parquet`
- `data/processed/paecter_embeddings_patents.parquet`
- `data/processed/paecter_award_patent_similarity.parquet`

View in Dagster UI or load with pandas:

```python
import pandas as pd

# Load embeddings
award_embeddings = pd.read_parquet("data/processed/paecter_embeddings_awards.parquet")
patent_embeddings = pd.read_parquet("data/processed/paecter_embeddings_patents.parquet")

# Load similarities
similarities = pd.read_parquet("data/processed/paecter_award_patent_similarity.parquet")

# View top matches
print(similarities.nlargest(10, "similarity_score"))
```

## Individual Component Testing

### Test SBIR Data Only

```bash
# Use the existing test script with S3
python scripts/test_paecter_real_data.py \
    --s3 s3://sbir-analytics-production-data/raw/sbir/award_data.csv \
    --limit 100
```

### Test USPTO Data Only

The combined script supports USPTO-only testing by providing only `--uspto-s3`:

```bash
python scripts/test_paecter_combined_s3.py \
    --uspto-s3 s3://sbir-analytics-production-data/raw/uspto/patentsview/2025-11-18/patent.zip \
    --limit-uspto 50
```

## Configuration

### API Mode (Default)

The default configuration uses HuggingFace Inference API. Configure in `config/base.yaml`:

```yaml
ml:
  paecter:
    provider: "huggingface"
    use_local: false
    api:
      token_env: "HF_TOKEN"
      batch_size: 32
      max_qps: 10
      timeout_seconds: 60
```

### Local Mode

To use local sentence-transformers model:

```yaml
ml:
  paecter:
    provider: "huggingface"
    use_local: true
    local:
      model_name: "mpi-inno-comp/paecter"
      device: "auto"
      batch_size: 32
```

Or override via environment variable:
```bash
export SBIR_ETL__ML__PAECTER__USE_LOCAL=true
```

## Troubleshooting

### S3 Access Issues

**Error**: `NoCredentialsError` or `AccessDenied`

**Solution**: Verify AWS credentials are configured:
```bash
aws s3 ls s3://sbir-analytics-production-data/
```

### HuggingFace API Issues

**Error**: `401 Unauthorized` or `Invalid token`

**Solution**:
1. Verify token is set: `echo $HF_TOKEN`
2. Get a new token from https://huggingface.co/settings/tokens
3. Ensure token has read access

**Error**: `429 Too Many Requests`

**Solution**: Reduce batch size or max_qps in config:
```yaml
ml:
  paecter:
    api:
      batch_size: 16  # Reduce from 32
      max_qps: 5      # Reduce from 10
```

### Missing Data

**Error**: `No patent data available for embedding generation`

**Solution**:
1. Verify S3 paths are correct
2. Check that Lambda functions have downloaded data:
   ```bash
   aws s3 ls s3://sbir-analytics-production-data/raw/uspto/patentsview/
   aws s3 ls s3://sbir-analytics-production-data/raw/sbir/
   ```

### Memory Issues

**Error**: `MemoryError` or process killed

**Solution**:
1. Reduce batch size
2. Process fewer records (use `--limit-sbir` and `--limit-uspto`)
3. Use API mode instead of local mode (local mode loads full model into memory)

## Performance Tips

1. **Start Small**: Test with `--limit-sbir 10 --limit-uspto 10` first
2. **Use API Mode**: Faster for small batches, no model download required
3. **Batch Processing**: Increase `--batch-size` for better throughput (up to 64)
4. **Parallel Processing**: Dagster assets can run in parallel if dependencies allow

## Expected Results

### Embedding Dimensions
- All embeddings should be **1024-dimensional** vectors
- Each embedding is a list of 1024 floats

### Similarity Scores
- Range: **0.0 to 1.0** (cosine similarity)
- Typical matches: **0.80-0.95**
- Very similar: **>0.90**
- Moderately similar: **0.70-0.85**

### Coverage
- Awards: **≥95%** should have valid embeddings
- Patents: **≥98%** should have valid embeddings

## Next Steps

1. **Analyze Results**: Review top similarity matches to validate quality
2. **Tune Thresholds**: Adjust `similarity_threshold` based on your use case
3. **Scale Up**: Remove `--limit` flags to process full datasets
4. **Integrate**: Use embeddings in downstream analysis or Neo4j graph

## Additional Resources

- [PaECTER Model Card](https://huggingface.co/mpi-inno-comp/paecter)
- [HuggingFace Inference API Docs](https://huggingface.co/docs/inference-providers/index)
- [Dagster Asset Documentation](https://docs.dagster.io/concepts/assets)
- [SBIR ETL Architecture](../architecture/detailed-overview.md)

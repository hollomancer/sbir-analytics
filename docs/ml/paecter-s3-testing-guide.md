# PaECTER S3 Testing Guide

This guide provides comprehensive instructions for testing PaECTER (Patent Embeddings) integration with SBIR and USPTO data stored in S3.

## Prerequisites

1. **AWS Credentials**: Configure AWS credentials with access to your S3 bucket
   ```bash
   export AWS_ACCESS_KEY_ID="your_access_key"
   export AWS_SECRET_ACCESS_KEY="your_secret_key"
   export AWS_DEFAULT_REGION="us-east-2"  # or your region
   ```

2. **S3 Bucket Configuration**: Set the S3 bucket name
   ```bash
   export SBIR_ETL__S3_BUCKET="sbir-etl-production-data"
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
export SBIR_ETL__S3_BUCKET="sbir-etl-production-data"

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
    --sbir-s3 s3://sbir-etl-production-data/raw/sbir/award_data.csv \
    --uspto-s3 s3://sbir-etl-production-data/raw/uspto/patentsview/2025-11-18/patent.zip

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
    --s3 s3://sbir-etl-production-data/raw/sbir/award_data.csv \
    --limit 100
```

### Test USPTO Data Only

The combined script supports USPTO-only testing by providing only `--uspto-s3`:

```bash
python scripts/test_paecter_combined_s3.py \
    --uspto-s3 s3://sbir-etl-production-data/raw/uspto/patentsview/2025-11-18/patent.zip \
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
aws s3 ls s3://sbir-etl-production-data/
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
   aws s3 ls s3://sbir-etl-production-data/raw/uspto/patentsview/
   aws s3 ls s3://sbir-etl-production-data/raw/sbir/
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
- [HuggingFace Inference API Docs](https://huggingface.co/docs/api-inference)
- [Dagster Asset Documentation](https://docs.dagster.io/concepts/assets)
- [SBIR ETL Architecture](./architecture.md)


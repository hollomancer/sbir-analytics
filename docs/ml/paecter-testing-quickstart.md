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

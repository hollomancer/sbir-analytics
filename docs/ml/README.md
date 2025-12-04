---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Machine Learning Documentation

This directory contains documentation for machine learning features in the SBIR ETL project, primarily focused on the Commercialization and Economic Transformation (CET) classification system.

## Overview

This directory contains documentation for machine learning features in the SBIR ETL project:

- **CET Classification**: Categorizes SBIR/STTR awards based on commercialization potential and economic impact
- **PaECTER Embeddings**: Generates semantic embeddings for awards and patents to compute similarity scores

## Getting Started

Start with these guides to understand and use the ML features:

1. **[PaECTER Integration Guide](paecter.md)** - Patent and award similarity using embeddings
2. **[CET Integration Guide](cet-integration.md)** - How to integrate CET classification into your workflow
3. **[CET Classifier](cet-classifier.md)** - Core classifier documentation and usage

## Detailed Documentation

### PaECTER Embeddings

- **[PaECTER Integration Guide](paecter.md)** - Complete PaECTER documentation
  - Dual inference modes (API and local)
  - Configuration and setup
  - Dagster asset integration
  - Performance optimization
  - Troubleshooting guide

### CET Classification

- **[CET Classifier](cet-classifier.md)** - Main classifier documentation
  - Model architecture and features
  - Training process and evaluation
  - Usage examples and API reference

- **[CET Classifier Appendix](cet-classifier-appendix.md)** - Extended technical details
  - Detailed feature engineering
  - Model evaluation metrics
  - Performance analysis and tuning
  - Implementation details

- **[CET Award Training Data](cet-award-training-data.md)** - Training data documentation
  - Data sources and collection methodology
  - Data labeling and annotation process
  - Training dataset characteristics
  - Data quality and validation

## Quick Reference

### Using PaECTER Embeddings

Generate embeddings and compute similarity scores:

```bash
# Via Dagster UI
# Navigate to Assets → paecter group → Materialize

# Via CLI
dagster asset materialize -m src.definitions --select "paecter*"

# Run complete PaECTER job
dagster job execute -m src.definitions -j paecter_job
```

### Using the CET Classifier

The CET classifier is integrated into the Dagster pipeline as an asset. To run classification:

```bash
# Via Dagster UI
# Navigate to Assets → CET Classification → Materialize

# Via CLI
dagster asset materialize -m src.definitions --select cet_classifications
```

### Classification Categories

The CET classifier categorizes awards into:

- **High Commercialization Potential** - Strong indicators of market success
- **Medium Commercialization Potential** - Moderate commercialization signals
- **Low Commercialization Potential** - Limited commercial indicators
- **Research-Focused** - Primarily academic/research outcomes

## Architecture

The ML systems integrate with the broader SBIR analytics pipeline:

### PaECTER Embeddings

- **Input**: SBIR awards and USPTO patents
- **Processing**: Text embedding generation (1024-dimensional vectors)
- **Output**: Similarity scores between awards and patents
- **Use Cases**: Technology transfer detection, patent-award matching

### CET Classification

- **Input**: SBIR/STTR award information
- **Processing**: ML-based commercialization potential classification
- **Output**: Classification labels and confidence scores
- **Integration**: Transition Detection, USPTO Patents, USAspending Data

## Related Documentation

- **[Transition Detection Documentation](../transition/)** - Technology transition detection system
- **[Integration Guide](cet-integration.md)** - Integration patterns and workflows
- **[Architecture Documentation](../architecture/)** - System architecture overview

## Configuration

ML feature configuration is managed through:

- **PaECTER**: `config/base.yaml` (ml.paecter section)
  - Inference mode (API or local)
  - Batch sizes and rate limits
  - Similarity thresholds
  - Quality coverage thresholds

- **CET Classifier**: `config/cet/` directory
  - CET configuration files
  - Model parameters
  - Classification thresholds

- **Environment Variables**: Override any configuration at runtime
  - `SBIR_ETL__ML__PAECTER__*` for PaECTER settings
  - `HF_TOKEN` for HuggingFace API access

---

For questions about the CET classifier or to report issues, refer to the detailed guides above or consult the main [project README](../../README.md).

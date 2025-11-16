# Machine Learning Documentation

This directory contains documentation for machine learning features in the SBIR ETL project, primarily focused on the Commercialization and Economic Transformation (CET) classification system.

## Overview

The CET classification system uses machine learning to categorize SBIR/STTR awards based on their commercialization potential and economic impact. This classification helps identify successful technology transitions and economic outcomes.

## Getting Started

Start with these guides to understand and use the CET classifier:

1. **[CET Integration Guide](cet-integration.md)** - How to integrate CET classification into your workflow
2. **[CET Classifier](cet_classifier.md)** - Core classifier documentation and usage

## Detailed Documentation

### Core Classifier

- **[CET Classifier](cet_classifier.md)** - Main classifier documentation
  - Model architecture and features
  - Training process and evaluation
  - Usage examples and API reference

- **[CET Classifier Appendix](cet_classifier_appendix.md)** - Extended technical details
  - Detailed feature engineering
  - Model evaluation metrics
  - Performance analysis and tuning
  - Implementation details

### Training Data

- **[CET Award Training Data](cet_award_training_data.md)** - Training data documentation
  - Data sources and collection methodology
  - Data labeling and annotation process
  - Training dataset characteristics
  - Data quality and validation

## Quick Reference

### Using the CET Classifier

The CET classifier is integrated into the Dagster pipeline as an asset. To run classification:

```python
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

The CET classification system integrates with:

- **Transition Detection** (`docs/transition/`) - Identifies successful technology transitions
- **Awards Data** - SBIR/STTR award information
- **USPTO Patents** - Patent data for commercialization signals
- **USAspending Data** - Federal contract and financial data

## Related Documentation

- **[Transition Detection Documentation](../transition/)** - Technology transition detection system
- **[Integration Guide](cet-integration.md)** - Integration patterns and workflows
- **[Architecture Documentation](../architecture/)** - System architecture overview

## Configuration

CET classifier configuration is managed through:

- `config/cet/` - CET configuration files
- Environment variables for model parameters
- Dagster configuration for pipeline integration

---

For questions about the CET classifier or to report issues, refer to the detailed guides above or consult the main [project README](../../README.md).

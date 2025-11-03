# CET Configuration Directory

This directory contains configuration files for the Critical and Emerging Technology (CET) classification module.

## Files

### taxonomy.yaml

Defines the 21 NSTC CET technology areas following the National Science and Technology Council framework:

- CET category definitions
- Keywords for each technology area
- Hierarchical relationships
- Taxonomy versioning (e.g., NSTC-2025Q1)

### classification.yaml

ML model hyperparameters and classification settings:

- TF-IDF vectorization parameters
- Logistic Regression configuration
- Probability calibration settings
- Confidence thresholds (High: ≥70, Medium: 40-69, Low: <40)
- Evidence extraction parameters

## Usage

Configuration files are loaded by the `TaxonomyLoader` in `src/ml/config/taxonomy_loader.py`.

Example:

```python
from src.ml.config.taxonomy_loader import TaxonomyLoader

loader = TaxonomyLoader()
taxonomy = loader.load_taxonomy()  # Loads taxonomy.yaml
config = loader.load_classification_config()  # Loads classification.yaml
```

## Taxonomy Versioning

The taxonomy is versioned to support longitudinal analysis:

- Format: `NSTC-{YEAR}Q{QUARTER}` (e.g., `NSTC-2025Q1`)
- Stored in each classification for tracking changes over time
- Enables historical analysis when taxonomy updates occur

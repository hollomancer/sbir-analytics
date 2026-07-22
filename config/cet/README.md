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

### defense_crosswalk.yaml

Defines a cited, versioned many-to-many policy crosswalk from the canonical
21-area `NSTC-2025Q1` taxonomy to:

- `DOD-CTA-14-2022` — the frozen 14 DoD Critical Technology Areas.
- `DOD-SC-8-2022` — the four focus areas plus four strategic enablers from
  *Securing Defense-Critical Supply Chains* (2022).

`DOD-SC-8-2022` is a repository label, not an official “NDIS-8” taxonomy.
Each mapping records `direct`, `partial`, or `enabling` strength and a short
rationale. The supply-chain baseline validates complete CET coverage and
target referential integrity before producing results.

## Usage

Configuration files are loaded by the `TaxonomyLoader` in `src/ml/config/taxonomy_loader.py`.

Example:

```python
from sbir_etl.ml.config.taxonomy_loader import TaxonomyLoader

loader = TaxonomyLoader()
taxonomy = loader.load_taxonomy()  # Loads taxonomy.yaml
config = loader.load_classification_config()  # Loads classification.yaml
```

## Taxonomy Versioning

The taxonomy is versioned to support longitudinal analysis:

- Format: `NSTC-{YEAR}Q{QUARTER}` (e.g., `NSTC-2025Q1`)
- Stored in each classification for tracking changes over time
- Enables historical analysis when taxonomy updates occur

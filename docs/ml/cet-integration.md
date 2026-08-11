---
Type: Subsystem Overview
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-03
Status: active
---

# CET Classification

The CET subsystem classifies awards and patents against the repository's canonical 21-area
`NSTC-2025Q1` taxonomy. Classification is probabilistic and must retain its taxonomy version,
scores, and supporting evidence; a label is not a policy finding by itself.

## Canonical components

| Concern | Owner |
| --- | --- |
| Taxonomy | `config/cet/taxonomy.yaml` |
| Taxonomy loading and checks | `sbir_ml.ml.config.taxonomy_loader` and `taxonomy_checks` |
| Award model and rules | `sbir_ml.ml.models.cet_classifier.CETClassifier` |
| Patent model | `sbir_ml.ml.models.patent_classifier` |
| Dagster assets | `packages/sbir-analytics/sbir_analytics/assets/cet/` |
| Thresholds and priors | `config/cet/classification.yaml` |
| Patent keywords | `config/cet/patent_keywords.yaml` |

Do not introduce a second hardcoded list of CET areas. Reporting and transition consumers should
load the taxonomy or consume versioned classifications.

## Data flow

```text
taxonomy + award/patent text
          │
          ▼
classification and rule adjustment
          │
          ├──▶ quality checks and human-validation samples
          ├──▶ Parquet classification outputs and aggregates
          ├──▶ company profiles
          └──▶ Neo4j CETArea nodes and relationships
```

The main Dagster assets are exported from `assets/cet/__init__.py`, including taxonomy,
award/patent classifications, analytics, validation, company profiles, and Neo4j loading. Inspect
the definitions in Dagster rather than relying on a copied asset list when changing selections.

Run the complete job only after installing the full stack and providing its local inputs:

```bash
make cet-run
```

Heavy CET assets are not scheduled by default on the self-hosted server. Follow the
[capacity guidance](../deployment/self-hosted-server.md#heavy-assets) before a live run.

## Model and rule boundary

The classifier produces per-area scores. `RuleEngine` then applies negative-keyword penalties,
context rules, and agency/branch priors from versioned YAML. See the [classifier](cet-classifier.md)
and [rule-engine guide](cet-rule-engine.md) for their narrow contracts.

## Training-data limitation

The `ml/cet_award_training_dataset` asset looks for labeled CSV or NDJSON inputs and writes an
empty, failed check when no input exists. When input does exist, the current code imports
`sbir_ml.ml.data.award_training_loader`, which is absent from the repository; the asset therefore
records `reason: load_failed` instead of producing a usable award-training dataset. Treat award
training as unsupported until that loader is restored or the asset is redesigned and tested.

Patent training is separate: `train_cet_patent_classifier` expects
`data/processed/cet_patent_training.parquet` with the schema documented in the asset itself.

## Validation and evidence

Available assets can generate a human sample, inter-annotator agreement report, distribution-drift
report, and asset checks. These outputs measure classifier behavior; they do not make downstream
commercialization claims citable. Research use still follows the
[epistemic-tier](../steering/epistemic-tiers.md) and study-contract rules.

Transition detection consumes CET alignment as one optional signal. The narrow integration is
documented in [Transition CET alignment](../transition/cet-integration.md).

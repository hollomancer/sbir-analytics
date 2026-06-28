# Machine Learning Documentation

Two ML systems: CET classification (predicts applicability to 21 NSTC critical & emerging technology areas) and ModernBert embeddings (semantic similarity between awards and patents).

## CET Classification

| Doc | Purpose |
|-----|---------|
| [cet-integration.md](cet-integration.md) | Award classifier: data flow, model architecture, Neo4j schema, quality checks, scenarios |
| [cet-classifier.md](cet-classifier.md) | Patent classifier: feature extraction, vectorizers, training/inference flow |
| [cet-award-training-data.md](cet-award-training-data.md) | Training data: sources, labeling, quality |

**Run award classification:**

```bash
dagster asset materialize -m sbir_analytics.definitions --select cet_classifications
dagster job execute -m sbir_analytics.definitions -j cet_full_pipeline_job
```

## ModernBert Embeddings

| Doc | Purpose |
|-----|---------|
| [modernbert.md](modernbert.md) | Full guide: inference modes, config, Dagster assets, optimization, troubleshooting |

**Run embeddings:**

```bash
dagster asset materialize -m sbir_analytics.definitions --select "modernbert*"
dagster job execute -m sbir_analytics.definitions -j modernbert_job
```

## Configuration

- **ModernBert**: `config/base.yaml` § `ml.modernbert` — inference mode, batch sizes, similarity thresholds; `HF_TOKEN` env var for HuggingFace API
- **CET**: `config/cet/` — taxonomy (`taxonomy.yaml`), classification thresholds (`classification.yaml`)

## Related

- [Transition Detection](../transition/) — consumes CET classifications as one of its signals
- [Architecture](../architecture/) — system-level overview

# Machine Learning Documentation

This project has two machine-learning systems. CET classification decides which
of 21 critical and emerging technology areas may apply to a record. ModernBERT
embeddings measure how similar award and patent text is.

## CET Classification

| Doc | Purpose |
|-----|---------|
| [cet-integration.md](cet-integration.md) | Technology categories, pipeline steps, checks, and known limits |
| [cet-classifier.md](cet-classifier.md) | How the patent classifier prepares text, trains, and makes predictions |
| [cet-rule-engine.md](cet-rule-engine.md) | Keyword and context rules, including agency and service-branch settings |

**Run the complete CET pipeline:**

```bash
make cet-run
```

## ModernBert Embeddings

| Doc | Purpose |
|-----|---------|
| [modernbert.md](modernbert.md) | Setup, run options, Dagster assets, performance, and troubleshooting |

**Run the complete embeddings pipeline:**

```bash
make modernbert-run
```

Use the Make commands above for a full run. They keep the Dagster module and job
names in one place. Follow the linked guides when you need to run only part of a
pipeline.

## Configuration

- **ModernBERT**: `config/base.yaml` under `ml.modernbert` sets the run mode,
  batch sizes, and similarity limits. Set `HF_TOKEN` to use the Hugging Face API.
- **CET**: `config/cet/taxonomy.yaml` defines the technology areas, and
  `config/cet/classification.yaml` sets the classification limits.

## Related

- [Transition Detection](../transition/) — uses CET classifications as one input
- [Architecture](../architecture/) — shows how the system fits together

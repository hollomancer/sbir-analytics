# sbir-analytics

Full SBIR analytics pipeline including Dagster orchestration, CLI, ML, and Neo4j.

This is a convenience metapackage that installs [`sbir-etl`](../../) with all extras
enabled. If you only need the ETL library (extractors, enrichers, transformers), install
`sbir-etl` directly.

## Installation

```bash
# Full pipeline (Dagster + CLI + S3 + ML + Neo4j)
pip install sbir-analytics

# ETL library only (no Dagster, CLI, ML, or Neo4j)
pip install sbir-etl

# Just the data models (only pydantic)
pip install sbir-models
```

## What's Included

| Package | What You Get |
|---------|-------------|
| `sbir-etl` | ETL library — extractors, enrichers, transformers, models, config |
| `sbir-etl[pipeline]` | + Dagster orchestration (assets, jobs, sensors) |
| `sbir-etl[cli]` | + `sbir-cli` command-line interface |
| `sbir-etl[cloud]` | + AWS S3 storage (boto3, cloudpathlib) |
| `sbir-etl[ml]` | + ML/NLP (scikit-learn, spacy, huggingface) |
| `sbir-etl[neo4j]` | + Neo4j graph database loader |
| **`sbir-analytics`** | **All of the above** |

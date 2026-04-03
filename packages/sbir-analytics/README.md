# sbir-analytics

Full SBIR analytics pipeline including Dagster orchestration, CLI, ML, and Neo4j.

Installs [`sbir-etl`](../../) with all extras plus the `sbir_analytics` Python
package containing deployment and infrastructure modules (AWS Lambda handlers,
developer automation) that don't belong in the reusable ETL library.

## Installation

```bash
# Full pipeline (Dagster + CLI + S3 + ML + Neo4j)
pip install sbir-analytics

# ETL library only (no Dagster, CLI, ML, or Neo4j)
pip install sbir-etl
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
| **`sbir-analytics`** | **All of the above** + `sbir_analytics.lambda` |

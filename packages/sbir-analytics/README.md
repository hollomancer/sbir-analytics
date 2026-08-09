# sbir-analytics

Full SBIR analytics pipeline including Dagster orchestration, ML, and Neo4j.

Installs the ETL integrations used by the pipeline plus the `sbir_ml` and
`sbir_graph` workspace packages. The `sbir_analytics` Python package contains
Dagster orchestration and application tools that do not belong in the reusable
ETL library.

## Installation

These packages are currently installed from a repository checkout; they are not
published to PyPI.

From the repository root:

```bash
make install       # full workspace; uv sync --extra stack-dev
make install-core  # reusable sbir-etl library only; uv sync
```

## What's Included

| Package | What You Get |
|---------|-------------|
| `sbir-etl` | ETL library — extractors, enrichers, transformers, models, config |
| `sbir-etl[cloud,uspto,monitoring]` | ETL integrations used by the pipeline |
| `sbir-ml[nlp]` | ML/NLP models and enrichment |
| `sbir-graph` | Neo4j loaders, queries, and packaged migrations |
| **`sbir-analytics`** | **All of the above** + orchestration and analysis tools |

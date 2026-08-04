# sbir-analytics

Full SBIR analytics pipeline including Dagster orchestration, ML, and Neo4j.

Installs [`sbir-etl`](../../) with all extras plus the `sbir_analytics` Python
package containing Dagster orchestration, the analytics API, and application
tools that don't belong in the reusable ETL library.

## Installation

From a package index:

```bash
# Full pipeline (Dagster + ML + Neo4j)
pip install sbir-analytics

# ETL library only (no Dagster, ML, or Neo4j)
pip install sbir-etl
```

From a repository checkout with development tools:

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
| **`sbir-analytics`** | **All of the above** + orchestration, API, and analysis tools |

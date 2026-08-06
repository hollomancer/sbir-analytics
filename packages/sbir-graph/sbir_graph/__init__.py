"""SBIR Graph — Neo4j graph database loading and query modules.

Epistemic tier: pipelines. Package default: loading, schema migrations, and
queries move validated ETL outputs deterministically without producing new
inference.

This package contains Neo4j-specific code: loaders for writing ETL
outputs to the graph database, and query modules for traversing
transition pathways.
"""

EPISTEMIC_TIER = "pipelines"

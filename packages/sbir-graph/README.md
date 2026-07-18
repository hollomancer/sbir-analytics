# sbir-graph

SBIR Graph — Neo4j graph database loaders and pathway queries.

Loads the SBIR knowledge graph into Neo4j (organizations, financial
transactions, patents, CET areas, transitions) and provides the Cypher pathway
queries used by the analytics layer. Node/relationship conventions are
documented in [`docs/schemas/neo4j.md`](../../docs/schemas/neo4j.md) and
[`docs/steering/neo4j-patterns.md`](../../docs/steering/neo4j-patterns.md).

## Installation

Installed automatically with the Neo4j extra or the full pipeline:

```bash
pip install "sbir-etl[neo4j]"   # ETL library + this package
pip install sbir-analytics       # full pipeline (includes [neo4j])
```

Depends on `neo4j>=5.20`, `pydantic`, `pandas`, `loguru`.

## Key Entry Points

| Import | Purpose |
|--------|---------|
| `sbir_graph.loaders.neo4j.client` — `Neo4jClient`, `Neo4jConfig` | Connection + batched MERGE upserts |
| `sbir_graph.loaders.neo4j.base` — `BaseNeo4jLoader`, `BaseLoaderConfig` | Base class for all loaders |
| `sbir_graph.loaders.neo4j.organizations` | Organization nodes (companies, agencies) |
| `sbir_graph.loaders.neo4j.cet` / `patent_cet` | CET area nodes + `APPLICABLE_TO` / `SPECIALIZES_IN` enrichment |
| `sbir_graph.loaders.neo4j.transitions` | Transition nodes + `TRANSITIONED_TO` / `RESULTED_IN` / `ENABLED_BY` / `INVOLVES_TECHNOLOGY` edges |
| `sbir_graph.loaders.neo4j.patents` | Patent nodes + assignment chains |
| `sbir_graph.loaders.neo4j.categorization` / `profiles` / `sec_edgar` / `ot_consortium` | Organization property enrichment |
| `sbir_graph.queries.pathway_queries` | Award → transition → contract pathway Cypher |

## Graph Model (summary)

SBIR awards are `:FinancialTransaction {transaction_type: "AWARD"}` (keyed by
`transaction_id`); companies are `:Organization {organization_type: "COMPANY"}`
(keyed by `organization_id`). Loaders MERGE on those authoritative keys — see
the schema docs above for the full label/relationship reference.

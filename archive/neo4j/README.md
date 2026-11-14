# Neo4j retirement record

**Status:** Retired in 0.19.0. Not maintained. Not an active evidence path.

Neo4j and the `sbir-graph` package were retired because no active study, report, or operated
research product required graph-native queries. Governed Parquet and DuckDB records remain the
authority. The graph was a derived read projection and could not strengthen a claim.

## Last supported release

- Tag: `v0.18.0`
- Release commit: `15e11ed45c3ce5adf6a2441bdd0092a255dc730f`
- Release Git tree: `0d8e2c6709abaaf9c3eab710ddd063911e7a2871`

The tag preserves the exact package, loaders, migrations, Cypher queries, Compose service,
scripts, tests, and dependency lock. This directory does not duplicate that source.

## Retired paths

- `packages/sbir-graph/`
- `packages/sbir-analytics/sbir_analytics/assets/*loading.py` graph projections
- `scripts/neo4j/` and graph-specific data scripts
- `config/neo4j/`
- graph services in `docker-compose.yml` and `docker-compose.server.yml`
- graph-only GitHub Actions and integration tests

## Successor boundary

- Governed analytical records: Parquet and DuckDB tables produced by their owning pipelines
- Candidate derivations: content-addressed Parquet snapshots under `sbir_etl.assertions`
- Study claims: frozen study inputs and generated study artifacts

The retired `detect_award_progressions` heuristic has no automatic successor.
`phase_ii_iii_pairs.parquet` is not declared equivalent to it.

## Recovery

Use the annotated `v0.18.0` tag and a verified final database dump for read-only historical
recovery. Follow the old tag's setup and backup instructions in an isolated checkout. Do not use
retired commands from a current checkout.

The retirement change does not delete host graph directories, Docker volumes, or dump files. Any
later deletion requires a separate operator decision with an exact target and recovery record.

See [the deployment cutover](../../docs/deployment/neo4j-retirement-cutover.md) and
[ADR-006](../../docs/decisions/ADR-006-retire-neo4j.md).

# Private Analytics API

The private API exposes curated, read-only SBIR evidence to analyst applications. It does not
accept Cypher or trigger Dagster runs. Neo4j-backed endpoints use parameterized queries and a
read access mode; deployed environments should also provide a database account with read-only
permissions.

Run locally with `sbir-analytics-api`, then authenticate with
`Authorization: Bearer $SBIR_ANALYTICS_API_TOKEN`. OpenAPI documentation is available at `/docs`.

The `/v1/snapshots` endpoints read validated JSON files from
`reports/analytics_snapshots/<analysis-kind>/<period>.json`. Supported kinds are `cet_portfolio`,
`transition_rate`, and `follow_on_multiplier`. Snapshot producers must preserve the metadata from
the analytics `ToolResult`: tool and schema versions, source references, warnings, and run ID.
Comparisons reject snapshots produced by different tools or versions.

MCP should be implemented, if needed, as an adapter over these service methods. It must not gain
raw graph access or pipeline controls that are absent from the HTTP API.

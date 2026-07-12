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

Pipeline code creates snapshots with `snapshot_from_tool_result(...)`, or
`snapshot_from_result(...)` for deterministic analyses such as the follow-on multiplier that do
not return `ToolResult`, and persists them atomically with `write_snapshot(...)`. Those writer
utilities normalize pandas/numpy values and retain explicit provenance. They are deliberately not
exposed as HTTP endpoints; the API container mounts the snapshot directory read-only.

`/health/live` reports process liveness. `/health/ready` checks Neo4j connectivity and snapshot-store
access. Neo4j availability errors are returned as a sanitized `503`. API requests emit structured
audit records with a correlation ID, route template, status, and duration; request headers,
identifiers, and query strings are not logged.

MCP should be implemented, if needed, as an adapter over these service methods. It must not gain
raw graph access or pipeline controls that are absent from the HTTP API.

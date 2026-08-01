# Private Analytics API

The private API exposes curated, read-only SBIR evidence to analyst applications. It does not
accept Cypher or trigger Dagster runs. Neo4j-backed endpoints use parameterized queries and a
read access mode; deployed environments should also provide a database account with read-only
permissions.

Run locally with `sbir-analytics-api`, then authenticate with
`Authorization: Bearer $SBIR_ANALYTICS_API_TOKEN`. OpenAPI documentation is available at `/docs`.

The `/v1/snapshots` endpoints read validated JSON files from
`reports/analytics_snapshots/<analysis-kind>/<period>.json` (root configurable via
`SBIR_ANALYTICS_SNAPSHOT_DIR`). Supported kinds are `cet_portfolio`, `transition_rate`,
`follow_on_multiplier`, `tech_census_drone_manufacturing`, and `tech_census_uas_relevance`.
Snapshot producers must preserve the metadata from
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

## Endpoints

All `/v1/*` routes require `Authorization: Bearer $SBIR_ANALYTICS_API_TOKEN`; the two
health routes are unauthenticated. The live OpenAPI schema at `/docs` is authoritative; this
table is a quick reference.

| Method & path | Params | Purpose | Auth |
|---|---|---|---|
| `GET /health/live` | — | Process liveness | No |
| `GET /health/ready` | — | Readiness: auth config, Neo4j, snapshot store (503 if any unavailable) | No |
| `GET /v1/organizations/{identifier}` | path `identifier` (organization_id / uei / duns / cage) | Single organization lookup | Yes |
| `GET /v1/organizations/{identifier}/awards` | `limit` (1–500, def 100), `offset` (0–100000, def 0) | Paginated award history for an org | Yes |
| `GET /v1/analytics/transitions` | `agency?`, `fiscal_year?` (1982–2100), `limit`, `offset` | Per-agency award→transition rates | Yes |
| `GET /v1/analytics/cet-concentration` | `agency?`, `fiscal_year?`, `limit`, `offset` | CET-area award concentration (HHI) | Yes |
| `GET /v1/data/freshness` | — | Per-entity record counts + latest timestamp | Yes |
| `GET /v1/snapshots` | `analysis_kind?` | List persisted snapshot summaries | Yes |
| `GET /v1/snapshots/{analysis_kind}/{period}` | `period` matches `^\d{4}(-Q[1-4])?$` | Fetch one snapshot | Yes |
| `GET /v1/snapshots/{analysis_kind}/{period}/compare/{comparison_period}` | both periods same format | Diff two snapshots of the same kind (409 if incompatible) | Yes |

**Response envelope** (data endpoints): `AnalyticsResponse` = `{data: [...], provenance:
{as_of, source, methodology_version, pipeline_run_id, limitations}, page: {limit, offset,
returned} | null}`.

**Authentication**: the `Authorization` header (optionally `Bearer `-prefixed) is compared to
the configured token with a constant-time check. No token configured → `503`; wrong/missing
token → `401`. Every request emits a structured audit record and an `X-Request-ID` response
header.

**Launch**: console script `sbir-analytics-api` (`sbir_analytics.api.__main__:main`) runs
uvicorn on `SBIR_ANALYTICS_API_HOST` (default `0.0.0.0`) / `SBIR_ANALYTICS_API_PORT`
(default `8000`). See [configuration](../configuration.md#analytics-api--read-only-neo4j) for
the full env-var list.

# mcp-interface - MCP Server Delta

## ADDED Requirements

### Requirement: MCP Server Endpoint
The system SHALL expose an MCP-compliant server so AI copilots can discover SBIR ETL tools and resources.

#### Scenario: Start MCP server over HTTP
- **WHEN** a developer runs `poetry run sbir-etl-mcp serve --host 0.0.0.0 --port 9000`
- **THEN** the process starts an MCP server that advertises version metadata and available tools/resources
- **AND** responds to `GET /manifest` (or stdio manifest request) within 2 seconds with JSON describing the interface

#### Scenario: Dockerized MCP service
- **WHEN** `docker compose up mcp-server` executes
- **THEN** the container waits for Dagster + Neo4j health checks
- **AND** exposes the MCP endpoint on the configured port for other services/clients

### Requirement: Dagster Asset Resources
The MCP server SHALL provide read-only resources that describe Dagster assets, their metadata, and most recent materializations.

#### Scenario: List assets resource
- **WHEN** a client requests the `sbir-assets` resource
- **THEN** the server returns an array of asset descriptors (key, stage, last_run_status, upstream_keys)
- **AND** the response is cached for ≤30 seconds to avoid overwhelming Dagster

#### Scenario: Asset detail fetch
- **WHEN** a client requests a specific asset by key
- **THEN** the server returns last run timestamp, result summary, and materialization URL so copilots can link to Dagster UI

### Requirement: Dagster Action Triggers
The MCP server SHALL expose a tool/action that triggers Dagster materialization jobs with validated parameters.

#### Scenario: Trigger single asset run
- **WHEN** a client invokes `run_asset` with `{ "asset_key": "raw_sbir_awards" }`
- **THEN** the server validates the key, calls Dagster’s job launcher, and returns a run ID
- **AND** the action times out if Dagster does not acknowledge within 10 seconds

#### Scenario: Reject unauthorized asset run
- **WHEN** a token lacking `run_asset` permission attempts to invoke the tool
- **THEN** the server returns an MCP error indicating insufficient privileges
- **AND** the audit log records the denial with timestamp and token ID

### Requirement: Configuration Resources
The MCP server SHALL deliver sanitized configuration bundles so copilots can answer questions about pipeline settings without reading local files.

#### Scenario: Fetch merged configuration
- **WHEN** a client requests `config/docker` resource
- **THEN** the server merges `config/base.yaml` + `config/docker.yaml`, redacts secrets, and returns the YAML/JSON payload

#### Scenario: Environment override inspection
- **WHEN** the client includes `environment=prod` parameter
- **THEN** the server loads the corresponding override file and highlights differing keys in the response metadata

### Requirement: Direct Neo4j Query Interface
The MCP server SHALL offer a controlled tool for executing parameterized Cypher queries against Neo4j so copilots can inspect graph data directly.

#### Scenario: Read-only query execution
- **WHEN** a client invokes `neo4j_query` with `{ "cypher": "MATCH (c:Company) RETURN c.name LIMIT 5" }`
- **THEN** the server validates that the statement is read-only (no WRITE/CREATE/DELETE)
- **AND** executes it against Neo4j, returning rows plus summary statistics in JSON
- **AND** enforces a 5-second query timeout

#### Scenario: Parameterized query with bindings
- **WHEN** a client provides `{ "cypher": "MATCH (a:Award) WHERE a.phase = $phase RETURN count(*)", "params": { "phase": "II" } }`
- **THEN** the server passes the parameters to Neo4j, preventing string interpolation attacks
- **AND** logs the query metadata (duration, row count) for observability

### Requirement: Authentication & Rate Limiting
All MCP requests SHALL be authenticated via API tokens defined in configuration, and the server SHALL enforce per-token rate limits to protect backend services.

#### Scenario: Valid token access
- **WHEN** a client supplies `Authorization: Bearer <token>` matching `config/mcp.yaml`
- **THEN** the request proceeds and the server attaches the token’s identity to the audit log

#### Scenario: Rate limit exceeded
- **WHEN** a client exceeds the configured limit (e.g., 60 requests/min)
- **THEN** subsequent requests receive an MCP error with `retry_after` metadata
- **AND** the server continues to serve other clients unaffected

# Add Model Context Protocol Interface

## Why

Analysts increasingly rely on AI copilots that speak the Model Context Protocol (MCP) to manage data pipelines, yet SBIR ETL currently exposes only Dagster UI and CLI tooling. Without an MCP server the application cannot be wired into Anthropic Claude Desktop, Cursor, or other MCP-enabled assistants, so:

- Team members must leave their AI workspace to run ETL commands, inspect asset health, or retrieve SBIR metrics.
- There is no structured way for copilots to enumerate SBIR assets, read configuration snapshots, or trigger idempotent runs; everything requires shell access.
- Infrastructure guards (auth, rate limits, audit logs) cannot be enforced because ad-hoc scripts bypass a unified gateway.

Providing an MCP server gives every developer a consistent, secure interface that copilots can call to inspect pipeline state, run targeted jobs, and answer SBIR-specific questions from the same knowledge graph.

## What Changes

- **Python MCP server** implemented under `src/mcp/server.py` using the `mcp` reference SDK. It exposes capabilities for:
  - Listing Dagster assets with metadata (status, last materialization, upstream dependencies).
  - Triggering asset materialization or DB sync jobs with structured parameters.
  - Reading configuration bundles (`config/base.yaml`, env-specific overrides) as resources.
  - Surfacing health summaries (recent runs, metrics, Neo4j status) via MCP prompts/tools.
- **Direct Neo4j access** through a safe MCP action that runs parameterized Cypher queries against Neo4j and returns tabular/graph JSON so copilots can inspect graph data without SSHing into the database host.
- **Authentication & policy layer** that loads allowed operations/users from `config/mcp.yaml`, supports API tokens, and rate limits long-running commands.
- **Deployment wrappers** so the MCP server can run:
  - Inside the existing Docker image (new entrypoint `scripts/docker/mcp-server.sh`).
  - As a Poetry script for local development (`poetry run sbir-etl-mcp serve`).
- **Documentation & onboarding** describing how to register the MCP endpoint with Claude Desktop / Cursor, which resources and actions are available, and how secrets are managed.

## Impact

### Affected Specs
- **mcp-interface** *(new)*: Formalizes requirements for the MCP server, supported resources/actions, auth, and observability.

### Affected Code
- `pyproject.toml`: add `mcp>=0.1.0`, `fastapi` (for optional HTTP transport), and `uvicorn` dependencies.
- `src/mcp/`: new package containing `server.py`, `auth.py`, `resources/`, `actions/`, and `clients/dagster.py` / `clients/neo4j.py` helpers.
- `scripts/docker/mcp-server.sh`: container entrypoint.
- `config/mcp.yaml` plus updates to `config/README.md`.
- `Makefile` / `README` instructions for `make mcp-serve` or similar.
- GitHub Actions update to run MCP unit tests + linting.

### Dependencies
- `mcp` reference Python SDK.
- `fastapi` + `uvicorn` for hosting the MCP server over HTTP/WebSocket.
- Optional `redis` dependency (Docker profile) if rate-limiting/backoff needs durable state.

### Risks & Mitigations
- **Unauthorized access**: require explicit API tokens and document network boundaries; add integration tests that reject missing/invalid tokens.
- **Long-running Dagster jobs**: enforce concurrency + timeout when triggering runs via MCP; surface job IDs so callers can poll later.
- **Spec drift**: add contract tests verifying each MCP tool/resource returns JSON that conforms to documented schemas.

### Out of Scope
- Full RBAC or multi-tenant policy engine (single tenant with token-based auth is sufficient initially).
- Conversational agent logic; MCP server only exposes tools/resources for external copilots.

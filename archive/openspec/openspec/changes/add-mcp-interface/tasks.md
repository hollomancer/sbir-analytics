# Implementation Tasks

## 1. Dependencies & Scaffolding
- [ ] 1.1 Add `mcp`, `fastapi`, and `uvicorn` dependencies to `pyproject.toml`; lock via Poetry.
- [ ] 1.2 Create `src/mcp/__init__.py` plus submodules `server.py`, `auth.py`, `resources/`, `actions/`, `clients/` with placeholders.
- [ ] 1.3 Add `scripts/mcp/__init__.py` or console entry point (`sbir_etl_mcp = "mcp.server:cli"`).

## 2. Dagster & Neo4j Clients
- [ ] 2.1 Implement `clients/dagster.py` utilities to list assets, fetch run metadata, and trigger materializations via Dagster GraphQL / Python APIs.
- [ ] 2.2 Implement `clients/neo4j.py` to run health queries (node counts, last sync) with configurable timeouts.
- [ ] 2.3 Add unit tests with fixtures that mock Dagster and Neo4j responses.

## 3. MCP Resources & Tools
- [ ] 3.1 Implement `resources/assets.py` to expose Dagster assets as MCP resources (metadata, dependencies, last run).
- [ ] 3.2 Implement `resources/config.py` that concatenates YAML sources and returns sanitized configuration bundles.
- [ ] 3.3 Implement `actions/run_asset.py` to trigger Dagster materialization jobs with parameters (asset key, run tags).
- [ ] 3.4 Implement `actions/pipeline_health.py` to summarize recent run success, failure counts, and Neo4j connectivity.
- [ ] 3.5 Implement `actions/neo4j_query.py` that executes parameterized Cypher queries, enforces read-only defaults, and returns rows/graph JSON.
- [ ] 3.6 Register all resources/actions with the MCP server manifest so clients auto-discover them.

## 4. Authentication & Policy
- [ ] 4.1 Add `config/mcp.yaml` describing tokens, allowed actions per token, rate limits, and default timeouts.
- [ ] 4.2 Implement token validation inside `auth.py`, including constant-time comparisons and structured audit logs.
- [ ] 4.3 Add middleware that enforces rate limits (in-memory to start) and logs denials.
- [ ] 4.4 Document secret management expectations in `config/README.md` + `.env.example` (e.g., `MCP_API_TOKEN`).

## 5. Serving & Deployment
- [ ] 5.1 Implement CLI (`python -m mcp.server serve`) with options for host, port, transport (stdio vs HTTP), and config path.
- [ ] 5.2 Create `scripts/docker/mcp-server.sh` entrypoint plus Compose service wiring (ports, health checks, depends_on Dagster + Neo4j).
- [ ] 5.3 Update README + `docs/deployment/containerization.md` with MCP usage instructions and diagrams.
- [ ] 5.4 Add Make targets (`make mcp-serve`, `make mcp-test`).

## 6. Testing & Observability
- [ ] 6.1 Add unit tests covering each MCP resource/action schema, auth failures, and Dagster client error handling.
- [ ] 6.2 Create integration test that spins up the MCP server with mocked clients and performs tool/resource discovery + invocation.
- [ ] 6.3 Wire tests into CI, ensuring coverage is reported.
- [ ] 6.4 Add structured logging hooks (JSON logs) and OpenTelemetry-ready spans for MCP requests.

# MCP Agent Tools Implementation Plan

## Executive Summary

Transform the SBIR Analytics application's features into MCP (Model Context Protocol) tools, enabling AI agents (Claude Desktop, Cursor, etc.) to query SBIR data, inspect pipeline state, and interact with the knowledge graph via a local stdio-based MCP server.

**Priority:** Query/Search tools first, then pipeline operations and analysis tools in later phases.

---

## Current State Analysis

### Existing Infrastructure (Ready to Reuse)

The codebase already has well-factored service layers that can be wrapped directly as MCP tools:

| Component | Location | MCP Tool Potential |
|-----------|----------|-------------------|
| `DagsterClient` | `src/cli/integration/dagster_client.py` | Asset listing, status, run history |
| `Neo4jClient` | `src/cli/integration/neo4j_client.py` | Health checks, statistics, Cypher queries |
| `MetricsCollector` | `src/cli/integration/metrics_collector.py` | Performance metrics, pipeline health |
| `FreshnessStore` | `src/utils/enrichment_freshness.py` | Enrichment staleness tracking |
| `PipelineConfig` | `src/config/schemas.py` | Configuration inspection |
| Neo4j Loaders | `src/loaders/neo4j/` | Query builders for all entity types |

### Existing MCP Spec (`.kiro/specs/mcp_interface/`)

A prior design spec exists with requirements, architecture, and task list. This plan **builds on** that spec but refines it with:
- Phased delivery focusing on query tools first
- Concrete tool definitions with JSON schemas
- Reuse of existing CLI integration clients (no new Dagster GraphQL client needed)
- Simplified auth for local-first deployment (stdio mode)

### Key Insight: Reuse CLI Integration Layer

The CLI's `CommandContext` pattern (`src/cli/context.py`) already initializes `DagsterClient`, `Neo4jClient`, and `MetricsCollector` with proper config loading. The MCP server can use **the same pattern** to bootstrap its service dependencies, avoiding duplication.

---

## Architecture

```
┌─────────────────────┐
│  AI Agent (Claude    │
│  Desktop / Cursor)   │
└─────────┬───────────┘
          │ stdio (JSON-RPC)
          ▼
┌─────────────────────┐
│   MCP Server        │
│   src/mcp/server.py │
│                     │
│  ┌───────────────┐  │
│  │  Tool Router  │  │
│  └───┬───┬───┬───┘  │
│      │   │   │      │
│  ┌───┴┐ ┌┴──┐ ┌┴──┐ │
│  │Q/S │ │Ops│ │Ana│ │     Q/S = Query/Search
│  │Tools│ │   │ │   │ │     Ops = Pipeline Operations
│  └──┬─┘ └─┬─┘ └─┬─┘ │     Ana = Analysis
│     │     │     │    │
│  ┌──┴─────┴─────┴──┐│
│  │  Service Layer   ││  ◄── Reuses src/cli/integration/*
│  │  (Shared Context)││
│  └──┬────┬────┬────┘│
└─────┼────┼────┼─────┘
      │    │    │
      ▼    ▼    ▼
   Neo4j  Dagster  DuckDB/Files
```

### Module Layout

```
src/mcp/
├── __init__.py
├── server.py              # MCP server entry point, tool registration
├── context.py             # MCPContext (mirrors CLI CommandContext)
├── config.py              # MCP-specific config (loaded from config/mcp.yaml)
├── tools/
│   ├── __init__.py
│   ├── search.py          # Phase 1: Query/Search tools
│   ├── pipeline.py        # Phase 2: Pipeline operation tools
│   └── analysis.py        # Phase 3: Analysis tools
└── resources/
    ├── __init__.py
    └── assets.py           # MCP resources (read-only data endpoints)
```

---

## Phase 1: Query/Search Tools (Priority)

### 1.1 — Core Infrastructure

**Task:** Set up MCP server skeleton with stdio transport

- Add `mcp` SDK dependency to `pyproject.toml` (`mcp[cli]>=1.0.0`)
- Create `src/mcp/server.py` — initialize MCP server using the `mcp` Python SDK (`FastMCP`)
- Create `src/mcp/context.py` — `MCPContext` class that mirrors `CommandContext.create()`, initializing `DagsterClient`, `Neo4jClient`, `MetricsCollector` from `PipelineConfig`
- Create `config/mcp.yaml` — MCP-specific settings (query timeouts, result limits, allowed query patterns)
- Add console entry point: `sbir-mcp = "src.mcp.server:main"` in `pyproject.toml`
- Add `make mcp-serve` target to Makefile

**Files to create:**
- `src/mcp/__init__.py`
- `src/mcp/server.py`
- `src/mcp/context.py`
- `src/mcp/config.py`
- `config/mcp.yaml`

**Files to modify:**
- `pyproject.toml` (add `mcp` dependency + entry point)
- `Makefile` (add `mcp-serve` target)

### 1.2 — SBIR Award Search Tool

**Tool:** `search_sbir_awards`

Wraps Neo4j queries against the SBIRAward/Award nodes. Provides full-text search across award titles, abstracts, company names, and topic descriptions.

```json
{
  "name": "search_sbir_awards",
  "description": "Search SBIR/STTR awards by keyword, company, agency, year range, or award ID. Returns matching awards with key metadata.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Free-text search across titles, abstracts, and topics"},
      "company_name": {"type": "string", "description": "Filter by company name (fuzzy match)"},
      "agency": {"type": "string", "description": "Filter by awarding agency (e.g., DOD, HHS, NASA)"},
      "year_start": {"type": "integer", "description": "Start year for award date range"},
      "year_end": {"type": "integer", "description": "End year for award date range"},
      "program": {"type": "string", "enum": ["SBIR", "STTR"], "description": "Filter by program type"},
      "phase": {"type": "string", "enum": ["Phase I", "Phase II", "Phase III"], "description": "Filter by phase"},
      "limit": {"type": "integer", "default": 25, "description": "Max results to return (max 100)"}
    }
  }
}
```

**Implementation:** Builds parameterized Cypher queries using `Neo4jClient.execute_query()`. Uses existing `src/loaders/neo4j/query_builder.py` patterns where applicable.

### 1.3 — Company Lookup Tool

**Tool:** `lookup_company`

Queries the Company nodes in Neo4j, returning company details, associated awards, and patent counts.

```json
{
  "name": "lookup_company",
  "description": "Look up a company by name or UEI/DUNS identifier. Returns company profile, award history summary, and patent count.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "Company name (fuzzy matched)"},
      "uei": {"type": "string", "description": "Unique Entity Identifier"},
      "duns": {"type": "string", "description": "DUNS number"},
      "include_awards": {"type": "boolean", "default": false, "description": "Include award summary"},
      "include_patents": {"type": "boolean", "default": false, "description": "Include patent summary"}
    }
  }
}
```

### 1.4 — Neo4j Graph Query Tool

**Tool:** `query_knowledge_graph`

Direct parameterized Cypher access for advanced queries. Read-only with timeout enforcement.

```json
{
  "name": "query_knowledge_graph",
  "description": "Execute a read-only Cypher query against the SBIR knowledge graph. Use for custom queries not covered by other tools. Returns structured JSON results.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "cypher": {"type": "string", "description": "Cypher query (read-only, no CREATE/DELETE/SET)"},
      "parameters": {"type": "object", "description": "Query parameters (use $param syntax in query)"},
      "limit": {"type": "integer", "default": 50, "description": "Max rows returned (max 500)"}
    },
    "required": ["cypher"]
  }
}
```

**Security:** Validates read-only (reuses `Neo4jClient` write-keyword check), adds configurable timeout, enforces result limit.

### 1.5 — Database Statistics Tool

**Tool:** `get_database_stats`

Wraps `Neo4jClient.get_statistics()` and `Neo4jClient.health_check()`.

```json
{
  "name": "get_database_stats",
  "description": "Get Neo4j database statistics: node counts by label, relationship counts by type, and connection health.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "include_health": {"type": "boolean", "default": true, "description": "Include connection health status"},
      "include_counts": {"type": "boolean", "default": true, "description": "Include node/relationship counts"}
    }
  }
}
```

### 1.6 — Asset Status Tool

**Tool:** `get_asset_status`

Wraps `DagsterClient.list_assets()` and `DagsterClient.get_asset_status()`.

```json
{
  "name": "get_asset_status",
  "description": "Get Dagster pipeline asset status. Lists all assets or checks status of a specific asset.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "asset_key": {"type": "string", "description": "Specific asset key to check (omit for all assets)"},
      "group": {"type": "string", "description": "Filter assets by group name"}
    }
  }
}
```

### 1.7 — Pipeline Metrics Tool

**Tool:** `get_pipeline_metrics`

Wraps `MetricsCollector.get_metrics()` and `get_latest_metrics()`.

```json
{
  "name": "get_pipeline_metrics",
  "description": "Get pipeline performance metrics: success rates, throughput, memory usage, and error counts.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "start_date": {"type": "string", "format": "date", "description": "Start date (YYYY-MM-DD)"},
      "end_date": {"type": "string", "format": "date", "description": "End date (YYYY-MM-DD)"},
      "asset_group": {"type": "string", "description": "Filter by asset group"},
      "latest_only": {"type": "boolean", "default": false, "description": "Return only latest aggregated metrics"}
    }
  }
}
```

### 1.8 — Graph Schema Resource

**MCP Resource (not a tool):** `sbir://schema`

Exposes the Neo4j graph schema as a readable resource so agents understand what entities and relationships exist before querying.

**Implementation:** Reads from `docs/schemas/neo4j.md` and returns structured schema information (node labels, relationship types, key properties).

### 1.9 — Testing & Documentation

- Unit tests for each tool with mocked `Neo4jClient`/`DagsterClient`
- Integration test: start MCP server, call tools via `mcp` client SDK
- Add MCP configuration instructions to `docs/deployment/`
- Add Claude Desktop `claude_desktop_config.json` example snippet

---

## Phase 2: Pipeline Operation Tools (Future)

These wrap the CLI's `ingest` and `enrich` command functionality:

| Tool | Wraps | Risk Level |
|------|-------|------------|
| `trigger_ingestion` | `DagsterClient.trigger_materialization()` | High — mutates state |
| `trigger_enrichment` | Enrich command logic | High — mutates state |
| `check_enrichment_freshness` | `FreshnessStore.get_stale_records()` | Low — read-only |
| `get_run_status` | `DagsterClient.get_run_status()` | Low — read-only |
| `list_recent_runs` | `DagsterClient.list_recent_runs()` | Low — read-only |

Phase 2 tools that trigger pipeline runs will require confirmation prompts (MCP `confirmation` field) and optional auth tokens.

---

## Phase 3: Analysis Tools (Future)

Expose the specialized analysis capabilities:

| Tool | Source Module | Description |
|------|--------------|-------------|
| `detect_transitions` | `src/assets/transition/` | Search for technology transition indicators |
| `classify_cet` | `src/assets/cet/` | Classify awards by Critical & Emerging Technology area |
| `find_similar_patents` | `src/assets/specter2/` | Find patents similar to a given award using SPECTER2 embeddings |
| `analyze_fiscal_impact` | `src/assets/fiscal_assets.py` | Get economic impact estimates for awards |
| `detect_ma_activity` | `src/assets/ma_detection.py` | Check for M&A activity affecting companies |

---

## Implementation Order (Phase 1 Tasks)

| # | Task | Depends On | Est. Complexity |
|---|------|-----------|-----------------|
| 1 | Core infrastructure: MCP server, context, config, entry point | — | Medium |
| 2 | `get_database_stats` tool | Task 1 | Low |
| 3 | `get_asset_status` tool | Task 1 | Low |
| 4 | `get_pipeline_metrics` tool | Task 1 | Low |
| 5 | `search_sbir_awards` tool | Task 1 | Medium |
| 6 | `lookup_company` tool | Task 1 | Medium |
| 7 | `query_knowledge_graph` tool (with security) | Task 1 | Medium |
| 8 | `sbir://schema` resource | Task 1 | Low |
| 9 | Unit + integration tests | Tasks 2-8 | Medium |
| 10 | Documentation + Claude Desktop config example | Tasks 2-8 | Low |

### Rationale for Order

- Tasks 2-4 are thin wrappers around existing clients — quick wins that validate the MCP infrastructure works
- Tasks 5-6 require building Cypher query templates — more design work
- Task 7 is the most powerful but needs careful security controls
- Task 8 gives agents schema awareness to write better queries

---

## Technical Decisions

### Why `FastMCP` (from `mcp` SDK)?
- Official Python SDK for MCP, well-maintained
- Handles JSON-RPC protocol, stdio transport, tool/resource registration automatically
- Avoids reimplementing protocol details

### Why Reuse CLI Integration Clients?
- `DagsterClient`, `Neo4jClient`, `MetricsCollector` already handle connection management, error handling, and data formatting
- Avoids code duplication and divergence
- CLI and MCP server share the same `PipelineConfig` loader

### Why stdio Transport First (Not HTTP)?
- User chose "Local CLI agent" deployment
- Claude Desktop and Cursor use stdio-based MCP servers
- Simpler — no auth/CORS/rate-limiting needed for local use
- HTTP can be added in Phase 4 (from original spec) if needed

### Security for `query_knowledge_graph`
- Reject queries containing write keywords (CREATE, DELETE, SET, REMOVE, MERGE)
- Enforce configurable query timeout (default: 30s)
- Enforce result row limit (default: 500)
- Log all queries for audit
- Future: allowlist of query patterns

---

## Configuration

`config/mcp.yaml`:
```yaml
mcp:
  server:
    name: "sbir-analytics"
    version: "0.1.0"
    transport: "stdio"

  query:
    default_timeout_seconds: 30
    max_result_rows: 500
    max_search_results: 100

  security:
    allow_write_queries: false
    blocked_cypher_keywords:
      - CREATE
      - DELETE
      - SET
      - REMOVE
      - MERGE
      - DROP
      - DETACH

  logging:
    level: "INFO"
    audit_queries: true
```

## Claude Desktop Integration

Example `claude_desktop_config.json` snippet:
```json
{
  "mcpServers": {
    "sbir-analytics": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/sbir-analytics", "sbir-mcp"],
      "env": {
        "SBIR_ETL__NEO4J__URI": "neo4j://localhost:7687"
      }
    }
  }
}
```

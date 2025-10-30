# Requirements Document

## Introduction

This specification implements Add Model Context Protocol Interface.

Analysts increasingly rely on AI copilots that speak the Model Context Protocol (MCP) to manage data pipelines, yet SBIR ETL currently exposes only Dagster UI and CLI tooling. Without an MCP server the application cannot be wired into Anthropic Claude Desktop, Cursor, or other MCP-enabled assistants, so:

- Team members must leave their AI workspace to run ETL commands, inspect asset health, or retrieve SBIR metrics.
- There is no structured way for copilots to enumerate SBIR assets, read configuration snapshots, or trigger idempotent runs; everything requires shell access.
- Infrastructure guards (auth, rate limits, audit logs) cannot be enforced because ad-hoc scripts bypass a unified gateway.

Providing an MCP server gives every developer a consistent, secure interface that copilots can call to inspect pipeline state, run targeted jobs, and answer SBIR-specific questions from the same knowledge graph.

## Glossary

- **MCP**: System component or technology referenced in the implementation
- **SBIR**: System component or technology referenced in the implementation
- **ETL**: System component or technology referenced in the implementation
- **CLI**: System component or technology referenced in the implementation
- **SDK**: System component or technology referenced in the implementation
- **JSON**: System component or technology referenced in the implementation
- **API**: System component or technology referenced in the implementation
- **src/mcp/server.py**: Code component or file: src/mcp/server.py
- **mcp**: Code component or file: mcp
- **config/base.yaml**: Code component or file: config/base.yaml
- **config/mcp.yaml**: Code component or file: config/mcp.yaml
- **scripts/docker/mcp-server.sh**: Code component or file: scripts/docker/mcp-server.sh
- **poetry run sbir-etl-mcp serve**: Code component or file: poetry run sbir-etl-mcp serve
- **Python MCP server**: Key concept: Python MCP server
- **Direct Neo4j access**: Key concept: Direct Neo4j access
- **Authentication & policy layer**: Key concept: Authentication & policy layer
- **Deployment wrappers**: Key concept: Deployment wrappers
- **Documentation & onboarding**: Key concept: Documentation & onboarding

## Requirements

### Requirement 1

**User Story:** As a developer, I want add model context protocol interface, so that analysts increasingly rely on ai copilots that speak the model context protocol (mcp) to manage data pipelines, yet sbir etl currently exposes only dagster ui and cli tooling.

#### Acceptance Criteria

1. THE System SHALL implement model context protocol interface
2. THE System SHALL validate the implementation of model context protocol interface

### Requirement 2

**User Story:** As a developer, I want **Python MCP server** implemented under `src/mcp/server.py` using the `mcp` reference SDK. It exposes capabilities for:, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL implement **python mcp server** implemented under `src/mcp/server.py` using the `mcp` reference sdk. it exposes capabilities for:
2. THE System SHALL validate the implementation of **python mcp server** implemented under `src/mcp/server.py` using the `mcp` reference sdk. it exposes capabilities for:

### Requirement 3

**User Story:** As a developer, I want Listing Dagster assets with metadata (status, last materialization, upstream dependencies), so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support listing dagster assets with metadata (status, last materialization, upstream dependencies)
2. THE System SHALL ensure proper operation of listing dagster assets with metadata (status, last materialization, upstream dependencies)

### Requirement 4

**User Story:** As a developer, I want Triggering asset materialization or DB sync jobs with structured parameters, so that support the enhanced functionality described in the proposal.

#### Acceptance Criteria

1. THE System SHALL support triggering asset materialization or db sync jobs with structured parameters
2. THE System SHALL ensure proper operation of triggering asset materialization or db sync jobs with structured parameters


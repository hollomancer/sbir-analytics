# Requirements Document

## Introduction

This specification implements a Model Context Protocol (MCP) interface for the SBIR ETL system.

Analysts increasingly rely on AI copilots that speak the Model Context Protocol (MCP) to manage data pipelines, yet SBIR ETL currently exposes only Dagster UI and CLI tooling. Without an MCP server the application cannot be wired into Anthropic Claude Desktop, Cursor, or other MCP-enabled assistants, so:

- Team members must leave their AI workspace to run ETL commands, inspect asset health, or retrieve SBIR metrics.
- There is no structured way for copilots to enumerate SBIR assets, read configuration snapshots, or trigger idempotent runs; everything requires shell access.
- Infrastructure guards (auth, rate limits, audit logs) cannot be enforced because ad-hoc scripts bypass a unified gateway.

Providing an MCP server gives every developer a consistent, secure interface that copilots can call to inspect pipeline state, run targeted jobs, and answer SBIR-specific questions from the same knowledge graph.

## Glossary

- **MCP_Server**: Python-based Model Context Protocol server implementation
- **SBIR_ETL_System**: The existing SBIR analytics ETL pipeline system
- **Dagster_Assets**: Pipeline assets managed by Dagster orchestration
- **Neo4j_Database**: Graph database storing SBIR analytics data
- **AI_Copilot**: MCP-enabled AI assistants like Claude Desktop or Cursor
- **Authentication_Token**: Security token for MCP server access control
- **Asset_Materialization**: Dagster operation to execute and update pipeline assets
- **Pipeline_Health**: Status information about ETL pipeline operations and data quality

## Requirements

### Requirement 1

**User Story:** As an analyst, I want to access SBIR ETL functionality through my AI copilot, so that I can manage data pipelines without leaving my AI workspace.

#### Acceptance Criteria

1. THE MCP_Server SHALL expose SBIR_ETL_System capabilities through Model Context Protocol interface
2. THE MCP_Server SHALL support connection from AI_Copilot applications
3. THE MCP_Server SHALL provide structured access to Dagster_Assets without requiring shell access
4. THE MCP_Server SHALL enforce Authentication_Token validation for all requests

### Requirement 2

**User Story:** As a developer, I want to query Dagster asset information through MCP, so that AI copilots can inspect pipeline state and metadata.

#### Acceptance Criteria

1. THE MCP_Server SHALL provide resource endpoints for listing Dagster_Assets with metadata
2. WHEN queried for asset information, THE MCP_Server SHALL return asset status, last materialization timestamp, and upstream dependencies
3. THE MCP_Server SHALL expose asset execution history and quality metrics
4. THE MCP_Server SHALL provide configuration snapshots for pipeline inspection

### Requirement 3

**User Story:** As a developer, I want to trigger pipeline operations through MCP, so that AI copilots can execute ETL jobs with proper parameters.

#### Acceptance Criteria

1. THE MCP_Server SHALL provide action endpoints for triggering Asset_Materialization operations
2. WHEN receiving materialization requests, THE MCP_Server SHALL validate structured parameters before execution
3. THE MCP_Server SHALL support triggering database synchronization jobs with appropriate safeguards
4. THE MCP_Server SHALL return execution status and job identifiers for tracking

### Requirement 4

**User Story:** As a developer, I want to query Neo4j data through MCP, so that AI copilots can answer SBIR-specific questions from the knowledge graph.

#### Acceptance Criteria

1. THE MCP_Server SHALL provide action endpoints for executing parameterized Neo4j queries
2. THE MCP_Server SHALL enforce read-only query restrictions by default for security
3. WHEN executing queries, THE MCP_Server SHALL return results in structured JSON format
4. THE MCP_Server SHALL implement query timeouts and result size limits

### Requirement 5

**User Story:** As a system administrator, I want MCP server security controls, so that pipeline access is properly authenticated and audited.

#### Acceptance Criteria

1. THE MCP_Server SHALL implement Authentication_Token validation with configurable policies
2. THE MCP_Server SHALL enforce rate limiting per Authentication_Token to prevent abuse
3. THE MCP_Server SHALL log all requests with timestamps, tokens, and actions for audit trails
4. THE MCP_Server SHALL support both stdio and HTTP transport modes for different deployment scenarios

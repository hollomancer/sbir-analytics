# MCP Interface Design Document

## Overview

This document outlines the design for implementing a Model Context Protocol (MCP) server that exposes SBIR ETL system capabilities to AI copilots. The MCP server will provide structured access to Dagster assets, Neo4j data queries, and pipeline operations through a standardized protocol interface.

The design follows MCP specification patterns with resource discovery, action execution, and proper authentication/authorization controls. The server will support both stdio and HTTP transport modes to accommodate different deployment scenarios.

## Architecture

### High-Level Architecture

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AI Copilot    │◄──►│   MCP Server    │◄──►│  SBIR ETL Core  │
│ (Claude/Cursor) │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                        │
                              │                        ▼
                              │               ┌─────────────────┐
                              │               │     Dagster     │
                              │               │   (GraphQL/API) │
                              │               └─────────────────┘
                              │                        │
                              ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Auth & Rate   │    │     Neo4j       │
                       │    Limiting     │    │   Database      │
                       └─────────────────┘    └─────────────────┘
```

### Component Architecture

```text
src/mcp/
├── server.py           # MCP server implementation & CLI
├── auth.py             # Token validation & rate limiting
├── resources/          # MCP resource endpoints
│   ├── assets.py       # Dagster asset metadata
│   └── config.py       # Configuration snapshots
├── actions/            # MCP action endpoints
│   ├── run_asset.py    # Asset materialization
│   ├── pipeline_health.py # Health checks
│   └── neo4j_query.py  # Graph queries
└── clients/            # Backend integrations
    ├── dagster.py      # Dagster GraphQL client
    └── neo4j.py        # Neo4j query client
```

## Components and Interfaces

### MCP Server Core (`server.py`)

### Responsibilities:

- MCP protocol implementation (stdio/HTTP transport)
- Resource and action registration
- Request routing and response handling
- Error handling and logging

### Key Interfaces:

```python
class MCPServer:
    def __init__(self, config: MCPConfig)
    def register_resources(self, resources: List[MCPResource])
    def register_actions(self, actions: List[MCPAction])
    def serve_stdio(self) -> None
    def serve_http(self, host: str, port: int) -> None
```

**Design Rationale:** Centralized server implementation allows for consistent protocol handling and easy transport mode switching.

### Authentication & Authorization (`auth.py`)

### Responsibilities:

- Token validation with constant-time comparison
- Rate limiting per token
- Audit logging for security events
- Permission checking for actions

### Key Interfaces:

```python
class AuthManager:
    def validate_token(self, token: str) -> AuthResult
    def check_rate_limit(self, token: str) -> bool
    def log_request(self, token: str, action: str, result: str)
    def has_permission(self, token: str, action: str) -> bool
```

**Design Rationale:** Separate authentication component enables security policy enforcement and audit trail maintenance without coupling to MCP protocol details.

### Resource Endpoints

#### Asset Resources (`resources/assets.py`)

**Purpose:** Expose Dagster asset metadata as MCP resources for discovery and inspection.

### Resource Schema:

```python
@dataclass
class AssetResource:
    asset_key: str
    status: str  # "materialized", "failed", "never_materialized"
    last_materialization: Optional[datetime]
    upstream_dependencies: List[str]
    metadata: Dict[str, Any]
    run_history: List[Dict[str, Any]]
```

**Design Rationale:** Asset resources provide read-only access to pipeline state, enabling AI copilots to understand current system status without execution permissions.

#### Configuration Resources (`resources/config.py`)

**Purpose:** Provide sanitized configuration snapshots for system inspection.

### Resource Schema:

```python
@dataclass
class ConfigResource:
    config_name: str
    sanitized_config: Dict[str, Any]  # Secrets removed
    last_updated: datetime
    environment: str
```

**Design Rationale:** Configuration resources enable troubleshooting and system understanding while maintaining security by removing sensitive values.

### Action Endpoints

#### Asset Materialization (`actions/run_asset.py`)

**Purpose:** Trigger Dagster asset materialization with proper parameter validation.

### Action Schema:

```python
@dataclass
class RunAssetAction:
    asset_key: str
    run_tags: Optional[Dict[str, str]] = None
    partition_key: Optional[str] = None

@dataclass
class RunAssetResult:
    run_id: str
    status: str
    started_at: datetime
    asset_key: str
```

**Design Rationale:** Structured asset execution enables controlled pipeline operations with proper tracking and parameter validation.

#### Pipeline Health (`actions/pipeline_health.py`)

**Purpose:** Provide comprehensive system health information including recent runs and database connectivity.

### Action Schema:

```python
@dataclass
class PipelineHealthResult:
    overall_status: str  # "healthy", "degraded", "unhealthy"
    dagster_status: Dict[str, Any]
    neo4j_status: Dict[str, Any]
    recent_runs: List[Dict[str, Any]]
    quality_metrics: Dict[str, float]
```

**Design Rationale:** Centralized health checking enables AI copilots to assess system state and make informed decisions about operations.

#### Neo4j Queries (`actions/neo4j_query.py`)

**Purpose:** Execute parameterized Cypher queries with security controls and result formatting.

### Action Schema:

```python
@dataclass
class Neo4jQueryAction:
    query: str
    parameters: Dict[str, Any]
    read_only: bool = True
    timeout_seconds: Optional[int] = None

@dataclass
class Neo4jQueryResult:
    records: List[Dict[str, Any]]
    summary: Dict[str, Any]
    execution_time_ms: int
    record_count: int
```

**Design Rationale:** Parameterized queries with read-only defaults provide secure access to graph data while preventing accidental modifications.

### Backend Clients

#### Why Both Dagster and Neo4j?

### Dagster Integration:

- **Pipeline Operations**: Dagster manages the ETL pipeline orchestration, asset materialization, and run tracking
- **Operational Metadata**: Asset status, execution history, dependencies, and quality metrics
- **Execution Control**: Triggering new pipeline runs, monitoring progress, and managing asset lifecycle

### Neo4j Integration:

- **Business Data Queries**: Access to the processed SBIR data, company relationships, patent chains, and CET classifications
- **Graph Analytics**: Complex relationship queries that span companies, awards, patents, and technology areas
- **Domain Knowledge**: The actual business intelligence that analysts need for SBIR ecosystem analysis

**Design Rationale**: Dagster handles "how the system works" (pipeline operations), while Neo4j provides "what the system knows" (business data and relationships). AI copilots need both operational control and data access.

#### Dagster Client (`clients/dagster.py`)

### Responsibilities:

- GraphQL API communication with Dagster
- Asset metadata retrieval
- Run triggering and status monitoring
- Error handling and retry logic

### Key Methods:

```python
class DagsterClient:
    def list_assets(self) -> List[AssetMetadata]
    def get_asset_status(self, asset_key: str) -> AssetStatus
    def trigger_materialization(self, asset_key: str, **kwargs) -> RunResult
    def get_run_status(self, run_id: str) -> RunStatus
```

**Design Rationale:** Dedicated client abstracts Dagster API complexity and provides consistent error handling across MCP operations. This enables AI copilots to understand and control the ETL pipeline state.

#### Neo4j Client (`clients/neo4j.py`)

### Responsibilities:

- Neo4j driver management
- Query execution with timeouts
- Result formatting and error handling
- Connection health monitoring

### Key Methods:

```python
class Neo4jClient:
    def execute_query(self, query: str, parameters: Dict) -> QueryResult
    def health_check(self) -> HealthStatus
    def get_node_counts(self) -> Dict[str, int]
    def validate_read_only(self, query: str) -> bool
```

**Design Rationale:** Separate Neo4j client enables query validation, timeout management, and consistent result formatting. This provides AI copilots with access to the business intelligence and relationship data that analysts need for SBIR ecosystem analysis.

## Data Models

### Configuration Schema

```python
@dataclass
class MCPConfig:
    # Server configuration
    server: ServerConfig

    # Authentication settings
    auth: AuthConfig

    # Rate limiting
    rate_limits: RateLimitConfig

    # Backend connections
    dagster: DagsterConfig
    neo4j: Neo4jConfig

@dataclass
class AuthConfig:
    tokens: Dict[str, TokenConfig]  # token -> permissions
    audit_log_path: str

@dataclass
class TokenConfig:
    name: str
    permissions: List[str]  # ["read_assets", "run_assets", "query_neo4j"]
    rate_limit_per_minute: int
```

**Design Rationale:** Structured configuration enables flexible permission management and deployment-specific customization.

### MCP Protocol Models

```python
@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mime_type: str

@dataclass
class MCPAction:
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema

@dataclass
class MCPRequest:
    method: str
    params: Dict[str, Any]

@dataclass
class MCPResponse:
    result: Optional[Any] = None
    error: Optional[MCPError] = None
```

**Design Rationale:** Standard MCP protocol models ensure compatibility with MCP-enabled AI copilots and tools.

## Error Handling

### Error Categories

1. **Authentication Errors**: Invalid tokens, rate limit exceeded
2. **Validation Errors**: Invalid parameters, malformed requests
3. **Backend Errors**: Dagster API failures, Neo4j connection issues
4. **System Errors**: Configuration problems, resource exhaustion

### Error Response Format

```python
@dataclass
class MCPError:
    code: int
    message: str
    details: Optional[Dict[str, Any]] = None

## Standard error codes

class ErrorCodes:
    AUTHENTICATION_FAILED = 401
    RATE_LIMIT_EXCEEDED = 429
    VALIDATION_ERROR = 400
    BACKEND_ERROR = 502
    SYSTEM_ERROR = 500
```

**Design Rationale:** Structured error handling with standard HTTP codes enables proper client-side error handling and debugging.

### Retry and Fallback Strategy

- **Transient Backend Errors**: Exponential backoff retry (max 3 attempts)
- **Rate Limiting**: Return 429 with retry-after header
- **Authentication Failures**: Immediate rejection with audit logging
- **System Errors**: Graceful degradation where possible

## Testing Strategy

### Unit Testing

**Scope:** Individual components in isolation
- Authentication logic with mock tokens
- Resource/action handlers with mock backends
- Configuration validation and loading
- Error handling scenarios

**Tools:** pytest with fixtures for mock clients

### Integration Testing

**Scope:** Component interactions with real backends
- MCP server with live Dagster instance
- Neo4j client with test database
- End-to-end request/response cycles
- Authentication and rate limiting

**Tools:** pytest with containerized dependencies

### Security Testing

**Scope:** Authentication and authorization controls
- Token validation edge cases
- Rate limiting effectiveness
- Query injection prevention
- Audit logging completeness

**Tools:** Custom security test suite

### Performance Testing

**Scope:** Response times and resource usage
- Concurrent request handling
- Large query result processing
- Memory usage under load
- Rate limiting accuracy

**Tools:** pytest-benchmark for performance regression detection

## Security Considerations

### Authentication Security

- **Constant-time token comparison** prevents timing attacks
- **Secure token storage** in configuration with environment variable support
- **Audit logging** for all authentication events
- **Token rotation support** through configuration updates

### Query Security

- **Read-only query validation** prevents data modification
- **Parameterized queries** prevent injection attacks
- **Query timeouts** prevent resource exhaustion
- **Result size limits** prevent memory exhaustion

### Rate Limiting

- **Per-token rate limits** prevent abuse
- **Sliding window implementation** for accurate limiting
- **Graceful degradation** under high load
- **Rate limit bypass for health checks**

### Network Security

- **HTTPS support** for HTTP transport mode
- **Input validation** for all request parameters
- **Output sanitization** for configuration resources
- **Error message sanitization** to prevent information leakage

## Deployment Considerations

### Transport Modes

### stdio Mode:

- Direct integration with AI copilots
- Process-based communication
- Suitable for local development and desktop tools

### HTTP Mode:

- Network-accessible service
- Load balancer compatible
- Suitable for server deployments and web integrations

### Configuration Management

- **Environment-specific configs** in `config/mcp.yaml`
- **Secret management** through environment variables
- **Configuration validation** on startup
- **Hot reload support** for non-security settings

### Monitoring and Observability

- **Structured logging** with request correlation IDs
- **Metrics collection** for request rates and response times
- **Health check endpoints** for load balancer integration
- **Audit trail** for security and compliance

### Scalability

- **Stateless design** enables horizontal scaling
- **Connection pooling** for backend services
- **Async request handling** for improved throughput
- **Resource cleanup** for long-running operations

## Implementation Phases

### Phase 1: Core Infrastructure

- MCP server framework with stdio transport
- Basic authentication and configuration loading
- Dagster and Neo4j client implementations

### Phase 2: Resource Endpoints

- Asset metadata resources
- Configuration snapshot resources
- Resource discovery and enumeration

### Phase 3: Action Endpoints

- Asset materialization actions
- Pipeline health actions
- Neo4j query actions with security controls

### Phase 4: Production Features

- HTTP transport mode
- Rate limiting and audit logging
- Comprehensive error handling and monitoring

### Phase 5: Advanced Features

- Permission-based action filtering
- Query result caching
- Performance optimization and load testing

## Related Requirements

This design addresses all requirements from the requirements document:

- **Requirement 1**: MCP server exposes SBIR ETL capabilities through standard protocol
- **Requirement 2**: Resource endpoints provide Dagster asset information and metadata
- **Requirement 3**: Action endpoints enable pipeline operations with parameter validation
- **Requirement 4**: Neo4j query actions provide secure graph data access
- **Requirement 5**: Authentication, rate limiting, and audit logging ensure security

The modular design enables incremental implementation while maintaining security and extensibility for future enhancements.

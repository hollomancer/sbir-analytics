# Design Document

## Overview

The Rich CLI Interface provides a comprehensive command-line interface for the SBIR analytics pipeline using Typer for command structure and Rich for enhanced visual output. The design emphasizes developer experience, real-time feedback, and seamless integration with the existing Dagster-based pipeline architecture.

## Architecture

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Application                          │
├─────────────────────────────────────────────────────────────────┤
│  Typer App (main.py)                                          │
│  ├── Command Router                                            │
│  ├── Configuration Loader                                      │
│  └── Error Handler                                             │
├─────────────────────────────────────────────────────────────────┤
│                     Command Modules                            │
│  ├── IngestCommand     ├── EnrichCommand    ├── StatusCommand  │
│  ├── MetricsCommand    ├── DashboardCommand                    │
├─────────────────────────────────────────────────────────────────┤
│                    Display Components                          │
│  ├── ProgressTracker   ├── MetricsDisplay   ├── StatusDisplay  │
│  ├── DashboardLayout   ├── ErrorFormatter                      │
├─────────────────────────────────────────────────────────────────┤
│                    Integration Layer                           │
│  ├── DagsterClient     ├── Neo4jClient      ├── ConfigLoader   │
│  ├── AssetMonitor      ├── MetricsCollector                    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Command Input
    ↓
Command Parsing (Typer)
    ↓
Configuration Loading
    ↓
Pipeline Integration (Dagster API)
    ↓
Progress Tracking (Rich Progress)
    ↓
Result Display (Rich Console)
```

## Components and Interfaces

### 1. CLI Application Structure

**Main Application (`src/cli/main.py`)**
- Typer app instance with command registration
- Global configuration and error handling
- Consistent styling and theming

**Command Interface Pattern**
```python
@dataclass
class CommandContext:
    config: PipelineConfig
    console: Console
    dagster_client: DagsterClient
    neo4j_client: Neo4jClient
```

### 2. Command Modules

**Ingest Command (`src/cli/commands/ingest.py`)**
- Triggers data extraction and loading operations
- Supports asset group targeting and dry-run mode
- Real-time progress tracking for long operations

**Enrich Command (`src/cli/commands/enrich.py`)**
- Executes enrichment workflows with source selection
- Batch processing with progress visualization
- Success rate monitoring and reporting

**Status Command (`src/cli/commands/status.py`)**
- Asset materialization status display
- Neo4j health and connection testing
- Quality gate violation reporting

**Metrics Command (`src/cli/commands/metrics.py`)**
- Performance metrics collection and display
- Time-range filtering and export capabilities
- Resource utilization statistics

**Dashboard Command (`src/cli/commands/dashboard.py`)**
- Interactive real-time monitoring interface
- Keyboard navigation and hotkey support
- Auto-refresh with configurable intervals

### 3. Display Components

**Progress Tracker (`src/cli/display/progress.py`)**
- Rich Progress integration with custom columns
- Multi-task progress support for parallel operations
- Error handling and graceful termination

**Metrics Display (`src/cli/display/metrics.py`)**
- Formatted tables and charts for metrics data
- Color-coded indicators for thresholds
- Export functionality for data analysis

**Status Display (`src/cli/display/status.py`)**
- Asset status visualization with icons
- Health indicators and warning highlights
- Summary statistics formatting

**Dashboard Layout (`src/cli/display/dashboard.py`)**
- Live updating terminal interface
- Panel-based layout with Rich Layout
- Keyboard event handling for interactivity

### 4. Integration Layer

**Dagster Client (`src/cli/integration/dagster_client.py`)**
- Dagster GraphQL API integration
- Asset execution and monitoring
- Run tracking and status queries

**Neo4j Client (`src/cli/integration/neo4j_client.py`)**
- Database health monitoring
- Statistics collection for dashboard
- Connection validation and testing

**Metrics Collector (`src/cli/integration/metrics_collector.py`)**
- Performance data aggregation
- Historical metrics retrieval
- Real-time monitoring support

## Data Models

### Command Options Model
```python
@dataclass
class IngestOptions:
    asset_groups: List[str] = field(default_factory=list)
    dry_run: bool = False
    force_refresh: bool = False
    chunk_size: Optional[int] = None

@dataclass
class EnrichOptions:
    sources: List[str] = field(default_factory=list)
    batch_size: Optional[int] = None
    confidence_threshold: Optional[float] = None

@dataclass
class MetricsOptions:
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    asset_group: Optional[str] = None
    export_format: str = "table"
```

### Display Models
```python
@dataclass
class AssetStatus:
    name: str
    status: str  # "success", "failed", "running", "not_started"
    last_run: Optional[datetime]
    duration: Optional[timedelta]
    records_processed: Optional[int]

@dataclass
class PipelineMetrics:
    enrichment_success_rate: float
    processing_throughput: float
    memory_usage_mb: float
    error_count: int
    last_updated: datetime
```

## Error Handling

### Error Categories
- **Configuration Errors**: Invalid YAML, missing credentials
- **Connection Errors**: Neo4j, Dagster API unavailable
- **Execution Errors**: Asset failures, timeout issues
- **User Input Errors**: Invalid commands, missing arguments

### Error Display Strategy
- Rich-formatted error messages with context
- Suggested fixes and troubleshooting steps
- Exit codes for scripting integration
- Detailed logging for debugging

## Testing Strategy

### Unit Testing
- Command parsing and validation logic
- Display component formatting and layout
- Integration client mocking and error handling
- Configuration loading and validation

### Integration Testing
- End-to-end command execution with test data
- Dagster API integration with test instances
- Neo4j connectivity and query testing
- Progress tracking with simulated operations

### User Experience Testing
- CLI usability and help text clarity
- Progress bar accuracy and responsiveness
- Dashboard layout and keyboard navigation
- Error message clarity and actionability

## Performance Considerations

### Responsive Design
- Async operations for non-blocking UI updates
- Efficient data polling with configurable intervals
- Memory-conscious display updates for large datasets
- Graceful degradation for slow connections

### Resource Management
- Connection pooling for database clients
- Caching for frequently accessed metrics
- Lazy loading for dashboard components
- Cleanup handlers for interrupted operations

## Security Considerations

### Credential Management
- Environment variable integration for secrets
- No credential storage in CLI history
- Secure connection handling for APIs
- Configuration validation for security settings

### Input Validation
- Command argument sanitization
- Path traversal prevention for file operations
- SQL injection prevention for query parameters
- Rate limiting for API operations

## Configuration Integration

### YAML Configuration Support
- Reuse existing PipelineConfig structure
- Environment variable override support
- Profile-based configuration selection
- Validation with clear error messages

### CLI-Specific Settings
```yaml
cli:
  # Display settings
  theme: "default"  # "default", "dark", "light"
  progress_refresh_rate: 0.1  # seconds
  dashboard_refresh_rate: 10  # seconds
  
  # Output settings
  max_table_rows: 50
  truncate_long_text: true
  show_timestamps: true
  
  # Performance settings
  api_timeout_seconds: 30
  max_concurrent_operations: 4
  cache_metrics_seconds: 60
```

## Deployment and Distribution

### Installation Method
- Poetry-based installation as development dependency
- Entry point configuration for `sbir-cli` command
- Optional system-wide installation support
- Docker container integration for containerized workflows

### Cross-Platform Support
- Windows, macOS, and Linux compatibility
- Terminal capability detection and adaptation
- Unicode and color support detection
- Graceful fallback for limited terminals
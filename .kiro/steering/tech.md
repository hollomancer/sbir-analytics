# Technology Stack & Build System

## 🎉 Consolidated Architecture (2025-01-01)

The technology stack has been streamlined through major consolidation efforts:
- ✅ **Single Docker Compose**: Profile-based configuration replaces multiple files
- ✅ **Unified Configuration**: Hierarchical PipelineConfig with standardized patterns
- ✅ **Consolidated Assets**: Single files replace multiple scattered implementations
- ✅ **Streamlined Build**: Optimized Docker build process and dependency management

## Core Technologies

### Language & Runtime
- **Python 3.11+** (supports up to 3.12)
- **Poetry** for dependency management and packaging

### Key Frameworks & Libraries
- **Dagster 1.7+**: Asset-based pipeline orchestration and observability
- **Pydantic 2.8+**: Type-safe configuration and data validation
- **DuckDB 1.0+**: High-performance analytical database for CSV/PostgreSQL processing
- **Neo4j 5.x**: Graph database for storing relationships and entities
- **Pandas 2.2+**: Data manipulation and analysis
- **RapidFuzz 3.0+**: Fast fuzzy string matching for entity resolution

### Development Tools
- **Black**: Code formatting (line length 100, Python 3.11 target)
- **Ruff**: Fast Python linter with comprehensive rule set
- **MyPy**: Static type checking with strict configuration
- **Bandit**: Security vulnerability scanning
- **Pytest**: Testing framework with coverage reporting

### Infrastructure
- **Docker & Docker Compose**: Containerized development and deployment
- **Neo4j 5.x**: Graph database (provided via Docker Compose)

## Common Commands

### Development Setup
```bash
# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Start local services (Neo4j) - Consolidated Docker Compose
make neo4j-up
# or use profile-based configuration
docker-compose --profile dev up -d neo4j
```

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check . --fix

# Type checking
mypy src/

# Security scan
bandit -r src/

# Run all quality checks
make lint  # if available, or run individually
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest -m "not slow"  # Skip slow tests
```

### Pipeline Execution
```bash
# Start Dagster UI
poetry run dagster dev
# Open http://localhost:3000

# Run specific jobs via CLI
dagster job execute -f src/definitions.py -j sbir_ingestion_job
dagster job execute -f src/definitions.py -j cet_full_pipeline_job
dagster job execute -f src/definitions.py -j fiscal_returns_mvp_job
dagster job execute -f src/definitions.py -j fiscal_returns_full_job

# Container-based development
make docker-up-dev
make cet-pipeline-dev  # Run CET pipeline in container
```

### Container Operations
```bash
# Build and start development stack
make docker-build
make docker-up-dev

# Run tests in container
make docker-test

# View logs
make docker-logs SERVICE=app

# Execute commands in container
make docker-exec SERVICE=app CMD="poetry run pytest"
```

### Data Pipeline Commands
```bash
# Transition Detection MVP (local)
make transition-mvp-run
make transition-mvp-clean

# Neo4j operations
make neo4j-up
make neo4j-down
make neo4j-reset  # Fresh Neo4j instance
```

## Configuration System

### Three-layer Configuration
- `config/base.yaml`: Default settings (version controlled)
- `config/dev.yaml`: Development overrides
- `config/prod.yaml`: Production settings

### Environment Variable Overrides
```bash
# Format: SBIR_ETL__SECTION__KEY=value
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__ENRICHMENT__MATCH_RATE_THRESHOLD=0.75
```

## Build & Deployment

### Docker Multi-stage Build
- Development profile: Bind mounts for live code editing
- Production profile: Optimized image without dev dependencies
- Test profile: Isolated testing environment

### CI/CD Workflows
- **Standard CI**: Lint, test, security scan on push/PR
- **Container CI**: Docker build and test (8-12 min runtime)
- **Performance Regression**: Benchmark comparison on enrichment changes
- **Neo4j Integration**: Database connectivity and schema validation

## Related Documents

- **[product.md](product.md)** - Project overview and key features
- **[structure.md](structure.md)** - Project organization and code structure
- **[configuration-patterns.md](configuration-patterns.md)** - Environment variable configuration examples
- **[pipeline-orchestration.md](pipeline-orchestration.md)** - Dagster orchestration and development workflow
- **[quick-reference.md](quick-reference.md)** - Common commands quick reference
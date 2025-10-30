# Implementation Tasks

## 1. Project Scaffolding
- [x] 1.1 Create directory structure (src/, config/, tests/, data/)
- [x] 1.2 Initialize Poetry with pyproject.toml
- [x] 1.3 Create .gitignore (data/, logs/, .env, __pycache__, etc.)
- [x] 1.4 Create basic README.md with setup instructions
- [x] 1.5 Create Dockerfile for application container

## 2. Configuration Management
- [x] 2.1 Create config/ directory with base.yaml, dev.yaml, prod.yaml
- [x] 2.2 Implement Pydantic schemas in src/config/schemas.py
  - [x] 2.2.1 DataQualityConfig model
  - [x] 2.2.2 EnrichmentConfig model
  - [x] 2.2.3 Neo4jConfig model
  - [x] 2.2.4 PipelineConfig root model
- [x] 2.3 Implement configuration loader in src/config/loader.py
  - [x] 2.3.1 YAML file loading with environment selection
  - [x] 2.3.2 Environment variable override logic
  - [x] 2.3.3 Configuration caching with lru_cache
- [x] 2.4 Create config/README.md with documentation and examples
- [x] 2.5 Write unit tests for configuration loading and validation

## 3. Structured Logging Setup
- [x] 3.1 Implement logging configuration in src/utils/logging_config.py
  - [x] 3.1.1 Console handler with pretty formatting
  - [x] 3.1.2 File handler with JSON formatting
  - [x] 3.1.3 Daily log rotation
- [x] 3.2 Implement context variables for stage and run_id tracking
- [x] 3.3 Create log_with_context context manager
- [x] 3.4 Write unit tests for logging configuration

## 4. Data Models
- [x] 4.1 Create Pydantic models in src/models/
  - [x] 4.1.1 Award model (award.py)
  - [x] 4.1.2 Company model (company.py)
  - [x] 4.1.3 Researcher model (researcher.py)
  - [x] 4.1.4 Patent model (patent.py)
- [x] 4.2 Implement QualityReport and QualityIssue models
- [x] 4.3 Implement EnrichmentResult model
- [x] 4.4 Write unit tests for model validation

## 5. Data Quality Framework
- [x] 5.1 Create validation module in src/validators/
  - [x] 5.1.1 Implement schema validation functions
  - [x] 5.1.2 Implement completeness checks
  - [x] 5.1.3 Implement uniqueness checks
  - [x] 5.1.4 Implement value range validation
- [x] 5.2 Implement QualitySeverity enum and QualityIssue dataclass
- [x] 5.3 Implement validate_sbir_awards function with configurable thresholds
- [x] 5.4 Write comprehensive unit tests for validators

## 6. Pipeline Stage Structure
- [x] 6.1 Create src/extractors/ directory with __init__.py
  - [x] 6.1.1 Create placeholder for SBIR CSV extractor (sbir.py)
  - [x] 6.1.2 Create placeholder for USAspending DuckDB extractor (usaspending.py)
- [x] 6.2 Create src/validators/ directory with __init__.py
- [x] 6.3 Create src/enrichers/ directory with __init__.py
- [x] 6.4 Create src/transformers/ directory with __init__.py
- [x] 6.5 Create src/loaders/ directory with __init__.py
- [x] 6.6 Create DuckDB utilities in src/utils/duckdb_client.py
  - [x] 6.6.1 Postgres dump import helper
  - [x] 6.6.2 CSV query helper
  - [x] 6.6.3 Connection management
- [x] 6.7 Create placeholder modules for future implementation

## 7. Dagster Setup
- [x] 7.1 Install Dagster and dagster-webserver dependencies
- [x] 7.2 Create src/assets/ directory
- [x] 7.3 Create Dagster repository definition (src/__init__.py or src/definitions.py)
- [x] 7.4 Implement example asset with dependency (e.g., raw_data → validated_data)
- [x] 7.5 Implement example asset check for data quality
- [ ] 7.6 Test Dagster UI launches successfully (requires Python 3.11-3.13 environment)

## 8. Neo4j Client Setup
- [x] 8.1 Implement Neo4j client wrapper in src/loaders/neo4j_client.py
  - [x] 8.1.1 Connection management with context manager
  - [x] 8.1.2 Batch write support
  - [x] 8.1.3 Transaction management
- [x] 8.2 Implement index and constraint creation utilities
- [x] 8.3 Implement upsert helpers for nodes and relationships
- [x] 8.4 Write integration tests for Neo4j client (requires test database)

## 9. Metrics and Monitoring
- [x] 9.1 Implement MetricsCollector class in src/utils/metrics.py
- [x] 9.2 Implement PipelineMetrics dataclass
- [x] 9.3 Add metrics collection to asset execution context
- [x] 9.4 Implement metrics persistence to JSON
- [x] 9.5 Write unit tests for metrics collection

## 10. Testing Infrastructure
- [x] 10.1 Create tests/unit/ directory structure
- [x] 10.2 Create tests/integration/ directory structure
- [x] 10.3 Create tests/e2e/ directory structure
- [x] 10.4 Create tests/fixtures/ directory with sample data
- [x] 10.5 Configure pytest with pytest.ini or pyproject.toml
- [x] 10.6 Set up test coverage reporting (pytest-cov)

## 11. Code Quality Tools
- [x] 11.1 Configure black in pyproject.toml (line length: 100)
- [x] 11.2 Configure ruff in pyproject.toml or ruff.toml
- [x] 11.3 Configure mypy in pyproject.toml or mypy.ini
- [ ] 11.4 Create pre-commit hooks (optional)
- [x] 11.5 Document code quality commands in README

## 12. Docker and Deployment
- [x] 12.1 Create Dockerfile with multi-stage build for application
- [x] 12.2 Create docker-compose.yml for local development with services:
  - [x] 12.2.1 Neo4j service (graph database)
  - [x] 12.2.2 Application service (ETL pipeline)
- [x] 12.3 Configure volume mounts for data directory (SBIR CSV, USAspending dump, DuckDB files)
- [x] 12.4 Create .dockerignore
- [x] 12.5 Create volumes for persistent data (Neo4j)
- [x] 12.6 Test Docker Compose startup and service connectivity (docker-compose.yml validated)
- [ ] 12.7 Document Docker usage and data setup (SBIR CSV + USAspending dump) in README (pending live testing)

## 13. Documentation
- [x] 13.1 Update README.md with:
  - [x] 13.1.1 Project overview and architecture diagram
  - [x] 13.1.2 Setup instructions
  - [x] 13.1.3 Configuration guide
  - [x] 13.1.4 Development workflow
  - [x] 13.1.5 Testing instructions
- [x] 13.2 Create CONTRIBUTING.md with development guidelines
- [x] 13.3 Add inline code documentation (docstrings)

## 14. Integration and Validation
- [ ] 14.1 Run full test suite and verify ≥85% coverage (requires Python 3.11-3.13)
- [x] 14.2 Run black, ruff, and mypy to verify code quality
- [ ] 14.3 Test Dagster UI with example assets (requires Python 3.11-3.13)
- [x] 14.4 Test configuration loading with different environments (integration tests written)
- [x] 14.5 Test Docker build and container execution (docker-compose.yml validated)
- [ ] 14.6 Verify structured logging output (console and JSON) (requires Python 3.11-3.13)

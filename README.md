# SBIR ETL Pipeline

A robust, consolidated ETL pipeline for processing SBIR program data into a Neo4j graph database for analysis and visualization.

## Quick Start

### Choose Your Journey

#### 1. Local Developer (No Cloud)
**Best for:** Code contributions, local testing, and offline work.

1.  **Clone and Install:**
    ```bash
    git clone <repository-url>
    cd sbir-analytics
    make install
    ```

2.  **Configure Local Environment:**
    ```bash
    make setup-local
    # Creates .env with local defaults (no S3, local Neo4j)
    ```

3.  **Run the Pipeline:**
    ```bash
    make dev
    # Open http://localhost:3000
    ```

#### 2. Cloud Developer
**Best for:** Production debugging, working with full datasets (S3), and cloud deployment.

1.  **Clone and Install:**
    ```bash
    git clone <repository-url>
    cd sbir-analytics
    make install
    ```

2.  **Configure Cloud Environment:**
    ```bash
    make setup-cloud
    # Enables S3 usage. Ensure AWS credentials are set in your environment.
    ```

### Production Deployment

The SBIR ETL pipeline supports multiple production deployment strategies optimized for different use cases:

**Cloud-First Architecture:**
- **Orchestration**: Dagster Cloud Solo Plan or AWS Step Functions
- **Compute**: Dagster Cloud managed or AWS Lambda
- **Storage**: AWS S3 (primary data storage)
- **Database**: Neo4j Aura (cloud-hosted graph database)
- **Secrets**: AWS Secrets Manager

#### Option A: Dagster Cloud (Recommended for Primary ETL)

**Best for:** Full ETL pipeline orchestration, asset management, observability

**Quick Start:**
1. Create account at [cloud.dagster.io](https://cloud.dagster.io) (30-day free trial)
2. Connect GitHub repository
3. Configure code location: `src.definitions` (Python 3.11)
4. Set environment variables (see [Dagster Cloud Overview](docs/deployment/dagster-cloud-overview.md))
5. Deploy automatically on git push

**Deployment Methods:**
- **UI-Based**: Best for initial setup ([guide](docs/deployment/dagster-cloud-deployment-guide.md))
- **CLI-Based**: Best for CI/CD ([guide](docs/deployment/dagster-cloud-deployment-guide.md#5-setup-cli-based-serverless-deployment))

**Cost:** $10/month Solo Plan

#### Option B: AWS Step Functions + Lambda (Recommended for Scheduled Workflows)

**Best for:** Weekly SBIR data refresh, scheduled data downloads

**Architecture:**
- **Step Functions**: Orchestrates workflow
- **Lambda Functions**: Execute processing steps (download, validate, profile)
- **S3**: Stores data and artifacts
- **Secrets Manager**: Stores credentials

**Quick Deploy:**
```bash
cd infrastructure/cdk
pip install -r requirements.txt
cdk deploy --all
```

**Full Guide:** [AWS Serverless Deployment Guide](docs/deployment/aws-serverless-deployment-guide.md)

### Container Development (Alternative)

For containerized development with Docker Compose:

```bash
cp .env.example .env
# Edit .env: set NEO4J_USER, NEO4J_PASSWORD (for local Neo4j if not using Aura)
make docker-build
make docker-up-dev
# Open http://localhost:3000 and materialize the assets
```

See [`docs/deployment/containerization.md`](docs/deployment/containerization.md) for full details.

**Note**: Docker Compose is recommended for local development and serves as a failover option for production.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data (SBIR.gov CSV, USAspending PostgreSQL dump, USPTO patent DTAs)
2. **Validate**: Schema validation and data quality checks
3. **Enrich**: Augment data with fuzzy matching and external enrichment
4. **Transform**: Business logic and graph-ready entity preparation
5. **Load**: Write to Neo4j with idempotent operations and relationship chains

### Key Features

- **Cloud-First Architecture**: AWS S3 + Lambda + Neo4j Aura for production deployment
- **Dagster Orchestration**: Asset-based pipeline with dependency management and observability
- **Dagster Cloud**: Primary orchestration platform (fully managed, $10/month Solo Plan)
- **AWS Lambda**: Serverless compute for scheduled data refresh workflows
- **Neo4j Aura**: Cloud-hosted graph database for production (free tier available)
- **S3 Data Lake**: Primary data storage with automatic fallback to local filesystem
- **DuckDB Processing**: Efficient querying of CSV and PostgreSQL dump data
- **Pydantic Configuration**: Type-safe YAML configuration with environment overrides
- **Docker Deployment**: Local development and testing environment (secondary option)
- **Iterative Enrichment Refresh**: Automatic freshness tracking and refresh for enrichment data

### Major Systems

The SBIR ETL pipeline includes several specialized analysis systems:

#### Transition Detection System

Identifies SBIR-funded companies that transitioned research into federal procurement contracts using six independent signals. Achieves ≥85% precision with ~40,000-80,000 detected transitions.

**Learn more**: [`docs/transition/overview.md`](docs/transition/overview.md)

**Quick start**:
```bash
# Run transition detection
uv run python -m dagster job execute -f src/definitions.py -j transition_full_job
```

#### CET Classification System

Classifies SBIR awards into Critical and Emerging Technology (CET) areas using machine learning. Enables technology trend analysis and portfolio assessment.

**Learn more**: [`docs/ml/README.md`](docs/ml/README.md)

**Quick start**:
```bash
# Run CET classification
dagster job execute -f src/definitions.py -j cet_full_pipeline_job
```

#### Fiscal Returns Analysis

Calculates return on investment (ROI) of SBIR funding using economic input-output modeling (StateIO). Estimates federal tax receipts generated from economic impacts.

**Configuration**: `config/fiscal/`
**Documentation**: `docs/fiscal/`

#### Patent Analysis

Tracks USPTO patents linked to SBIR awards, including patent assignments, ownership chains, and technology transfer analysis.

**Schema**: [`docs/schemas/patent-neo4j-schema.md`](docs/schemas/patent-neo4j-schema.md)
**Data Dictionary**: [`docs/data/dictionaries/uspto-patent-data-dictionary.md`](docs/data/dictionaries/uspto-patent-data-dictionary.md)

## Documentation

Comprehensive documentation is organized by topic:

- **Testing**: [`docs/testing/`](docs/testing/README.md) - Testing guides, environment setup, and coverage analysis
- **Deployment**: [`docs/deployment/`](docs/deployment/README.md) - Dagster Cloud and Docker deployment guides
- **Transition Detection**: [`docs/transition/`](docs/transition/README.md) - Technology transition detection system
- **Machine Learning**: [`docs/ml/`](docs/ml/README.md) - CET classifier and ML integration
- **Architecture**: [`docs/architecture/`](docs/architecture/detailed-overview.md) - System architecture and design patterns
- **Schemas**: [`docs/schemas/`](docs/schemas/neo4j.md) - Neo4j graph schema documentation
- **Data Sources**: `docs/data/` - Data dictionaries and source documentation
- **Specifications**: `.kiro/specs/` - Kiro specification system (see `AGENTS.md` for workflow guidance)

For a complete documentation map, see [`docs/index.md`](docs/index.md).

## Project Structure

```
sbir-analytics/
├── src/                    # Source code (assets, extractors, loaders, etc.)
├── tests/                  # Unit, integration, and E2E tests
├── docs/                   # Documentation
├── config/                 # YAML configuration files
├── .kiro/                  # Kiro specifications
└── archive/                # Archived content
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for a detailed breakdown of the project structure.

## Neo4j Graph Model

The Neo4j graph database stores entities and relationships for comprehensive analysis.

### Key Node Types

- `Award` — SBIR/STTR awards with company, agency, phase, amount
- `Organization` — Companies, universities, and research institutions
- `Individual` — Researchers and key personnel
- `Patent` — USPTO patents linked to SBIR-funded research
- `Transition` — Detected technology transitions to federal contracts
- `CETArea` — Critical and Emerging Technology areas

### Key Relationship Types

- `RECEIVED` — Organization → Award
- `PARTICIPATED_IN` — Individual → Award
- `GENERATED_FROM` — Patent → Award (SBIR-funded patents)
- `OWNS` — Organization → Patent
- `TRANSITIONED_TO` — Award → Transition → Contract
- `INVOLVES_TECHNOLOGY` — Award/Transition → CETArea

### Example Queries

See [`docs/schemas/neo4j.md`](docs/schemas/neo4j.md) for example Cypher queries and full schema documentation.

## Configuration

Configuration is managed through YAML files with environment variable overrides.

### Configuration Files

- `config/base.yaml` - Base pipeline configuration
- `config/transition/` - Transition detection settings
- `config/cet/` - CET classifier settings
- `config/fiscal/` - Fiscal analysis settings

### Environment Variable Overrides

Override any configuration using the pattern: `SBIR_ETL__SECTION__KEY`

```bash
# Example: Override Neo4j connection
export SBIR_ETL__NEO4J__URI="neo4j+s://your-instance.databases.neo4j.io"
export SBIR_ETL__NEO4J__USER="neo4j"
export SBIR_ETL__NEO4J__PASSWORD="your-password"  # pragma: allowlist secret

# Example: Override transition detection threshold
export SBIR_ETL__TRANSITION__DETECTION__HIGH_CONFIDENCE_THRESHOLD=0.88
```

**Full configuration guide**: [`docs/architecture/detailed-overview.md`](docs/architecture/detailed-overview.md)

## Testing
The project uses pytest with comprehensive test coverage.

```bash
make test
```

**Testing guide**: [`docs/testing/README.md`](docs/testing/README.md)

## Continuous Integration

GitHub Actions workflows provide comprehensive CI/CD:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to main/develop, PRs | Standard CI (lint, test, security) |
| `container-ci.yml` | Push to main/develop, PRs | Docker build + test |
| `neo4j-smoke.yml` | Push to main/develop, PRs | Neo4j integration tests |
| `performance-regression-check.yml` | PRs (enrichment changes) | Benchmark + regression detection |
| `cet-pipeline-ci.yml` | Push to main/develop, PRs | CET pipeline validation |
| `secret-scan.yml` | Push to main/develop, PRs | Secret leak detection |

## Error Handling

The pipeline uses a comprehensive exception hierarchy. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/development/exception-handling.md`](docs/development/exception-handling.md) for details.

## Contributing

1. Follow code quality standards (black, ruff, mypy, bandit)
2. Write tests for new functionality (≥80% coverage)
3. Update documentation as needed
4. Use Kiro specs for architectural changes (see `.kiro/specs/` and `AGENTS.md` for workflow)
5. Ensure performance regression checks pass in CI

**Contributing guide**: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Acknowledgments

This project makes use of and is grateful for the following open-source tools and research:

- **[StateIO](https://github.com/USEPA/stateior)** - State-level economic input-output modeling framework by USEPA
- **[Bayesian Mixture-of-Experts](https://www.arxiv.org/abs/2509.23830)** - Research on calibration and uncertainty estimation in classifier routing by Albus Yizhuo Li
- **[PaECTER](https://huggingface.co/mpi-inno-comp/paecter)** - Patent similarity model by Max Planck Institute for Innovation and Competition
- @SquadronConsult for help getting the SAM.gov data working

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.

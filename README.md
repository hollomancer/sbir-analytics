# SBIR ETL Pipeline

A robust, consolidated ETL pipeline for processing SBIR program data into a Neo4j graph database for analysis and visualization.

## Quick Start

### Local Development Setup (Recommended)

#### Prerequisites

- **Python**: 3.11 or 3.12
- **uv**: For dependency management ([install uv](https://github.com/astral-sh/uv))
- **Neo4j Aura**: Neo4j cloud instance (Free tier available) - [Setup Guide](docs/data/neo4j-aura-setup.md)
- **R** (optional): For fiscal returns analysis with StateIO models

#### 1. Clone and Install

```bash
git clone <repository-url>
cd sbir-analytics
make install
```

#### 2. Configure Environment

Create a `.env` file from the example:

```bash
cp .env.example .env
```

**Configure Neo4j:**
- **Option A (Recommended):** Use Neo4j Aura (Cloud). Set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` in `.env`.
- **Option B (Local):** Use Docker.
  ```bash
  make neo4j-up
  # Set NEO4J_URI=bolt://localhost:7687 in .env
  ```

**Configure Data Storage:**
- **Option A (S3):** Set `SBIR_ETL_USE_S3=true` and `SBIR_ETL_S3_BUCKET=your-bucket` in `.env`.
- **Option B (Local):** Set `SBIR_ETL_USE_S3=false` (default). Data will be stored in `data/`.

#### 3. Run the Pipeline

```bash
make dev
```

Open **http://localhost:3000** to view the Dagster UI.

#### 4. Materialize Assets

1. Navigate to the **Assets** tab in the UI.
2. Click **Materialize** on desired assets (e.g., `raw_sbir_awards`).
3. Monitor progress in the **Runs** tab.

#### 5. Run Tests

```bash
make test
```

### Production Deployment (Cloud-First Architecture)

The SBIR ETL pipeline is designed for cloud deployment with the following architecture:

- **Orchestration**: Dagster Cloud Solo Plan or AWS Step Functions
- **Compute**: AWS Lambda functions (for scheduled workflows)
- **Storage**: AWS S3 (primary data storage)
- **Database**: Neo4j Aura (cloud-hosted graph database)
- **Secrets**: AWS Secrets Manager

**Deployment Guides**:
- **[Dagster Cloud Overview](docs/deployment/dagster-cloud-overview.md)** - Primary orchestration prerequisites and env vars
- **[AWS Infrastructure](docs/deployment/aws-serverless-deployment-guide.md)** - Lambda + S3 + Step Functions setup
- **[Neo4j Aura Setup](docs/data/neo4j-aura-setup.md)** - Cloud graph database configuration

### AWS Infrastructure (Production)

The weekly SBIR awards refresh workflow runs on AWS Step Functions with Lambda functions:

- **Step Functions**: Orchestrates the workflow
- **Lambda Functions**: Execute processing steps
- **S3**: Stores data and artifacts
- **Secrets Manager**: Stores Neo4j and GitHub credentials

**Deployment Guide**: [`docs/deployment/aws-serverless-deployment-guide.md`](docs/deployment/aws-serverless-deployment-guide.md)

**Quick Deploy**:
```bash
cd infrastructure/cdk
pip install -r requirements.txt
cdk deploy --all
```

### Docker Development

For containerized development with Docker Compose (recommended for new developers):

**Quick Start:**
```bash
# 1. Check prerequisites
make docker-check-prerequisites

# 2. Configure environment
cp .env.example .env
# Edit .env: set NEO4J_USER, NEO4J_PASSWORD (defaults work for local dev)

# 3. Build and start
make docker-build
make docker-up-dev

# 4. Verify setup
make docker-verify
```

**Access Services:**
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474

**Guides:**
- **[Docker Quick Start](docs/development/docker-quickstart.md)** - Step-by-step setup guide
- **[Troubleshooting](docs/development/docker-troubleshooting.md)** - Common issues and solutions
- **[Environment Setup](docs/development/docker-env-setup.md)** - Configuration guide
- **[Containerization Guide](docs/deployment/containerization.md)** - Advanced Docker usage

### Production Deployment (Dagster Cloud)

**Primary deployment method**: Dagster Cloud Solo Plan ($10/month)

#### Option A: UI-Based Deployment (Recommended for Initial Setup)

1. **Set up Dagster Cloud:**
   - Create account at [cloud.dagster.io](https://cloud.dagster.io)
   - Start 30-day free trial (no credit card required)
   - Connect GitHub repository

2. **Configure code location:**
   - Module: `src.definitions`
   - Branch: `main`
   - Python version: 3.11

3. **Set environment variables in Dagster Cloud UI** (see [Dagster Cloud Overview](docs/deployment/dagster-cloud-overview.md) for the canonical list).

4. **Deploy and verify:**
   - Dagster Cloud automatically deploys on git push
   - Verify all assets, jobs, and schedules are visible
   - Test job execution

See [`docs/deployment/dagster-cloud-overview.md`](docs/deployment/dagster-cloud-overview.md) plus the [Dagster Cloud Deployment Guide](docs/deployment/dagster-cloud-deployment-guide.md) for complete instructions.

#### Option B: CLI-Based Serverless Deployment (Recommended for CI/CD)

**Note**: Requires Docker to be running (builds Docker image).

1. **Install CLI:**
   ```bash
   pip install dagster-cloud
   # or: uv pip install dagster-cloud
   ```

2. **Authenticate:**
   ```bash
   export DAGSTER_CLOUD_API_TOKEN="your-api-token"
   dagster-cloud auth login
   ```

3. **Deploy:**
   ```bash
   dagster-cloud serverless deploy-python-executable \
     --deployment prod \
     --location-name sbir-analytics-production \
     --module-name src.definitions
   ```

See [`docs/deployment/dagster-cloud-deployment-guide.md#5-setup-cli-based-serverless-deployment`](docs/deployment/dagster-cloud-deployment-guide.md#5-setup-cli-based-serverless-deployment) for complete CLI deployment guide.

**Note**: Docker Compose remains available as a failover option for local development and emergency scenarios.

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
export SBIR_ETL__NEO4J__PASSWORD="your-password"

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

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.

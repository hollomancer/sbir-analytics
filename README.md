# SBIR ETL Pipeline

> Analyze $50B+ in SBIR/STTR funding data: Track technology transitions, patent outcomes, and economic impact of federal R&D investments.

[![CI](https://github.com/your-org/sbir-analytics/workflows/CI/badge.svg)](https://github.com/your-org/sbir-analytics/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What This Does

- 🔍 **533K+ SBIR awards** from 1983-present across all federal agencies
- 🚀 **40K-80K technology transitions** detected using 6 independent signals
- 📊 **CET classification** for Critical & Emerging Technology trend analysis
- 💰 **Economic impact** analysis with ROI and federal tax receipt estimates
- 🔗 **Patent ownership chains** tracking SBIR-funded innovation outcomes

## Prerequisites

- **Python 3.11+** (required)
- **Docker** (optional, for local Neo4j database)
- **AWS credentials** (optional, for cloud features and S3 data)

## Quick Start

### Local Development

Get started in 2 minutes:

```bash
git clone https://github.com/your-org/sbir-analytics
cd sbir-analytics
make install      # Install dependencies with uv
make dev          # Start Dagster UI
# Open http://localhost:3000
```

**Next steps:**
1. Materialize `raw_sbir_awards` asset in Dagster UI
2. Explore data in Neo4j Browser (http://localhost:7474)
3. See [Getting Started Guide](docs/getting-started/local-development.md) for detailed walkthrough

### Production Deployment

For production use, see [Deployment Guide](docs/deployment/README.md) for:
- **Dagster Cloud** ($10/month, recommended for full ETL orchestration)
- **AWS Lambda** (serverless, recommended for scheduled data refresh)

## Key Features

### Pipeline Architecture
- **Five-stage ETL**: Extract → Validate → Enrich → Transform → Load
- **Asset-based orchestration**: Dagster with dependency management
- **Data quality gates**: Comprehensive validation at each stage
- **Cloud-first design**: AWS S3 + Neo4j Aura + Dagster Cloud

### Specialized Analysis Systems

| System | Purpose | Documentation |
|--------|---------|---------------|
| **Transition Detection** | Identify SBIR → federal contract transitions (≥85% precision) | [docs/transition/](docs/transition/) |
| **CET Classification** | ML-based technology area classification | [docs/ml/](docs/ml/) |
| **Fiscal Returns** | Economic impact & ROI analysis using StateIO | [docs/fiscal/](docs/fiscal/) |
| **Patent Analysis** | USPTO patent chains and tech transfer tracking | [docs/schemas/patent-neo4j-schema.md](docs/schemas/patent-neo4j-schema.md) |

### Technology Stack
- **Orchestration**: Dagster 1.7+ (asset-based pipeline)
- **Database**: Neo4j 5.x (graph database for relationships)
- **Processing**: DuckDB 1.0+ (analytical queries), Pandas 2.2+
- **Configuration**: Pydantic 2.8+ (type-safe YAML config)
- **Deployment**: Docker, AWS Lambda, Dagster Cloud

## Documentation

| Topic | Description |
|-------|-------------|
| [Getting Started](docs/getting-started/) | Detailed setup guides for local, cloud, and ML workflows |
| [Architecture](docs/architecture/) | System design, patterns, and technical decisions |
| [Deployment](docs/deployment/) | Production deployment options and guides |
| [Testing](docs/testing/) | Testing strategy, guides, and coverage |
| [Schemas](docs/schemas/) | Neo4j graph schema and data models |
| [API Reference](docs/api/) | Code documentation and API reference |

See [Documentation Index](docs/index.md) for complete map.

## Project Structure

```
sbir-analytics/
├── src/                    # Source code
│   ├── assets/            # Dagster asset definitions
│   ├── extractors/        # Data extraction (SBIR, USAspending, USPTO)
│   ├── enrichers/         # External enrichment and fuzzy matching
│   ├── transformers/      # Business logic and normalization
│   ├── loaders/           # Neo4j loading and relationship creation
│   └── ml/                # Machine learning (CET classification)
├── tests/                  # Unit, integration, and E2E tests
├── docs/                   # Documentation
├── config/                 # YAML configuration files
├── .kiro/                  # Kiro specifications
└── infrastructure/         # AWS CDK and deployment configs
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed breakdown.

## Common Commands

```bash
# Development
make install              # Install dependencies
make dev                  # Start Dagster UI
make test                 # Run tests
make lint                 # Run linters

# Docker (alternative)
make docker-build         # Build Docker image
make docker-up-dev        # Start development stack
make docker-test          # Run tests in container

# Data operations
make transition-mvp-run   # Run transition detection
make cet-pipeline-dev     # Run CET classification
```

See [Makefile](Makefile) for all available commands.

## Configuration

Configuration uses YAML files with environment variable overrides:

```bash
# Override any config using SBIR_ETL__SECTION__KEY pattern
export SBIR_ETL__NEO4J__URI="neo4j+s://your-instance.databases.neo4j.io"
export SBIR_ETL__ENRICHMENT__BATCH_SIZE=200
```

See [Configuration Guide](docs/configuration.md) for details.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Code quality standards (black, ruff, mypy)
- Testing requirements (≥80% coverage)
- Pull request process

## Testing

```bash
make test                 # Run all tests
make test-unit            # Unit tests only
make test-integration     # Integration tests
make test-e2e             # End-to-end tests
```

See [Testing Guide](docs/testing/README.md) for details.

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.

## Acknowledgments

This project makes use of and is grateful for the following open-source tools and research:

- **[StateIO](https://github.com/USEPA/stateior)** - State-level economic input-output modeling framework by USEPA
- **[Bayesian Mixture-of-Experts](https://www.arxiv.org/abs/2509.23830)** - Research on calibration and uncertainty estimation by Albus Yizhuo Li
- **[PaECTER](https://huggingface.co/mpi-inno-comp/paecter)** - Patent similarity model by Max Planck Institute
- **@SquadronConsult** - Help with SAM.gov data integration

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/sbir-analytics/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/sbir-analytics/discussions)
- **Documentation**: [docs/](docs/)

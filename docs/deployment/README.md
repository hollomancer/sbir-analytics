# Deployment Documentation

This directory contains comprehensive deployment documentation for the SBIR ETL project.

## Deployment Overview

The SBIR ETL project supports two deployment strategies:

1. **Dagster Cloud (Primary)** - Managed Dagster Cloud serverless deployment (recommended)
2. **Docker Compose (Failover)** - Self-hosted containerized deployment

## Quick Start

### Dagster Cloud Deployment (Recommended)

Start with these guides for Dagster Cloud deployment:

1. **[Dagster Cloud Migration Guide](dagster-cloud-migration.md)** - Comprehensive migration guide
2. **[Setup Checklist](dagster-cloud-setup-checklist.md)** - Step-by-step deployment checklist
3. **[Serverless CLI Guide](dagster-cloud-serverless-cli.md)** - CLI-based serverless deployment

### Docker Compose Deployment (Failover)

For self-hosted deployment:

- **[Containerization Guide](containerization.md)** - Docker Compose setup and configuration

## Dagster Cloud Documentation

### Setup and Configuration

- **[Dagster Cloud Migration](dagster-cloud-migration.md)** - Primary deployment guide
  - Environment setup and prerequisites
  - Secrets management
  - Configuration and deployment
  - Monitoring and troubleshooting

- **[Setup Checklist](dagster-cloud-setup-checklist.md)** - Implementation checklist
  - Step-by-step deployment tasks
  - Verification steps
  - Common issues and solutions

- **[Serverless CLI Guide](dagster-cloud-serverless-cli.md)** - CLI-based deployment
  - CLI installation and setup
  - Deployment commands
  - Code location management

### Advanced Configuration

- **[Code Locations](dagster-cloud-code-locations.md)** - Managing code locations
  - Code location structure
  - Deployment strategies
  - Version management

- **[Multiple Neo4j Instances](dagster-cloud-multiple-neo4j-instances.md)** - Multi-instance setup
  - Development, staging, and production instances
  - Instance configuration
  - Environment separation

### Testing and Quality

- **[Testing Guide](dagster-cloud-testing-guide.md)** - Testing in Dagster Cloud
  - Pre-deployment testing
  - Integration testing
  - Production validation

### Future Opportunities

- **[Cloud Migration Opportunities](cloud-migration-opportunities.md)** - Future enhancements
  - Performance optimization opportunities
  - Feature additions
  - Cost optimization strategies

## Docker Compose Deployment

- **[Containerization Guide](containerization.md)** - Docker Compose setup
  - Docker Compose configuration
  - Service definitions
  - Local development setup
  - Failover deployment

## Deployment Architecture

```
┌─────────────────────────────────────┐
│     Dagster Cloud (Primary)         │
│  ┌──────────────────────────────┐   │
│  │  Serverless Code Locations   │   │
│  │  - sbir-etl (main)          │   │
│  │  - Environment Variables     │   │
│  └──────────────────────────────┘   │
│           ↓                          │
│  ┌──────────────────────────────┐   │
│  │  External Resources          │   │
│  │  - Neo4j Aura (database)    │   │
│  │  - S3 (data storage)        │   │
│  │  - Secrets Manager          │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│   Docker Compose (Failover)         │
│  ┌──────────────────────────────┐   │
│  │  Services                    │   │
│  │  - dagster-webserver        │   │
│  │  - dagster-daemon           │   │
│  │  - postgres (metadata)      │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

## Environment Variables

Key environment variables for deployment:

- `DAGSTER_CLOUD_ORGANIZATION` - Dagster Cloud organization name
- `DAGSTER_CLOUD_DEPLOYMENT` - Deployment name (e.g., `prod`, `dev`)
- `NEO4J_URI` - Neo4j database connection URI
- `NEO4J_USER` / `NEO4J_PASSWORD` - Neo4j credentials
- Additional variables documented in individual guides

## Deployment Best Practices

1. **Use Dagster Cloud for production** - Managed infrastructure, better scaling
2. **Keep secrets in Dagster Cloud secrets manager** - Never commit secrets to git
3. **Test deployments in a staging environment** - Validate before production
4. **Monitor resource usage** - Watch for memory/CPU issues
5. **Use Docker Compose for local development** - Fast iteration cycle

## Related Documentation

- **[Testing Documentation](../testing/)** - Testing guides and setup
- **[Architecture Documentation](../architecture/)** - System architecture
- **[Configuration Documentation](../../config/)** - Configuration files and settings
- **[Quick Start Guide](../../QUICK_START.md)** - Getting started with the project

## Troubleshooting

Common deployment issues:

1. **Code location fails to load** - Check Python dependencies in `pyproject.toml`
2. **Neo4j connection errors** - Verify credentials and network access
3. **Asset materialization failures** - Check logs in Dagster Cloud UI
4. **Environment variable issues** - Verify secrets are set in Dagster Cloud

For detailed troubleshooting, see the [Dagster Cloud Migration Guide](dagster-cloud-migration.md).

---

For questions about deployment, consult the relevant guide above or refer to the main [project README](../../README.md).

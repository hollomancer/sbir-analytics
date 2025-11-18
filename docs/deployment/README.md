---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-01-XX
Status: active

---

# Deployment Documentation

This directory contains comprehensive deployment documentation for the SBIR ETL project.

## Deployment Overview

The SBIR ETL project supports multiple deployment strategies optimized for different use cases:

1.  **Dagster Cloud + AWS (Primary Production)** - Fully managed cloud deployment (recommended)
2.  **AWS Lambda + Step Functions** - Serverless scheduled workflows
3.  **Docker Compose (Development/Failover)** - Self-hosted containerized deployment

## Deployment Decision Tree

```
┌─────────────────────────────────────┐
│   What are you deploying?           │
└──────────────┬──────────────────────┘
               │
               ├─── Production ETL pipeline? ───────────────────┐
               │                                                │
               │                                                ▼
               │                               ┌───────────────────────────┐
               │                               │  Use Dagster Cloud        │
               │                               │  + Neo4j Aura + S3        │
               │                               │                           │
               │                               │  Benefits:                │
               │                               │  • Fully managed          │
               │                               │  • Auto-scaling           │
               │                               │  • Built-in observability │
               │                               │  • Cost-effective         │
               │                               └───────────────────────────┘
               │
               ├─── Scheduled AWS workflows? ───────────────────┐
               │                                                │
               │                                                ▼
               │                               ┌───────────────────────────┐
               │                               │  Use AWS Lambda           │
               │                               │  + Step Functions         │
               │                               │                           │
               │                               │  Benefits:                │
               │                               │  • Serverless (no servers)│
               │                               │  • Pay-per-execution      │
               │                               │  • CloudWatch monitoring  │
               │                               │  • Ideal for weekly runs  │
               │                               └───────────────────────────┘
               │
               └─── Local Development/Testing? ─────────────────┐
                                                                │
                                                                ▼
                                                 ┌───────────────────────────┐
                                                 │  Use Docker Compose       │
                                                 │  + Local Dagster          │
                                                 │                           │
                                                 │  Benefits:                │
                                                 │  • Fast local iteration   │
                                                 │  • No cloud costs         │
                                                 │  • Full control           │
                                                 │  • Works offline          │
                                                 └───────────────────────────┘
```

### Quick Deployment Selector

| Scenario | Recommended Deployment | Guide |
|----------|----------------------|-------|
| **Production ETL pipeline** | Dagster Cloud + Neo4j Aura + S3 | [Dagster Cloud Deployment Guide](dagster-cloud-deployment-guide.md) |
| **Weekly SBIR data refresh** | AWS Lambda + Step Functions | [AWS Serverless Deployment Guide](aws-serverless-deployment-guide.md) |
| **Local development** | Docker Compose + Local Dagster | [Containerization Guide](containerization.md) |
| **CI/CD testing** | Docker Compose (ci profile) | [Containerization Guide](containerization.md) |
| **Emergency failover** | Docker Compose | [Containerization Guide](containerization.md) |

## Detailed Deployment Guides

-   **[Dagster Cloud Overview](dagster-cloud-overview.md)**: Single source of truth for prerequisites, environment variables, and validation steps referenced by other docs.
-   **[Dagster Cloud Deployment Guide](dagster-cloud-deployment-guide.md)**: Comprehensive guide for deploying to Dagster Cloud, including UI and CLI-based methods, managing multiple Neo4j instances, and S3 data access.
-   **[AWS Serverless Deployment Guide](aws-serverless-deployment-guide.md)**: Detailed instructions for setting up AWS infrastructure using Step Functions and Lambda, covering architecture, deployment steps, and S3 data migration.
-   **[Containerization Guide](containerization.md)**: Explains how to build, run, and validate the SBIR ETL stack with Docker Compose for local development and failover scenarios.

## Related Documentation

-   **[Testing Documentation](../testing/)** - Testing guides and setup
-   **[Architecture Documentation](../architecture/)** - System architecture
-   **[Configuration Documentation](../../config/)** - Configuration files and settings
-   **[Quick Start Guide](../../QUICK_START.md)** - Getting started with the project

## Troubleshooting

For detailed troubleshooting, please refer to the specific deployment guide relevant to your issue.

---

For questions about deployment, consult the relevant guide above or refer to the main [project README](../../README.md).

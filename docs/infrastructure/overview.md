# Infrastructure Overview

**Last Updated:** 2025-01-20
**Status:** Active

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Diagram](#architecture-diagram)
3. [Infrastructure Components](#infrastructure-components)
4. [Local Development Environment](#local-development-environment)
5. [Cloud Production Environment](#cloud-production-environment)
6. [Configuration Management](#configuration-management)
7. [Deployment Strategy](#deployment-strategy)
8. [Security & Secrets Management](#security--secrets-management)
9. [Monitoring & Observability](#monitoring--observability)
10. [Cost Analysis](#cost-analysis)
11. [Quick Reference](#quick-reference)

---

## Executive Summary

The SBIR ETL infrastructure is designed with a **cloud-first, local-optional** approach:

- **Primary Orchestration:** Dagster Cloud (fully managed)
- **Scheduled Workflows:** AWS Lambda + Step Functions
- **Database:** Neo4j Aura (cloud) with local Docker option
- **Storage:** AWS S3 with local filesystem fallback
- **Local Development:** Docker Compose or native Python with UV

### Key Design Principles

1. **Cloud-Native:** Production runs entirely in managed services (no servers to maintain)
2. **Cost-Effective:** Leverages free tiers and serverless pricing (~$15-20/month total)
3. **Developer-Friendly:** Fast local iteration with Docker or native Python
4. **Resilient:** Multiple fallback paths and retry mechanisms
5. **Observable:** Built-in monitoring via Dagster Cloud and CloudWatch

---

## Architecture Diagram

### Production Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         PRODUCTION STACK                         │
└─────────────────────────────────────────────────────────────────┘

GitHub Push (main branch)
    │
    ├──> GitHub Actions (.github/workflows/deploy.yml)
    │    │
    │    └──> Dagster Cloud Deployment
    │         │
    │         ├──> Code Location: src.definitions
    │         ├──> Python 3.11 Runtime
    │         └──> Auto-reload on push
    │
    │
    └──> GitHub Actions (.github/workflows/lambda-deploy.yml)
         │
         └──> AWS CDK Deployment
              │
              ├──> S3 Bucket (sbir-etl-production-data)
              ├──> Secrets Manager (Neo4j credentials)
              ├──> Lambda Functions (8 functions + layer)
              └──> Step Functions (weekly-refresh workflow)


┌─────────────────────────────────────────────────────────────────┐
│                        EXECUTION FLOW                            │
└─────────────────────────────────────────────────────────────────┘

User/Schedule
    │
    ├──> Manual Execution: Dagster Cloud UI
    │    │
    │    └──> Dagster Cloud Agents
    │         │
    │         ├──> Reads from S3
    │         ├──> Writes to Neo4j Aura (neo4j+s://)
    │         └──> Outputs to S3
    │
    └──> Scheduled Execution: AWS EventBridge
         │
         └──> Step Functions State Machine
              │
              ├──> Lambda: download-csv
              ├──> Lambda: validate-dataset
              ├──> Lambda: trigger-dagster-refresh
              └──> Lambda: smoke-checks
                   │
                   └──> Dagster Cloud Job via API


┌─────────────────────────────────────────────────────────────────┐
│                         DATA FLOW                                │
└─────────────────────────────────────────────────────────────────┘

SBIR.gov CSV → Lambda → S3 (raw/) → Dagster Cloud → Neo4j Aura
                                                   ↓
USPTO APIs → Lambda → S3 (raw/) → Dagster Cloud → Neo4j Aura
                                                   ↓
                                            S3 (processed/)
```

### Local Development Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL DEVELOPMENT                           │
└─────────────────────────────────────────────────────────────────┘

Option A: Native Python (Recommended for Fast Iteration)
─────────────────────────────────────────────────────────

Developer Machine
    │
    └──> uv run dagster dev -m src.definitions
         │
         ├──> Dagster UI (localhost:3000)
         ├──> Python 3.11 Environment
         ├──> Local Filesystem (data/)
         └──> Neo4j Aura (neo4j+s://)
              OR Neo4j Docker (bolt://localhost:7687)


Option B: Docker Compose (Recommended for Full Stack Testing)
───────────────────────────────────────────────────────────────

Developer Machine
    │
    └──> docker compose --profile dev up
         │
         ├──> dagster-webserver (localhost:3000)
         ├──> dagster-daemon (scheduler)
         ├──> neo4j (localhost:7687, 7474)
         └──> Shared Volumes (data/, logs/, reports/)
```

---

## Infrastructure Components

### Orchestration

| Component | Type | Purpose | Access |
|-----------|------|---------|--------|
| **Dagster Cloud** | Managed Service | Primary ETL orchestration | https://sbir.dagster.cloud |
| **Dagster Local** | Python Process | Local development | http://localhost:3000 |
| **AWS Step Functions** | Serverless | Weekly scheduled workflows | AWS Console |

**Key Details:**
- **Dagster Cloud**: Solo Plan ($10/month), auto-deploys from GitHub, includes observability
- **Step Functions**: Orchestrates 8 Lambda functions for weekly SBIR data refresh
- **Local Dagster**: Runs with `uv run dagster dev`, auto-reloads on code changes

### Compute

| Component | Type | Purpose | Scaling |
|-----------|------|---------|---------|
| **Dagster Cloud Agents** | Serverless | Execute Dagster assets | Auto-scales |
| **AWS Lambda** | Serverless | Data download & validation | On-demand |
| **Docker Containers** | Local | Development services | Manual |

**Lambda Functions:**
1. `download-csv` - Fetch SBIR awards from data.www.sbir.gov
2. `download-uspto-assignments` - Fetch patent assignment data
3. `download-uspto-patentsview` - Fetch PatentsView data
4. `download-uspto-ai-patents` - Fetch AI patent classifications
5. `validate-dataset` - Data quality checks
6. `profile-inputs` - Data profiling and statistics
7. `enrichment-checks` - Enrichment coverage analysis
8. `trigger-dagster-refresh` - Trigger Dagster Cloud jobs
9. `reset-neo4j` - Database reset operations
10. `smoke-checks` - Post-load validation

**Resource Allocation:**
- Lambda: 1024-3008 MB memory, 15-minute timeout
- Docker: 1-2 GB per container, CPU limits configurable

### Database

| Component | Type | Purpose | Connection |
|-----------|------|---------|------------|
| **Neo4j Aura** | Managed Graph DB | Production data store | neo4j+s://[instance].databases.neo4j.io |
| **Neo4j Docker** | Containerized | Local development | bolt://localhost:7687 |

**Configuration:**
- **Version**: Neo4j 5.20+
- **Plugins**: APOC, GDS (Graph Data Science)
- **Memory**: 512 MB heap (local), auto-scaled (Aura)
- **Storage**: Graph store + full-text indexes

### Storage

| Component | Type | Purpose | Path Structure |
|-----------|------|---------|----------------|
| **AWS S3** | Object Storage | Production data lake | s3://sbir-etl-production-data/ |
| **Local Filesystem** | Directory | Development data | ./data/ |

**S3 Bucket Structure:**
```
sbir-etl-production-data/
├── raw/
│   ├── sbir/                    # SBIR award CSV files (30-day retention)
│   ├── uspto/                   # USPTO patent data
│   └── usaspending/             # USAspending contract data
├── processed/
│   ├── validated/               # Post-validation datasets
│   ├── enriched/                # Enriched data with fuzzy matching
│   └── duckdb/                  # DuckDB database files
└── artifacts/
    ├── reports/                 # Data quality reports (90-day retention)
    ├── metadata/                # Dataset metadata and checksums
    └── logs/                    # Processing logs
```

**Local Directory Structure:**
```
data/
├── raw/                         # Downloaded source files
├── processed/                   # Transformed data
├── reports/                     # Generated reports
└── cache/                       # Temporary caches
```

### Secrets Management

| Component | Type | Purpose | Access Pattern |
|-----------|------|---------|----------------|
| **AWS Secrets Manager** | Managed Service | Production secrets | IAM role-based |
| **Environment Variables** | .env file | Local secrets | File-based |
| **Dagster Cloud Env Vars** | UI Configuration | Cloud secrets | UI/API |

**Secrets Stored:**
- Neo4j credentials (URI, username, password, database)
- AWS credentials (access key, secret key)
- GitHub tokens (for CI/CD)
- API keys (PatentsView, PaECTER)

### Infrastructure as Code

| Component | Type | Purpose | Location |
|-----------|------|---------|----------|
| **AWS CDK** | Python IaC | AWS infrastructure | infrastructure/cdk/ |
| **Docker Compose** | Container orchestration | Local services | docker-compose.yml |
| **GitHub Actions** | CI/CD | Automated deployment | .github/workflows/ |

**CDK Stacks:**
1. **StorageStack**: S3 bucket with lifecycle policies
2. **SecurityStack**: IAM roles, policies, Secrets Manager
3. **LambdaStack**: Lambda functions with layers
4. **StepFunctionsStack**: State machine definition

---

## Local Development Environment

### Quick Start (Native Python)

**Prerequisites:**
- Python 3.11
- UV package manager
- Neo4j Aura account OR Docker

**Setup:**
```bash
# Clone repository
git clone https://github.com/hollomancer/sbir-analytics.git
cd sbir-analytics

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Start Dagster
uv run dagster dev -m src.definitions

# Open http://localhost:3000
```

**Recommended .env Configuration:**
```bash
# Neo4j (use Aura for simplicity)
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j

# Data Storage (local by default)
SBIR_ETL__S3__USE_S3=false
SBIR_ETL__PATHS__DATA_ROOT=./data

# Environment
ENVIRONMENT=dev
PYTHONPATH=/app
```

### Quick Start (Docker Compose)

**Prerequisites:**
- Docker Desktop OR Docker Engine + Compose V2
- .env file configured

**Setup:**
```bash
# Build images
make docker-build

# Start development stack
make docker-up-dev

# Open http://localhost:3000 (Dagster)
# Open http://localhost:7474 (Neo4j Browser)
```

**Makefile Commands:**
```bash
make docker-build         # Build all images
make docker-up-dev        # Start dev services
make docker-down          # Stop all services
make docker-test          # Run test suite in containers
make docker-logs          # Tail service logs
make docker-clean         # Remove containers and volumes
make neo4j-reset          # Fresh database
```

### Service Profiles

**Dev Profile** (development):
- Bind mounts for live code reloading
- Persistent Neo4j volumes
- Debug logging enabled
- Hot reload on file changes

**CI Profile** (testing):
- Ephemeral volumes (fresh state)
- Test execution mode
- Coverage reporting
- E2E test scenarios

### Development Workflow

1. **Edit Code**: Modify files in `src/`
2. **Reload**: Dagster auto-reloads (native) or restart containers (Docker)
3. **Test**: Run `uv run pytest -v` OR `make docker-test`
4. **Materialize Assets**: Use Dagster UI or CLI
5. **Query Data**: Use Neo4j Browser (http://localhost:7474)
6. **Debug**: Check logs in Dagster UI or `make docker-logs`

### Local Performance Tips

1. **Use Neo4j Aura**: Faster than local Docker, free tier available
2. **Native Python**: Faster startup than Docker (seconds vs. minutes)
3. **Limit Data**: Use sample data for faster iteration
4. **Cache Results**: Dagster caches asset materializations
5. **Skip Slow Tests**: Run `pytest -m "not slow"` for quick feedback

---

## Cloud Production Environment

### Dagster Cloud Setup

**Prerequisites:**
- Dagster Cloud account (30-day free trial)
- GitHub repository access
- Neo4j Aura credentials

**Initial Setup:**

1. **Create Dagster Cloud Deployment:**
   - Go to https://cloud.dagster.io
   - Start free trial (no credit card required)
   - Connect GitHub repository

2. **Configure Code Location:**
   - Module: `src.definitions`
   - Branch: `main`
   - Python version: 3.11

3. **Set Environment Variables** (Dagster Cloud UI → Deployments → Environment Variables):
   ```bash
   NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your-password
   NEO4J_DATABASE=neo4j
   SBIR_ETL__S3__BUCKET=sbir-etl-production-data
   SBIR_ETL__S3__USE_S3=true
   ENVIRONMENT=production
   ```

4. **Deploy:**
   - Push to `main` branch
   - GitHub Actions automatically deploys
   - Verify in Dagster Cloud UI

**Smoke Test:**
```bash
# In Dagster Cloud UI:
# 1. Navigate to Assets
# 2. Select a lightweight asset (e.g., "cet_validation")
# 3. Click "Materialize"
# 4. Check run logs for Neo4j connection
```

### AWS Infrastructure Setup

**Prerequisites:**
- AWS Account with admin permissions
- AWS CLI configured
- AWS CDK installed: `npm install -g aws-cdk`

**Deployment:**

```bash
# Navigate to CDK directory
cd infrastructure/cdk

# Install CDK dependencies
uv sync

# Bootstrap CDK (first time only)
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2

# Review changes
cdk diff

# Deploy all stacks
cdk deploy --all

# Note: Storage stack imports existing bucket by default
# To create new resources, use: --context create_new_resources=true
```

**Post-Deployment:**

1. **Create Secrets** (if not exists):
   ```bash
   aws secretsmanager create-secret \
     --name sbir-analytics/neo4j-aura \
     --secret-string '{
       "uri": "neo4j+s://...",
       "username": "neo4j",
       "password": "...",
       "database": "neo4j"
     }' \
     --region us-east-2
   ```

2. **Configure GitHub Actions Secrets:**
   - `AWS_ROLE_ARN`: Output from CDK SecurityStack
   - `STEP_FUNCTIONS_STATE_MACHINE_ARN`: Output from CDK StepFunctionsStack
   - `DAGSTER_CLOUD_API_TOKEN`: From Dagster Cloud settings

3. **Test Step Functions:**
   ```bash
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:states:us-east-2:ACCOUNT_ID:stateMachine:sbir-analytics-weekly-refresh \
     --input '{"force_refresh": false}'
   ```

### Neo4j Aura Setup

1. **Create Instance:**
   - Go to https://console.neo4j.io
   - Start free tier instance (50k nodes, 175k relationships)
   - Select AWS region: us-east-2 (Ohio)

2. **Configure:**
   - Memory: 2 GB (free tier)
   - Storage: Auto-scaled
   - Plugins: Enable APOC

3. **Get Credentials:**
   - Connection URI: `neo4j+s://[id].databases.neo4j.io`
   - Username: `neo4j`
   - Password: Generated on creation

4. **Apply Schema:**
   ```bash
   # Local environment
   export NEO4J_URI="neo4j+s://..."
   export NEO4J_USER="neo4j"
   export NEO4J_PASSWORD="..."

   # Apply schema
   uv run python scripts/neo4j/apply_schema.py
   ```

### Data Migration to S3

**Initial Upload:**
```bash
# Upload raw data
aws s3 sync data/raw/sbir/ \
  s3://sbir-etl-production-data/raw/sbir/ \
  --exclude "*.gitkeep" \
  --exclude ".DS_Store"

# Verify upload
aws s3 ls s3://sbir-etl-production-data/raw/sbir/ --recursive
```

**Ongoing Sync:**
- Lambda functions automatically download fresh data to S3
- No manual uploads needed for production workflows

---

## Configuration Management

### Configuration Hierarchy

Configuration loads in this order (later overrides earlier):

1. **Base Configuration**: `config/base.yaml` (default values)
2. **Environment Configuration**: `config/{environment}.yaml` (dev, prod, etc.)
3. **Environment Variables**: `SBIR_ETL__*` (runtime overrides)

### Environment Files

| File | Purpose | Usage |
|------|---------|-------|
| `config/base.yaml` | Default settings | Always loaded |
| `config/dev.yaml` | Development overrides | ENVIRONMENT=dev |
| `config/prod.yaml` | Production overrides | ENVIRONMENT=prod |
| `config/docker.yaml` | Docker-specific settings | Docker Compose |
| `config/test-aura.yaml` | Neo4j Aura testing | Test with Aura |

### Environment Variable Override Pattern

Format: `SBIR_ETL__SECTION__SUBSECTION__KEY`

**Examples:**
```bash
# Neo4j connection
SBIR_ETL__NEO4J__URI=neo4j+s://...
SBIR_ETL__NEO4J__USER=neo4j
SBIR_ETL__NEO4J__PASSWORD=secret

# S3 storage
SBIR_ETL__S3__BUCKET=sbir-etl-production-data
SBIR_ETL__S3__USE_S3=true

# Data paths
SBIR_ETL__PATHS__DATA_ROOT=/app/data
SBIR_ETL__PATHS__USASPENDING_DUMP=/app/data/usaspending.dump

# Data quality thresholds
SBIR_ETL__DATA_QUALITY__SBIR__PASS_RATE=0.95
SBIR_ETL__DATA_QUALITY__USPTO__PASS_RATE=0.99

# Enrichment performance
SBIR_ETL__ENRICHMENT__CHUNK_SIZE=25000
SBIR_ETL__ENRICHMENT__MEMORY_THRESHOLD_GB=2.0
```

### Feature Configurations

**CET Classification** (`config/cet/`):
- `taxonomy.yaml` - Technology taxonomy definitions
- `classification.yaml` - ML model configuration
- `patent_keywords.yaml` - Patent filtering rules

**Transition Detection** (`config/transition/`):
- `detection.yaml` - Detection thresholds and signals
- `presets.yaml` - Named configuration presets

**Fiscal Analysis** (`config/fiscal/`):
- `naics_bea_mappings.yaml` - Economic sector mappings

### Configuration Best Practices

1. **Never commit secrets**: Use `.env` or environment variables
2. **Use environment overrides**: For production-specific values
3. **Document changes**: Update relevant YAML comments
4. **Test locally**: Validate config changes before deploying
5. **Version control**: Keep config files in Git (except .env)

---

## Deployment Strategy

### Deployment Paths

```
┌─────────────────────────────────────────────────────────┐
│                   DEPLOYMENT DECISION TREE               │
└─────────────────────────────────────────────────────────┘

What are you deploying?
  │
  ├─── Dagster Assets/Jobs? ──────────────────────────┐
  │                                                    │
  │                                                    ▼
  │                                    Push to main branch
  │                                           │
  │                                           ├─> .github/workflows/deploy.yml
  │                                           │
  │                                           └─> Dagster Cloud Auto-Deploy
  │
  │
  ├─── AWS Infrastructure? ───────────────────────────┐
  │                                                    │
  │                                                    ▼
  │                                    cd infrastructure/cdk
  │                                    cdk deploy --all
  │                                           │
  │                                           ├─> StorageStack (S3)
  │                                           ├─> SecurityStack (IAM, Secrets)
  │                                           ├─> LambdaStack (Functions)
  │                                           └─> StepFunctionsStack (Workflow)
  │
  │
  └─── Local Development? ────────────────────────────┐
                                                      │
                                                      ▼
                                      Choose your path:
                                           │
                                           ├─> Native Python: uv run dagster dev
                                           └─> Docker: make docker-up-dev
```

### CI/CD Pipelines

| Workflow | Trigger | Purpose | Duration |
|----------|---------|---------|----------|
| `ci.yml` | PR, push to main | Unit tests, lint, security | 15-20 min |
| `deploy.yml` | Push to main | Dagster Cloud deployment | 5-10 min |
| `lambda-deploy.yml` | Push to main (infra changes) | AWS infrastructure | 10-15 min |
| `nightly.yml` | Daily at 03:00 UTC | Comprehensive tests | 30-45 min |
| `weekly-award-data-refresh.yml` | Weekly | SBIR data refresh | 20-30 min |

### Deployment Checklist

**Before Deploying:**
- [ ] All tests pass locally
- [ ] Configuration reviewed
- [ ] Secrets configured
- [ ] Documentation updated
- [ ] Breaking changes documented

**Dagster Cloud Deployment:**
- [ ] Code pushed to main branch
- [ ] GitHub Actions workflow succeeds
- [ ] Assets visible in Dagster Cloud UI
- [ ] Test materialize a simple asset
- [ ] Check logs for errors

**AWS Infrastructure Deployment:**
- [ ] CDK diff reviewed
- [ ] No destructive changes (unless intended)
- [ ] Secrets created in Secrets Manager
- [ ] IAM permissions validated
- [ ] Test Lambda invocation
- [ ] Test Step Functions execution

**Rollback Plan:**
- **Dagster Cloud**: Revert Git commit, automatic redeploy
- **AWS CDK**: `cdk deploy` previous version or manual rollback
- **Emergency**: Switch to Docker Compose failover

---

## Security & Secrets Management

### Security Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      SECURITY LAYERS                     │
└─────────────────────────────────────────────────────────┘

1. Network Security:
   ├─ Neo4j Aura: TLS encryption (neo4j+s://)
   ├─ AWS VPC: Private subnets (future enhancement)
   └─ GitHub OIDC: No long-lived AWS credentials

2. Authentication:
   ├─ AWS IAM Roles: Least-privilege access
   ├─ Neo4j: Username/password authentication
   └─ Dagster Cloud: SSO ready (future)

3. Secrets Management:
   ├─ AWS Secrets Manager: Production secrets
   ├─ GitHub Secrets: CI/CD credentials
   ├─ .env files: Local development (gitignored)
   └─ Dagster Cloud Env Vars: Cloud runtime

4. Data Security:
   ├─ S3: Server-side encryption (AES-256)
   ├─ Neo4j Aura: Encrypted at rest
   └─ TLS in transit: All external connections

5. Access Control:
   ├─ IAM Policies: Resource-level permissions
   ├─ Neo4j RBAC: Database access control
   └─ GitHub Branch Protection: Code review required
```

### Secrets Configuration

**Production (AWS Secrets Manager):**
```bash
# Neo4j credentials
aws secretsmanager get-secret-value \
  --secret-id sbir-analytics/neo4j-aura \
  --region us-east-2

# Structure:
{
  "uri": "neo4j+s://...",
  "username": "neo4j",
  "password": "...",
  "database": "neo4j"
}
```

**Local Development (.env file):**
```bash
# .env (gitignored)
NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
PATENTSVIEW_API_KEY=...
```

**Dagster Cloud (UI Configuration):**
```
Navigate to: Deployments → Code Location → Environment Variables
Add:
- NEO4J_URI
- NEO4J_USER
- NEO4J_PASSWORD
- SBIR_ETL__S3__BUCKET
```

### Security Best Practices

1. **Never commit secrets**: Use `.gitignore` for `.env` files
2. **Rotate credentials**: Change passwords every 90 days
3. **Use IAM roles**: Avoid hardcoded AWS credentials
4. **Enable MFA**: For AWS and GitHub accounts
5. **Scan for secrets**: GitHub secret scanning enabled
6. **Least privilege**: Grant minimum required permissions
7. **Audit logs**: Review CloudWatch and Dagster logs regularly

### Secret Rotation

**Neo4j Password Rotation:**
```bash
# 1. Update password in Neo4j Aura console
# 2. Update AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id sbir-analytics/neo4j-aura \
  --secret-string '{"uri":"...","username":"neo4j","password":"NEW_PASSWORD","database":"neo4j"}'

# 3. Update Dagster Cloud environment variables (if using)
# 4. Redeploy Lambda functions (they cache secrets)
```

**AWS Credentials Rotation:**
```bash
# 1. Create new access key in IAM
# 2. Update GitHub secrets
# 3. Test deployments
# 4. Delete old access key
```

---

## Monitoring & Observability

### Monitoring Stack

| Layer | Tool | Purpose | Access |
|-------|------|---------|--------|
| **Orchestration** | Dagster Cloud UI | Asset runs, logs, alerts | https://sbir.dagster.cloud |
| **AWS Services** | CloudWatch | Lambda logs, metrics | AWS Console |
| **Step Functions** | AWS Console | Workflow execution | AWS Console |
| **Database** | Neo4j Aura | Query performance, metrics | Neo4j Console |
| **CI/CD** | GitHub Actions | Pipeline status | GitHub UI |

### Key Metrics

**Dagster Cloud:**
- Asset materialization success rate
- Run duration by asset
- Asset freshness (last materialization time)
- Error rates by component
- Resource utilization (compute time)

**AWS Lambda:**
- Invocation count
- Error count and type
- Duration (p50, p95, p99)
- Throttles and concurrent executions
- Cold start frequency

**Step Functions:**
- Execution success rate
- State transition counts
- Total execution duration
- Failed state identification
- Retry counts

**Neo4j:**
- Query duration
- Database size (nodes, relationships)
- Connection pool utilization
- Memory usage
- Cache hit rate

### Logging

**Log Locations:**
```
Dagster Cloud:
  - UI: Runs → Run Details → Logs tab
  - Download: Export logs as JSON

AWS Lambda:
  - CloudWatch: /aws/lambda/sbir-analytics-*
  - Command: aws logs tail /aws/lambda/sbir-analytics-download-csv --follow

Step Functions:
  - CloudWatch: /aws/vendedlogs/states/sbir-analytics-weekly-refresh
  - Console: Step Functions → Executions → Execution Details

Neo4j Aura:
  - Console: Logs tab
  - Query log: Enable in settings

Local Development:
  - Dagster: http://localhost:3000 → Runs → Logs
  - Docker: make docker-logs
  - Neo4j: docker logs sbir-analytics-neo4j-1
```

### Alerting

**Dagster Cloud:**
- Failed runs: Email notifications (configurable)
- Asset staleness: Alert if not refreshed in X days
- Resource limits: Memory or compute exceeded

**AWS CloudWatch Alarms:**
```bash
# Example: Alert on Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name sbir-lambda-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=FunctionName,Value=sbir-analytics-download-csv
```

**Recommended Alarms:**
1. Step Functions execution failures (> 2 in 1 hour)
2. Lambda error rate (> 5% over 5 minutes)
3. Neo4j connection failures (> 3 in 5 minutes)
4. S3 access denied errors (> 1)
5. Dagster Cloud run failures (> 3 per day)

### Debugging Checklist

**Asset Materialization Failed:**
1. Check Dagster Cloud run logs
2. Verify Neo4j connection (credentials, network)
3. Check S3 access (permissions, bucket exists)
4. Review data quality thresholds
5. Check for upstream asset failures

**Lambda Function Failed:**
1. View CloudWatch logs
2. Check IAM permissions
3. Verify Secrets Manager access
4. Check Lambda timeout and memory
5. Review Step Functions input/output

**Step Functions Stuck:**
1. Check current state in AWS Console
2. Review Lambda function status
3. Check for infinite retries
4. Verify state machine definition
5. Check EventBridge trigger

**Neo4j Connection Issues:**
1. Verify credentials in Secrets Manager
2. Check Neo4j Aura instance status
3. Test connection from local machine
4. Review network security groups (if using VPC)
5. Check connection string format (neo4j+s://)

---

## Cost Analysis

### Monthly Cost Breakdown (Estimated)

| Service | Tier | Usage | Cost/Month |
|---------|------|-------|------------|
| **Dagster Cloud** | Solo Plan | Unlimited runs | $10.00 |
| **Neo4j Aura** | Free Tier | 50k nodes, 175k relationships | $0.00 |
| **Neo4j Aura** | Professional | 2GB RAM, auto-scaled storage | ~$65.00 (if needed) |
| **AWS Lambda** | Pay-per-use | ~50 invocations/month | $1.00 |
| **AWS Step Functions** | Pay-per-transition | ~300 transitions/month | $0.08 |
| **AWS S3** | Standard | ~50 GB storage, minimal requests | $1.15 |
| **AWS Secrets Manager** | Per secret | 2 secrets | $0.80 |
| **CloudWatch Logs** | Pay-per-GB | ~1 GB/month | $0.50 |
| **Data Transfer** | Out to Internet | Minimal | $0.20 |
| **GitHub Actions** | Free tier | < 2000 min/month | $0.00 |

**Total Estimated Cost:**
- **With Free Tier Neo4j**: ~$13-15/month
- **With Professional Neo4j**: ~$78-80/month

**Cost Optimization Tips:**

1. **Use Free Tiers:**
   - Neo4j Aura Free: Up to 50k nodes
   - AWS Free Tier: 1M Lambda requests/month (first 12 months)
   - GitHub Actions: 2000 minutes/month

2. **Reduce Lambda Costs:**
   - Right-size memory allocation
   - Minimize cold starts with provisioned concurrency (if needed)
   - Use Lambda layers to reduce package size

3. **Reduce S3 Costs:**
   - Enable lifecycle policies (move old data to Glacier)
   - Use S3 Intelligent-Tiering
   - Delete temporary files after processing

4. **Reduce CloudWatch Costs:**
   - Set log retention to 7-30 days
   - Use log sampling for high-volume logs
   - Export logs to S3 for long-term storage

5. **Monitor Usage:**
   - Set up AWS Budgets alerts
   - Review AWS Cost Explorer monthly
   - Check Dagster Cloud usage dashboard

---

## Quick Reference

### Essential Commands

**Local Development (Native Python):**
```bash
uv sync                                    # Install dependencies
uv run dagster dev -m src.definitions     # Start Dagster
uv run pytest -v --cov=src                # Run tests
uv run python scripts/neo4j/apply_schema.py  # Apply Neo4j schema
```

**Local Development (Docker):**
```bash
make docker-build                         # Build images
make docker-up-dev                        # Start dev stack
make docker-down                          # Stop services
make docker-test                          # Run tests
make docker-logs                          # View logs
make neo4j-reset                          # Reset database
```

**AWS Deployment:**
```bash
cd infrastructure/cdk
uv sync
cdk diff                                  # Preview changes
cdk deploy --all                          # Deploy all stacks
cdk destroy --all                         # Destroy infrastructure
```

**AWS Operations:**
```bash
# Trigger Step Functions
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-2:ACCOUNT_ID:stateMachine:sbir-analytics-weekly-refresh \
  --input '{"force_refresh": false}'

# View Lambda logs
aws logs tail /aws/lambda/sbir-analytics-download-csv --follow

# Upload data to S3
aws s3 sync data/raw/sbir/ s3://sbir-etl-production-data/raw/sbir/

# Test Lambda function
aws lambda invoke \
  --function-name sbir-analytics-download-csv \
  --payload '{"s3_bucket":"sbir-etl-production-data"}' \
  response.json
```

**Neo4j Operations:**
```bash
# Apply schema (local or Aura)
uv run python scripts/neo4j/apply_schema.py

# Run migrations
uv run python scripts/neo4j/migrate.py

# Clear database
uv run python scripts/neo4j/clear_database.py

# Check Aura usage
uv run python scripts/neo4j/check_aura_usage.py
```

### Configuration Files

| File | Purpose | Edit For |
|------|---------|----------|
| `.env` | Local secrets | Neo4j credentials, AWS keys |
| `config/base.yaml` | Default settings | Global defaults |
| `config/prod.yaml` | Production overrides | Production-specific settings |
| `docker-compose.yml` | Container orchestration | Service definitions |
| `infrastructure/cdk/cdk.json` | CDK configuration | AWS account, region |
| `dagster_cloud.yaml` | Dagster Cloud config | Code location settings |

### Environment Variables

**Required (All Environments):**
```bash
NEO4J_URI=neo4j+s://...               # Neo4j connection string
NEO4J_USER=neo4j                      # Neo4j username
NEO4J_PASSWORD=...                    # Neo4j password
```

**Optional (Common Overrides):**
```bash
ENVIRONMENT=dev|prod                  # Environment name
SBIR_ETL__S3__BUCKET=...              # S3 bucket name
SBIR_ETL__S3__USE_S3=true|false       # Enable S3 storage
AWS_ACCESS_KEY_ID=...                 # AWS access key (local only)
AWS_SECRET_ACCESS_KEY=...             # AWS secret key (local only)
PATENTSVIEW_API_KEY=...               # PatentsView API key
```

### Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| **Dagster won't start** | Check Python 3.11 installed, run `uv sync` |
| **Neo4j connection failed** | Verify credentials, check network access |
| **S3 access denied** | Check AWS credentials, IAM permissions |
| **Lambda timeout** | Increase timeout in CDK, optimize code |
| **Docker build failed** | Clear cache: `docker system prune -a` |
| **Tests failing** | Check Neo4j running, verify test data |
| **Asset materialization failed** | Check logs in Dagster UI, verify dependencies |
| **CDK deploy failed** | Review CloudFormation events, check permissions |

### Support Resources

- **Documentation**: `/docs/` directory in repository
- **Issues**: https://github.com/hollomancer/sbir-analytics/issues
- **Dagster Docs**: https://docs.dagster.io
- **AWS CDK Docs**: https://docs.aws.amazon.com/cdk/
- **Neo4j Docs**: https://neo4j.com/docs/

---

## Related Documentation

- **[Deployment Decision Tree](../deployment/README.md)** - Choose the right deployment path
- **[Dagster Cloud Guide](../deployment/dagster-cloud-deployment-guide.md)** - Detailed Dagster Cloud setup
- **[AWS Serverless Guide](../deployment/aws-serverless-deployment-guide.md)** - Lambda + Step Functions setup
- **[Containerization Guide](../deployment/containerization.md)** - Docker Compose setup
- **[Neo4j Runbook](../deployment/neo4j-runbook.md)** - Database operations
- **[Configuration Guide](../../config/README.md)** - Configuration management
- **[Testing Guide](../testing/README.md)** - Testing strategies

---

**Document Maintained By:** DevOps Team
**Last Review:** 2025-01-20
**Next Review:** 2025-04-20

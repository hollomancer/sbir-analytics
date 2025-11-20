# Infrastructure Recommendations

**Last Updated:** 2025-01-20
**Status:** Active
**Audience:** Developers, DevOps, Platform Engineers

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [High-Priority Recommendations](#high-priority-recommendations)
3. [Local Development Improvements](#local-development-improvements)
4. [Cloud Development Improvements](#cloud-development-improvements)
5. [Documentation Improvements](#documentation-improvements)
6. [Security Improvements](#security-improvements)
7. [Cost Optimization](#cost-optimization)
8. [Performance Optimization](#performance-optimization)
9. [Developer Experience](#developer-experience)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

This document provides actionable recommendations for improving the SBIR ETL infrastructure, with a focus on **local development velocity** and **cloud production reliability**.

### Key Findings

**Strengths:**
- ✅ Clean cloud-native architecture with minimal maintenance
- ✅ Comprehensive Docker setup for local development
- ✅ Good separation of concerns (orchestration, compute, storage)
- ✅ Extensive documentation and deployment guides
- ✅ Cost-effective infrastructure (~$15/month with free tiers)

**Areas for Improvement:**
- ⚠️ Local development setup has multiple paths (can be confusing)
- ⚠️ S3 fallback logic adds complexity for new developers
- ⚠️ Docker build times can be slow (~5-10 minutes)
- ⚠️ Limited observability for local development
- ⚠️ No automated infrastructure validation tests

### Impact Summary

| Category | Recommendations | Estimated Effort | Impact |
|----------|----------------|------------------|--------|
| **Local Dev** | 8 items | 2-3 weeks | High |
| **Cloud Dev** | 7 items | 2-3 weeks | High |
| **Documentation** | 5 items | 1 week | Medium |
| **Security** | 6 items | 2-3 weeks | Medium |
| **Cost** | 4 items | 1 week | Medium |
| **Performance** | 5 items | 2-3 weeks | Medium |
| **DX** | 7 items | 2-4 weeks | High |

---

## High-Priority Recommendations

### 1. Simplify Local Development Path Selection

**Current State:**
- Multiple options: Native Python, Docker Compose, Docker with profiles
- No clear guidance on when to use each
- .env file configuration is complex

**Recommendation:**
Create a `setup.sh` or `setup.py` script that:
1. Detects environment (Docker available? Python 3.11 installed?)
2. Prompts user for preferences
3. Auto-configures .env file
4. Validates Neo4j connectivity
5. Starts appropriate development environment

**Benefits:**
- Reduces onboarding time from hours to minutes
- Eliminates common configuration errors
- Provides clear default path

**Implementation:**
```bash
# Example flow
./scripts/setup.sh

# Output:
# 🔍 Checking prerequisites...
# ✅ Python 3.11 found
# ✅ Docker found
# ✅ UV installed
#
# 📋 Setup Options:
# 1. Native Python (Fastest, recommended)
# 2. Docker Compose (Full stack, isolated)
# 3. Docker Compose with local code (Hybrid)
#
# Choose option (1-3): 1
#
# 🔧 Configuring environment...
# ✅ Created .env file
#
# 🗄️ Neo4j Setup:
# 1. Use Neo4j Aura (Recommended, free tier)
# 2. Use Local Docker Neo4j
#
# Choose option (1-2): 1
#
# Enter Neo4j Aura URI: neo4j+s://...
# Enter Neo4j Username [neo4j]:
# Enter Neo4j Password:
#
# 🧪 Testing connection...
# ✅ Connected to Neo4j successfully
#
# 🚀 Starting Dagster...
# Dagster UI available at http://localhost:3000
```

**Effort:** 2-3 days
**Priority:** HIGH

---

### 2. Add Pre-commit Hooks for Configuration Validation

**Current State:**
- Configuration errors discovered at runtime
- No validation of YAML files before commit
- Missing environment variables cause pipeline failures

**Recommendation:**
Implement pre-commit hooks that:
1. Validate YAML syntax in `config/` directory
2. Check for required environment variables
3. Lint Docker Compose files
4. Validate CDK configuration
5. Run quick smoke tests

**Implementation:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-yaml
        files: ^config/.*\.yaml$
      - id: check-json
      - id: end-of-file-fixer
      - id: trailing-whitespace

  - repo: local
    hooks:
      - id: validate-env-example
        name: Validate .env.example
        entry: python scripts/ci/validate_env_file.py
        language: system
        files: ^\.env\.example$

      - id: validate-docker-compose
        name: Validate docker-compose.yml
        entry: docker compose config --quiet
        language: system
        files: ^docker-compose\.yml$

      - id: validate-cdk-config
        name: Validate CDK configuration
        entry: python scripts/ci/validate_cdk_config.py
        language: system
        files: ^infrastructure/cdk/.*\.py$
```

**Benefits:**
- Catch configuration errors before commit
- Reduce CI/CD failures
- Faster feedback loop

**Effort:** 1 week
**Priority:** HIGH

---

### 3. Implement Infrastructure Smoke Tests

**Current State:**
- Manual testing required after infrastructure changes
- No automated validation of AWS resources
- CDK deployments can succeed but be misconfigured

**Recommendation:**
Create automated smoke tests:

**For AWS Infrastructure:**
```python
# tests/infrastructure/test_aws_smoke.py
import boto3
import pytest

def test_s3_bucket_exists():
    """Verify S3 bucket exists and is accessible."""
    s3 = boto3.client('s3')
    response = s3.head_bucket(Bucket='sbir-etl-production-data')
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200

def test_lambda_functions_exist():
    """Verify all Lambda functions are deployed."""
    lambda_client = boto3.client('lambda')
    expected_functions = [
        'sbir-analytics-download-csv',
        'sbir-analytics-validate-dataset',
        'sbir-analytics-trigger-dagster-refresh',
        # ... more functions
    ]
    for function_name in expected_functions:
        response = lambda_client.get_function(FunctionName=function_name)
        assert response['Configuration']['State'] == 'Active'

def test_step_functions_state_machine_exists():
    """Verify Step Functions state machine is deployed."""
    sf_client = boto3.client('stepfunctions')
    state_machines = sf_client.list_state_machines()
    names = [sm['name'] for sm in state_machines['stateMachines']]
    assert 'sbir-analytics-weekly-refresh' in names

def test_secrets_manager_secrets_exist():
    """Verify required secrets exist in Secrets Manager."""
    secrets_client = boto3.client('secretsmanager')
    response = secrets_client.get_secret_value(
        SecretId='sbir-analytics/neo4j-aura'
    )
    assert response['SecretString'] is not None
```

**For Local Infrastructure:**
```python
# tests/infrastructure/test_local_smoke.py
import subprocess
import requests
import pytest

def test_dagster_ui_accessible():
    """Verify Dagster UI is running and accessible."""
    response = requests.get('http://localhost:3000/server_info')
    assert response.status_code == 200

def test_neo4j_accessible():
    """Verify Neo4j is running and accessible."""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "password")
    )
    with driver.session() as session:
        result = session.run("RETURN 1 as num")
        assert result.single()['num'] == 1
    driver.close()

def test_docker_compose_services_healthy():
    """Verify all Docker Compose services are healthy."""
    result = subprocess.run(
        ['docker', 'compose', 'ps', '--format', 'json'],
        capture_output=True,
        text=True
    )
    services = json.loads(result.stdout)
    for service in services:
        assert service['Health'] == 'healthy'
```

**Run in CI/CD:**
```yaml
# .github/workflows/infrastructure-validation.yml
name: Infrastructure Validation

on:
  push:
    branches: [main]
    paths:
      - 'infrastructure/**'
      - 'docker-compose.yml'
      - '.github/workflows/infrastructure-validation.yml'

jobs:
  test-aws-infrastructure:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-2
      - name: Run AWS smoke tests
        run: pytest tests/infrastructure/test_aws_smoke.py -v

  test-local-infrastructure:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start Docker Compose
        run: |
          cp .env.example .env
          docker compose --profile ci up -d
      - name: Run local smoke tests
        run: pytest tests/infrastructure/test_local_smoke.py -v
```

**Benefits:**
- Automated validation of infrastructure changes
- Catch misconfigurations early
- Confidence in deployments

**Effort:** 1-2 weeks
**Priority:** HIGH

---

## Local Development Improvements

### 4. Reduce Docker Build Time

**Current State:**
- Docker build takes 5-10 minutes
- Multi-stage build is complex
- R package installation is slow

**Recommendations:**

**A. Use Docker Layer Caching in CI/CD:**
```yaml
# .github/workflows/container-build.yml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3

- name: Build and cache
  uses: docker/build-push-action@v5
  with:
    context: .
    file: ./Dockerfile
    push: false
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**B. Split Dockerfile into base + application:**
```dockerfile
# Dockerfile.base (changes infrequently)
FROM python:3.11-slim as base
# Install system dependencies, R packages
# Build wheels
# Push to registry

# Dockerfile (changes frequently)
FROM ghcr.io/hollomancer/sbir-analytics-base:latest
COPY src/ /app/src/
COPY config/ /app/config/
# Fast rebuild
```

**C. Optimize R package installation:**
```dockerfile
# Use pre-built R binaries instead of source compilation
RUN apt-get update && apt-get install -y \
    r-base-core \
    r-cran-devtools \
    && Rscript -e 'install.packages("stateior", repos="https://cloud.r-project.org")'
```

**Benefits:**
- Reduce build time from 10 minutes to 2-3 minutes
- Faster iteration for developers
- Lower CI/CD costs

**Effort:** 3-5 days
**Priority:** MEDIUM

---

### 5. Add Development Container Support (devcontainers)

**Current State:**
- No VS Code devcontainer configuration
- Manual environment setup required
- Inconsistent development environments across team

**Recommendation:**
Add `.devcontainer/devcontainer.json`:

```json
{
  "name": "SBIR Analytics Dev",
  "dockerComposeFile": "../docker-compose.yml",
  "service": "dagster-webserver",
  "workspaceFolder": "/app",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-python.black-formatter",
        "charliermarsh.ruff",
        "neo4j.neo4j-vscode",
        "ms-azuretools.vscode-docker"
      ],
      "settings": {
        "python.defaultInterpreterPath": "/usr/local/bin/python",
        "python.linting.enabled": true,
        "python.formatting.provider": "black",
        "editor.formatOnSave": true
      }
    }
  },
  "forwardPorts": [3000, 7474, 7687],
  "postCreateCommand": "uv sync",
  "remoteUser": "sbir"
}
```

**Benefits:**
- One-click environment setup in VS Code
- Consistent development environment
- No local Python installation needed

**Effort:** 1 day
**Priority:** MEDIUM

---

### 6. Add Local Observability Stack

**Current State:**
- Limited visibility into local pipeline performance
- No metrics collection in development
- Debugging relies on logs only

**Recommendation:**
Add optional observability stack to Docker Compose:

```yaml
# docker-compose.yml (add to dev profile)
services:
  prometheus:
    image: prom/prometheus:latest
    profiles: [dev-observability]
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    profiles: [dev-observability]
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./config/grafana/dashboards:/etc/grafana/provisioning/dashboards

  jaeger:
    image: jaegertracing/all-in-one:latest
    profiles: [dev-observability]
    ports:
      - "16686:16686"
      - "6831:6831/udp"
```

**Usage:**
```bash
# Start with observability
docker compose --profile dev --profile dev-observability up

# Access:
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3001
# - Jaeger: http://localhost:16686
```

**Benefits:**
- Debug performance issues locally
- Understand pipeline bottlenecks
- Practice monitoring before production

**Effort:** 3-5 days
**Priority:** LOW

---

### 7. Improve Local Data Management

**Current State:**
- No easy way to reset to known state
- Sample data not version-controlled
- Manual data setup required

**Recommendations:**

**A. Add data snapshots:**
```bash
# scripts/dev/create_snapshot.sh
#!/bin/bash
# Create snapshot of current data state
SNAPSHOT_NAME=${1:-$(date +%Y%m%d_%H%M%S)}
mkdir -p .snapshots/$SNAPSHOT_NAME
cp -r data/ .snapshots/$SNAPSHOT_NAME/
echo "Snapshot created: $SNAPSHOT_NAME"

# scripts/dev/restore_snapshot.sh
#!/bin/bash
# Restore from snapshot
SNAPSHOT_NAME=$1
if [ -z "$SNAPSHOT_NAME" ]; then
    echo "Available snapshots:"
    ls -1 .snapshots/
    exit 1
fi
rm -rf data/
cp -r .snapshots/$SNAPSHOT_NAME/data/ data/
echo "Restored snapshot: $SNAPSHOT_NAME"
```

**B. Add sample data generation:**
```python
# scripts/dev/generate_sample_data.py
"""Generate sample SBIR data for local development."""
import pandas as pd
from pathlib import Path

def generate_sample_awards(n=1000):
    """Generate n sample award records."""
    df = pd.DataFrame({
        'award_id': [f'AWARD-{i:06d}' for i in range(n)],
        'agency': ['DoD', 'NIH', 'NSF', 'DOE'] * (n // 4),
        'company_name': [f'Company {i}' for i in range(n)],
        'amount': [50000 + i * 100 for i in range(n)],
        # ... more fields
    })
    output_path = Path('data/raw/sbir/sample_awards.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Generated {n} sample awards at {output_path}")

if __name__ == '__main__':
    generate_sample_awards(1000)
```

**C. Add Makefile targets:**
```makefile
# Makefile additions
.PHONY: data-snapshot data-restore data-reset data-sample

data-snapshot:
	@./scripts/dev/create_snapshot.sh

data-restore:
	@./scripts/dev/restore_snapshot.sh

data-reset:
	@echo "Resetting data directory..."
	@rm -rf data/
	@mkdir -p data/raw/sbir data/processed

data-sample:
	@echo "Generating sample data..."
	@uv run python scripts/dev/generate_sample_data.py
```

**Benefits:**
- Quick reset to known state
- Faster testing with sample data
- Reproducible local environment

**Effort:** 2-3 days
**Priority:** MEDIUM

---

### 8. Add Interactive Development Helper

**Current State:**
- No guided workflow for common tasks
- New developers don't know where to start
- Frequent reference to multiple docs

**Recommendation:**
Create interactive CLI helper:

```python
# scripts/dev/dev_helper.py
"""Interactive development helper for SBIR Analytics."""
import click

@click.group()
def cli():
    """SBIR Analytics Development Helper"""
    pass

@cli.command()
def setup():
    """Interactive setup wizard."""
    click.echo("🚀 SBIR Analytics Setup")
    # Guide through setup steps

@cli.command()
def status():
    """Check development environment status."""
    click.echo("📊 Environment Status\n")
    # Check Python, Docker, Neo4j, etc.

@cli.command()
def start():
    """Start development environment."""
    click.echo("🔧 Starting environment...")
    # Start appropriate services

@cli.command()
def test():
    """Run tests with options."""
    # Interactive test runner

@cli.command()
def materialize():
    """Materialize assets interactively."""
    # Guide through asset selection

if __name__ == '__main__':
    cli()
```

**Usage:**
```bash
$ python scripts/dev/dev_helper.py

SBIR Analytics Development Helper

Commands:
  setup        Interactive setup wizard
  status       Check environment status
  start        Start development environment
  test         Run tests with options
  materialize  Materialize assets interactively

$ python scripts/dev/dev_helper.py status

📊 Environment Status

✅ Python 3.11 installed
✅ UV installed
✅ Docker running
⚠️  Neo4j not running (use 'start' to launch)
✅ .env file configured
❌ Dagster not running
```

**Benefits:**
- Faster onboarding
- Guided workflows
- Less context switching

**Effort:** 3-5 days
**Priority:** LOW

---

## Cloud Development Improvements

### 9. Add Dagster Cloud Branch Deployments

**Current State:**
- Only main branch deploys to Dagster Cloud
- No preview environments for PRs
- Changes tested in production

**Recommendation:**
Enable Dagster Cloud branch deployments:

```yaml
# .github/workflows/deploy.yml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Determine deployment type
        id: deployment
        run: |
          if [ "${{ github.event_name }}" == "pull_request" ]; then
            echo "type=branch" >> $GITHUB_OUTPUT
            echo "name=pr-${{ github.event.pull_request.number }}" >> $GITHUB_OUTPUT
          else
            echo "type=prod" >> $GITHUB_OUTPUT
            echo "name=prod" >> $GITHUB_OUTPUT
          fi

      - name: Deploy to Dagster Cloud
        run: |
          dagster-cloud serverless deploy-python-executable \
            --deployment ${{ steps.deployment.outputs.name }} \
            --location-name sbir-analytics \
            --module-name src.definitions
```

**Benefits:**
- Test changes in isolated environment
- Faster feedback on PRs
- Safer deployments

**Effort:** 1-2 days
**Priority:** HIGH

---

### 10. Implement Blue-Green Deployments for Lambda

**Current State:**
- Lambda functions deploy directly (all-or-nothing)
- No gradual rollout
- Rollback requires redeployment

**Recommendation:**
Use Lambda aliases and versions:

```python
# infrastructure/cdk/stacks/lambda_stack.py
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_codedeploy as codedeploy

# Create versioned function
function = lambda_.Function(...)
version = function.current_version

# Create alias with deployment config
alias = lambda_.Alias(
    self, 'ProdAlias',
    alias_name='prod',
    version=version
)

# Add gradual deployment
deployment_config = codedeploy.LambdaDeploymentConfig(
    self, 'DeploymentConfig',
    traffic_routing=codedeploy.TimeBasedCanaryTrafficRouting(
        interval=cdk.Duration.minutes(5),
        percentage=10
    )
)
```

**Benefits:**
- Gradual traffic shifting
- Automatic rollback on errors
- Safer deployments

**Effort:** 3-5 days
**Priority:** MEDIUM

---

### 11. Add CloudWatch Dashboards

**Current State:**
- No centralized monitoring dashboard
- Metrics scattered across services
- Reactive debugging

**Recommendation:**
Create CloudWatch dashboard via CDK:

```python
# infrastructure/cdk/stacks/monitoring_stack.py
from aws_cdk import aws_cloudwatch as cloudwatch

dashboard = cloudwatch.Dashboard(
    self, 'SBIRAnalyticsDashboard',
    dashboard_name='sbir-analytics-production'
)

# Add Lambda metrics
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title='Lambda Invocations',
        left=[
            lambda_fn.metric_invocations(),
            lambda_fn.metric_errors(),
            lambda_fn.metric_throttles()
        ]
    )
)

# Add Step Functions metrics
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title='Step Functions Executions',
        left=[
            state_machine.metric_started(),
            state_machine.metric_succeeded(),
            state_machine.metric_failed()
        ]
    )
)

# Add custom metrics
dashboard.add_widgets(
    cloudwatch.SingleValueWidget(
        title='Neo4j Node Count',
        metrics=[
            cloudwatch.Metric(
                namespace='SBIRAnalytics',
                metric_name='Neo4jNodeCount',
                statistic='Average'
            )
        ]
    )
)
```

**Benefits:**
- Centralized monitoring
- Proactive issue detection
- Better operational visibility

**Effort:** 2-3 days
**Priority:** MEDIUM

---

### 12. Add Infrastructure Testing in CI/CD

**Current State:**
- CDK changes deployed directly
- No validation before deployment
- Breaking changes can reach production

**Recommendation:**
Add CDK validation and testing:

```yaml
# .github/workflows/infrastructure-validation.yml
name: Infrastructure Validation

on:
  pull_request:
    paths:
      - 'infrastructure/cdk/**'

jobs:
  validate-cdk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install CDK
        run: npm install -g aws-cdk

      - name: Install Python dependencies
        run: |
          cd infrastructure/cdk
          pip install -r requirements.txt

      - name: Synthesize CDK stacks
        run: |
          cd infrastructure/cdk
          cdk synth

      - name: Run CDK tests
        run: |
          cd infrastructure/cdk
          pytest tests/ -v

      - name: Check for breaking changes
        run: |
          cd infrastructure/cdk
          cdk diff --fail
```

**Benefits:**
- Catch CDK errors before merge
- Validate template syntax
- Document infrastructure changes

**Effort:** 2-3 days
**Priority:** MEDIUM

---

### 13. Add Automated Cost Monitoring

**Current State:**
- Manual cost review
- No alerts on cost spikes
- Unexpected bills possible

**Recommendation:**
Implement automated cost monitoring:

**A. AWS Budgets:**
```python
# infrastructure/cdk/stacks/monitoring_stack.py
from aws_cdk import aws_budgets as budgets

monthly_budget = budgets.CfnBudget(
    self, 'MonthlyBudget',
    budget=budgets.CfnBudget.BudgetDataProperty(
        budget_type='COST',
        time_unit='MONTHLY',
        budget_limit=budgets.CfnBudget.SpendProperty(
            amount=50,  # $50/month
            unit='USD'
        )
    ),
    notifications_with_subscribers=[
        budgets.CfnBudget.NotificationWithSubscribersProperty(
            notification=budgets.CfnBudget.NotificationProperty(
                notification_type='ACTUAL',
                comparison_operator='GREATER_THAN',
                threshold=80  # Alert at 80%
            ),
            subscribers=[
                budgets.CfnBudget.SubscriberProperty(
                    subscription_type='EMAIL',
                    address='team@example.com'
                )
            ]
        )
    ]
)
```

**B. Cost Anomaly Detection:**
```python
# Enable AWS Cost Anomaly Detection
from aws_cdk import aws_ce as ce

anomaly_monitor = ce.CfnAnomalyMonitor(
    self, 'CostAnomalyMonitor',
    monitor_name='sbir-analytics-monitor',
    monitor_type='DIMENSIONAL',
    monitor_dimension='SERVICE'
)

anomaly_subscription = ce.CfnAnomalySubscription(
    self, 'CostAnomalySubscription',
    subscription_name='sbir-analytics-anomaly',
    threshold=100,  # $100 anomaly
    frequency='IMMEDIATE',
    monitor_arn_list=[anomaly_monitor.attr_monitor_arn],
    subscribers=[
        ce.CfnAnomalySubscription.SubscriberProperty(
            type='EMAIL',
            address='team@example.com'
        )
    ]
)
```

**Benefits:**
- Proactive cost management
- Early warning of cost spikes
- Budget compliance

**Effort:** 1-2 days
**Priority:** MEDIUM

---

### 14. Implement Multi-Region Disaster Recovery

**Current State:**
- Single region deployment (us-east-2)
- No disaster recovery plan
- Data loss possible in region failure

**Recommendation:**
Implement multi-region backup:

```python
# infrastructure/cdk/stacks/disaster_recovery_stack.py
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_backup as backup

# Enable S3 cross-region replication
backup_bucket = s3.Bucket(
    self, 'BackupBucket',
    bucket_name='sbir-etl-backup-us-west-2',
    versioned=True,
    lifecycle_rules=[
        s3.LifecycleRule(
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.GLACIER,
                    transition_after=cdk.Duration.days(90)
                )
            ]
        )
    ]
)

# Add replication rule to primary bucket
primary_bucket.add_lifecycle_rule(
    replication_configuration=s3.ReplicationConfiguration(
        role=replication_role,
        rules=[
            s3.ReplicationRule(
                destination=s3.ReplicationDestination(
                    bucket=backup_bucket
                ),
                status=s3.ReplicationRuleStatus.ENABLED
            )
        ]
    )
)

# Backup Neo4j to S3 daily
backup_plan = backup.BackupPlan(
    self, 'Neo4jBackup',
    backup_plan_rules=[
        backup.BackupPlanRule(
            backup_vault=backup_vault,
            rule_name='DailyBackup',
            schedule_expression=backup.Schedule.cron(
                hour='2',
                minute='0'
            ),
            delete_after=cdk.Duration.days(30)
        )
    ]
)
```

**Benefits:**
- Data protection against region failures
- Compliance with backup requirements
- Peace of mind

**Effort:** 1 week
**Priority:** LOW

---

### 15. Add Canary Testing for Production

**Current State:**
- No automated production testing
- Issues discovered by users
- No SLA monitoring

**Recommendation:**
Implement CloudWatch Synthetics canaries:

```python
# infrastructure/cdk/stacks/monitoring_stack.py
from aws_cdk import aws_synthetics as synthetics

# Canary to test Dagster Cloud
dagster_canary = synthetics.Canary(
    self, 'DagsterCloudCanary',
    canary_name='dagster-cloud-health',
    runtime=synthetics.Runtime.SYNTHETICS_NODEJS_PUPPETEER_3_9,
    test=synthetics.Test.custom(
        handler='index.handler',
        code=synthetics.Code.from_inline('''
            const synthetics = require('Synthetics');
            const https = require('https');

            exports.handler = async () => {
                const options = {
                    hostname: 'sbir.dagster.cloud',
                    path: '/server_info',
                    method: 'GET'
                };

                return new Promise((resolve, reject) => {
                    const req = https.request(options, (res) => {
                        if (res.statusCode === 200) {
                            resolve();
                        } else {
                            reject(`Status ${res.statusCode}`);
                        }
                    });
                    req.on('error', reject);
                    req.end();
                });
            };
        ''')
    ),
    schedule=synthetics.Schedule.rate(cdk.Duration.minutes(5))
)

# Canary to test Neo4j Aura
neo4j_canary = synthetics.Canary(
    self, 'Neo4jAuraCanary',
    canary_name='neo4j-aura-health',
    runtime=synthetics.Runtime.SYNTHETICS_PYTHON_SELENIUM_1_3,
    test=synthetics.Test.custom(
        handler='canary.handler',
        code=synthetics.Code.from_asset('canaries/neo4j-health')
    ),
    schedule=synthetics.Schedule.rate(cdk.Duration.minutes(5))
)
```

**Benefits:**
- Proactive issue detection
- SLA monitoring
- Faster incident response

**Effort:** 3-5 days
**Priority:** LOW

---

## Documentation Improvements

### 16. Create Architecture Decision Records (ADRs)

**Current State:**
- Architecture decisions documented in various places
- No structured decision tracking
- Hard to understand why choices were made

**Recommendation:**
Implement ADRs in `docs/decisions/`:

```markdown
# docs/decisions/0001-use-dagster-cloud-for-orchestration.md

# 1. Use Dagster Cloud for Primary Orchestration

Date: 2024-12-15

## Status

Accepted

## Context

Need managed orchestration platform for SBIR ETL pipeline. Options:
- Dagster Cloud (Solo Plan)
- Self-hosted Dagster on EC2
- AWS Step Functions only
- Airflow on MWAA

## Decision

Use Dagster Cloud Solo Plan as primary orchestration.

## Rationale

- **Cost**: $10/month vs $300+/month for MWAA
- **Maintenance**: Fully managed, no server management
- **Developer Experience**: Best-in-class UI and debugging
- **Observability**: Built-in monitoring and lineage
- **Git Integration**: Auto-deploy from GitHub

## Consequences

### Positive
- Low operational overhead
- Fast development iteration
- Excellent observability
- Cost-effective

### Negative
- Vendor lock-in (mitigated by open-source Dagster)
- Need internet connectivity for UI access
- Additional $10/month cost

### Neutral
- Team needs to learn Dagster (but good investment)

## Alternatives Considered

1. **Self-hosted Dagster on EC2**
   - Pros: No vendor lock-in
   - Cons: High maintenance, ~$50/month EC2 costs

2. **AWS Step Functions Only**
   - Pros: Serverless, AWS-native
   - Cons: Limited observability, hard to debug

3. **Airflow on MWAA**
   - Pros: Industry standard
   - Cons: Expensive ($300+/month), complex setup
```

**Directory Structure:**
```
docs/decisions/
├── README.md
├── 0001-use-dagster-cloud-for-orchestration.md
├── 0002-consolidate-docker-compose-files.md
├── 0003-migrate-lambda-to-dagster-cloud.md
├── 0004-use-neo4j-aura-for-production.md
└── template.md
```

**Benefits:**
- Document decision rationale
- Onboard new team members faster
- Learn from past decisions

**Effort:** 1-2 days initial, ongoing
**Priority:** MEDIUM

---

### 17. Add Interactive Diagrams

**Current State:**
- Static text-based diagrams
- Hard to understand complex flows
- No interactive exploration

**Recommendation:**
Add interactive diagrams using Mermaid or D2:

```markdown
# docs/architecture/data-flow.md

## SBIR Data Flow

​```mermaid
graph TD
    A[SBIR.gov CSV] -->|download| B[Lambda: download-csv]
    B -->|upload| C[S3: raw/sbir/]
    C -->|materialize| D[Dagster: raw_sbir_awards]
    D -->|validate| E[Dagster: validated_sbir_awards]
    E -->|enrich| F[Dagster: enriched_sbir_awards]
    F -->|transform| G[Dagster: transformed_sbir_awards]
    G -->|load| H[Neo4j Aura]

    style A fill:#f9f,stroke:#333
    style H fill:#9f9,stroke:#333
    click D href "http://sbir.dagster.cloud" "Open in Dagster Cloud"
​```

## Click on nodes to explore!
```

**Tools:**
- Mermaid: Native GitHub/GitLab rendering
- D2: More powerful, requires build step
- Excalidraw: Hand-drawn style, collaborative

**Benefits:**
- Better understanding of architecture
- Interactive exploration
- Easier updates (code-based)

**Effort:** 2-3 days
**Priority:** LOW

---

### 18. Create Troubleshooting Flowcharts

**Current State:**
- Text-based troubleshooting guides
- No structured debugging process
- Common issues not documented

**Recommendation:**
Add troubleshooting flowcharts:

```markdown
# docs/troubleshooting/asset-materialization-failed.md

## Asset Materialization Failed

​```mermaid
graph TD
    A[Asset materialization failed] --> B{Check error message}
    B -->|Neo4j connection| C[Neo4j Troubleshooting]
    B -->|S3 access| D[S3 Troubleshooting]
    B -->|Data quality| E[Data Quality Checks]
    B -->|Other| F[Check Logs]

    C --> C1{Can connect to Neo4j?}
    C1 -->|No| C2[Check credentials]
    C1 -->|Yes| C3[Check query syntax]

    D --> D1{AWS credentials valid?}
    D1 -->|No| D2[Refresh credentials]
    D1 -->|Yes| D3[Check IAM permissions]

    E --> E1{Which check failed?}
    E1 -->|Pass rate| E2[Lower threshold or fix data]
    E1 -->|Completeness| E3[Add missing fields]
​```
```

**Benefits:**
- Faster issue resolution
- Consistent debugging process
- Reduced support burden

**Effort:** 2-3 days
**Priority:** MEDIUM

---

### 19. Add Video Walkthroughs

**Current State:**
- Text-only documentation
- Complex setup hard to follow
- No visual learning resources

**Recommendation:**
Create short video tutorials:

1. **Quick Start (5 min)**: Clone → Setup → First Materialization
2. **Docker Compose (3 min)**: Build → Run → Access Services
3. **Dagster Cloud Deploy (7 min)**: Setup → Configure → Deploy
4. **AWS Infrastructure (10 min)**: CDK → Deploy → Verify
5. **Troubleshooting (5 min)**: Common Issues → Solutions

**Hosting:**
- GitHub README embedded videos
- YouTube private/unlisted links
- Loom for quick recordings

**Benefits:**
- Faster onboarding
- Visual learning
- Reduced support questions

**Effort:** 1-2 days
**Priority:** LOW

---

### 20. Create Developer Cheat Sheet

**Current State:**
- Commands scattered across docs
- No quick reference guide
- Frequent doc searching

**Recommendation:**
Create `docs/cheatsheet.md`:

```markdown
# SBIR Analytics Cheat Sheet

## Quick Start
​```bash
# Native Python
uv sync && uv run dagster dev -m src.definitions

# Docker Compose
make docker-build && make docker-up-dev
​```

## Common Commands
​```bash
# Testing
uv run pytest -v                    # All tests
uv run pytest -m "not slow"         # Fast tests only
make docker-test                    # Tests in Docker

# Assets
dagster asset materialize -m src.definitions raw_sbir_awards
dagster asset list -m src.definitions

# Neo4j
uv run python scripts/neo4j/apply_schema.py
uv run python scripts/neo4j/clear_database.py

# AWS
cd infrastructure/cdk && cdk deploy --all
aws stepfunctions start-execution --state-machine-arn ...
​```

## Troubleshooting One-Liners
​```bash
# Check Neo4j connection
echo "RETURN 1" | cypher-shell -a bolt://localhost:7687 -u neo4j -p password

# Check Dagster UI
curl -s http://localhost:3000/server_info | jq

# Check Docker services
docker compose ps

# View Lambda logs
aws logs tail /aws/lambda/sbir-analytics-download-csv --follow

# Check S3 bucket
aws s3 ls s3://sbir-etl-production-data/ --recursive --human-readable
​```

## Configuration Quick Reference
​```bash
# Neo4j
NEO4J_URI=neo4j+s://...
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# S3
SBIR_ETL__S3__BUCKET=sbir-etl-production-data
SBIR_ETL__S3__USE_S3=true

# Data Quality
SBIR_ETL__DATA_QUALITY__SBIR__PASS_RATE=0.95
​```

## Useful Cypher Queries
​```cypher
// Count nodes by type
MATCH (n) RETURN labels(n), count(*);

// Find recent awards
MATCH (a:Award)
WHERE a.award_date >= date('2024-01-01')
RETURN a.award_id, a.company_name, a.amount
ORDER BY a.award_date DESC
LIMIT 10;

// Find high-value transitions
MATCH (a:Award)-[:TRANSITIONED_TO]->(t:Transition)
WHERE t.confidence = 'HIGH'
RETURN a, t
LIMIT 10;
​```

## Emergency Commands
​```bash
# Stop everything
docker compose down -v              # Docker
pkill -f dagster                    # Local Dagster

# Reset Neo4j
docker compose down -v neo4j
docker compose up -d neo4j

# Clear Dagster run history
rm -rf ~/dagster_home/history/

# Force CDK redeployment
cdk destroy --all --force
cdk deploy --all
​```
```

**Benefits:**
- Quick reference
- Copy-paste commands
- Reduced documentation searches

**Effort:** 1 day
**Priority:** HIGH

---

## Security Improvements

### 21. Implement Secret Scanning

**Current State:**
- No automated secret scanning
- Secrets could be committed accidentally
- Manual code review only

**Recommendation:**
Add secret scanning:

**A. Pre-commit Hook:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

**B. GitHub Secret Scanning:**
```yaml
# .github/workflows/secret-scan.yml
name: Secret Scan

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
```

**Benefits:**
- Prevent secret leaks
- Automated detection
- Compliance requirement

**Effort:** 1 day
**Priority:** HIGH

---

### 22. Implement Secrets Rotation Schedule

**Current State:**
- No regular secret rotation
- Long-lived credentials
- Compliance risk

**Recommendation:**
Create rotation schedule and automation:

```python
# scripts/security/rotate_secrets.py
"""Rotate secrets on schedule."""
import boto3
from datetime import datetime, timedelta

def rotate_neo4j_secret():
    """Rotate Neo4j Aura password."""
    # 1. Generate new password
    # 2. Update Neo4j Aura
    # 3. Update AWS Secrets Manager
    # 4. Notify team
    pass

def rotate_aws_credentials():
    """Rotate AWS access keys."""
    # 1. Create new access key
    # 2. Update GitHub secrets
    # 3. Test new credentials
    # 4. Delete old access key
    pass

def check_rotation_age():
    """Check if secrets need rotation."""
    secrets_client = boto3.client('secretsmanager')
    response = secrets_client.describe_secret(
        SecretId='sbir-analytics/neo4j-aura'
    )
    last_changed = response.get('LastChangedDate')
    age = (datetime.now() - last_changed).days

    if age > 90:
        print(f"⚠️  Secret is {age} days old (>90 days)")
        return True
    return False
```

**Schedule:**
- Neo4j password: Every 90 days
- AWS access keys: Every 90 days
- GitHub tokens: Every 180 days
- PatentsView API key: Yearly

**Benefits:**
- Reduced security risk
- Compliance with best practices
- Automated process

**Effort:** 2-3 days
**Priority:** MEDIUM

---

### 23. Add AWS IAM Access Analyzer

**Current State:**
- Manual IAM policy review
- No automated permission analysis
- Over-permissive policies possible

**Recommendation:**
Enable IAM Access Analyzer:

```python
# infrastructure/cdk/stacks/security_stack.py
from aws_cdk import aws_accessanalyzer as accessanalyzer

# Create analyzer
analyzer = accessanalyzer.CfnAnalyzer(
    self, 'AccessAnalyzer',
    type='ACCOUNT',
    analyzer_name='sbir-analytics-analyzer'
)

# Create findings alert
findings_rule = events.Rule(
    self, 'AccessAnalyzerFindings',
    event_pattern=events.EventPattern(
        source=['aws.access-analyzer'],
        detail_type=['Access Analyzer Finding']
    )
)

findings_rule.add_target(
    targets.SnsTopic(alert_topic)
)
```

**Benefits:**
- Identify overly permissive policies
- External access detection
- Compliance validation

**Effort:** 1 day
**Priority:** MEDIUM

---

## Implementation Roadmap

### Phase 1: Quick Wins (1-2 weeks)

**Priority: HIGH**
1. Simplify local development path selection (setup script)
2. Add pre-commit hooks
3. Enable Dagster Cloud branch deployments
4. Create developer cheat sheet
5. Implement secret scanning

**Estimated Effort:** 10-15 days
**Impact:** Immediate improvement in developer experience

---

### Phase 2: Infrastructure Improvements (2-4 weeks)

**Priority: HIGH-MEDIUM**
1. Implement infrastructure smoke tests
2. Add CloudWatch dashboards
3. Reduce Docker build time
4. Add infrastructure validation in CI/CD
5. Implement automated cost monitoring

**Estimated Effort:** 15-20 days
**Impact:** Better reliability and observability

---

### Phase 3: Documentation & DX (1-2 weeks)

**Priority:** MEDIUM**
1. Create ADRs for key decisions
2. Add troubleshooting flowcharts
3. Improve local data management
4. Add development container support
5. Create interactive diagrams

**Estimated Effort:** 8-12 days
**Impact:** Better onboarding and knowledge sharing

---

### Phase 4: Advanced Features (2-4 weeks)

**Priority: LOW-MEDIUM**
1. Add local observability stack
2. Implement blue-green deployments
3. Add canary testing
4. Multi-region disaster recovery
5. Secrets rotation automation
6. IAM Access Analyzer

**Estimated Effort:** 15-25 days
**Impact:** Production-grade reliability and security

---

## Success Metrics

**Developer Experience:**
- Onboarding time: < 30 minutes (currently ~2 hours)
- Local setup success rate: > 95% (currently ~80%)
- Time to first contribution: < 1 day (currently ~3 days)

**Reliability:**
- Deployment success rate: > 99%
- Mean time to recovery (MTTR): < 15 minutes
- Infrastructure drift: 0 (detected automatically)

**Cost:**
- Monthly AWS cost: < $50 (with monitoring)
- Cost anomalies detected: 100%
- Unused resources: 0

**Security:**
- Secret rotation compliance: 100%
- Vulnerability response time: < 24 hours
- Security findings: 0 high-severity

---

## Feedback & Iteration

This document should be reviewed quarterly and updated based on:
- Team feedback
- Incident retrospectives
- New AWS/Dagster features
- Industry best practices

**Next Review:** 2025-04-20

---

**Document Maintained By:** DevOps & Platform Team
**Last Updated:** 2025-01-20

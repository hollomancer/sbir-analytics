# Dagster Cloud Deployment

**Audience**: DevOps, Production Deployment
**Prerequisites**: GitHub access, Neo4j Aura instance
**Related**: [Docker Guide](docker.md), [AWS Deployment](aws-deployment.md)
**Last Updated**: 2025-11-29

## Overview

Dagster Cloud Solo Plan is the **primary** orchestration platform for SBIR ETL. Docker Compose is maintained as a **failover** option for local development.

### Benefits

- ✅ Fully managed (no infrastructure)
- ✅ Auto-scaling and scheduling
- ✅ GitHub integration (auto-deploy on push)
- ✅ Built-in monitoring and alerting
- ✅ Asset lineage visualization
- ✅ $10/month Solo Plan (30-day free trial)

### Architecture

```
GitHub Repository
    ↓ (push to main)
Dagster Cloud
    ↓ (executes)
Assets & Jobs
    ↓ (writes to)
Neo4j Aura + S3
```

## Quick Start

### 1. Create Account

1. Visit [cloud.dagster.io](https://cloud.dagster.io)
2. Sign up with GitHub
3. Start 30-day free trial
4. Select Solo Plan

### 2. Connect Repository

1. **Settings** → **Code Locations** → **Connect Repository**
2. Authorize Dagster Cloud
3. Select `sbir-analytics` repository

### 3. Create Code Location

**Configuration:**
- Name: `sbir-analytics-production`
- Type: Python module
- Module: `src.definitions`
- Branch: `main`
- Python: 3.11

### 4. Set Environment Variables

**Required:**
```bash
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>  # pragma: allowlist secret
```

**Optional:**
```bash
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>  # pragma: allowlist secret
SBIR_ETL__PIPELINE__ENVIRONMENT=production
```

### 5. Deploy

Dagster Cloud auto-deploys on push to `main`. Manual deploy:
1. **Deployments** → **Redeploy**
2. Wait for build to complete
3. Verify assets load

### 6. Verify

1. **Assets** → Check all assets visible
2. **Jobs** → Verify jobs listed
3. Materialize test asset
4. Check Neo4j connection in logs

## Deployment Methods

### UI-Based Deployment (Recommended)

**Best for**: Initial setup, non-technical users

**Steps:**
1. Configure via Dagster Cloud web interface
2. Set environment variables in UI
3. Auto-deploy on git push

**Pros:**
- Easy setup
- Visual configuration
- No CLI required

### CLI-Based Deployment

**Best for**: CI/CD, automation, advanced users

**Setup:**
```bash
# Install CLI
pip install dagster-cloud

# Get API token from Dagster Cloud UI
# Settings → Tokens → Create Token

# Authenticate
export DAGSTER_CLOUD_API_TOKEN=<token>
dagster-cloud config set-user-token

# Deploy
dagster-cloud workspace add-location \
  --location-name sbir-analytics-production \
  --module-name src.definitions \
  --python-version 3.11
```

**Pros:**
- Scriptable
- CI/CD integration
- Version control

## Configuration

### Code Location Settings

**File**: `pyproject.toml`
```toml
[tool.dg.project]
root_module = "src"
defs_module = "src.definitions"
code_location_target_module = "src.definitions"
code_location_name = "sbir-analytics-production"
```

### Environment Variables

**Neo4j Connection:**
```bash
NEO4J_URI=neo4j+s://<instance>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>  # pragma: allowlist secret
NEO4J_DATABASE=neo4j  # Optional
```

**AWS S3 Access:**
```bash
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>  # pragma: allowlist secret
AWS_REGION=us-east-2
```

**Pipeline Configuration:**
```bash
SBIR_ETL__PIPELINE__ENVIRONMENT=production
SBIR_ETL__NEO4J__BATCH_SIZE=2000
SBIR_ETL__ENRICHMENT__BATCH_SIZE=200
```

See [Configuration Patterns](.kiro/steering/configuration-patterns.md) for complete reference.

### Multiple Neo4j Instances

**Solo Plan Limitation**: 1 code location = 1 set of environment variables

**Workaround**: Use branch-based deployments

```bash
# Production (main branch)
NEO4J_URI=neo4j+s://prod.databases.neo4j.io

# Staging (staging branch)
NEO4J_URI=neo4j+s://staging.databases.neo4j.io
```

**Alternative**: Upgrade to Starter Plan for multiple deployments

## Testing

### Quick Smoke Test (5 minutes)

1. **Verify Deployment:**
   - **Deployments** → Check status is "Deployed"
   - **Code Locations** → Verify green checkmark

2. **Test Assets:**
   - **Assets** → Select lightweight asset
   - Click **Materialize**
   - Wait for completion
   - Check logs for errors

3. **Test Neo4j:**
   - Materialize asset that writes to Neo4j
   - Check logs for connection success
   - Verify data in Neo4j Browser

### Comprehensive Test Suite

**Test 1: Code Location**
```bash
# Verify code location loads
dagster-cloud workspace list-locations
```

**Test 2: Assets Load**
- Navigate to **Assets**
- Verify all asset groups visible
- Check for loading errors

**Test 3: Environment Variables**
- Materialize test asset
- Check logs for env var values
- Verify Neo4j URI is correct

**Test 4: Neo4j Connection**
```python
# Test asset
@asset
def test_neo4j_connection(context):
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    )
    driver.verify_connectivity()
    context.log.info("✓ Neo4j connection successful")
```

**Test 5: Job Execution**
- **Jobs** → Select small job
- Click **Launch Run**
- Monitor execution
- Verify completion

**Test 6: Schedules**
- **Schedules** → Verify schedules listed
- Enable test schedule
- Wait for next tick
- Verify execution

## Monitoring

### Built-in Monitoring

**Dagster Cloud provides:**
- Run history and logs
- Asset materialization tracking
- Job execution metrics
- Error alerting
- Performance dashboards

**Access:**
- **Runs** → View all executions
- **Assets** → View materialization history
- **Monitoring** → View metrics

### Custom Alerts

**Configure in UI:**
1. **Settings** → **Alerts**
2. **Create Alert**
3. Configure conditions:
   - Job failure
   - Asset staleness
   - Run duration threshold

**Notification Channels:**
- Email
- Slack
- PagerDuty
- Webhook

### Logging

**View Logs:**
- **Runs** → Select run → **Logs** tab
- Filter by level (INFO, WARNING, ERROR)
- Search logs
- Download logs

**Structured Logging:**
```python
@asset
def my_asset(context):
    context.log.info("Processing started", extra={"count": 100})
    context.log.warning("Low memory", extra={"available_mb": 500})
    context.log.error("Failed to connect", extra={"host": "example.com"})
```

## Cost Management

### Solo Plan Pricing

- **$10/month** after 30-day trial
- **7,500 Dagster Credits/month** included
- **1 user, 1 code location, 1 deployment**

### Credit Usage

**Credits consumed by:**
- Asset materializations
- Job executions
- Sensor evaluations
- Schedule ticks

**Optimize usage:**
- Use sensors instead of frequent schedules
- Batch asset materializations
- Optimize job execution time
- Use incremental processing

### Monitor Usage

**Dashboard:**
- **Settings** → **Usage**
- View credit consumption
- Set usage alerts
- Upgrade if needed

## Troubleshooting

### Deployment Fails

**Symptoms**: Code location shows error, assets don't load

**Solutions:**
1. Check build logs in **Deployments**
2. Verify `pyproject.toml` has `[tool.dg.project]`
3. Check Python version (must be 3.11)
4. Verify module path: `src.definitions`

### Assets Not Loading

**Symptoms**: Assets tab empty or shows errors

**Solutions:**
1. Check code location status
2. Verify `src/definitions.py` exports `defs`
3. Check for import errors in logs
4. Verify all dependencies in `pyproject.toml`

### Environment Variables Not Working

**Symptoms**: Jobs fail with missing config

**Solutions:**
1. Verify variables set in code location config
2. Check variable names (case-sensitive)
3. Redeploy after adding variables
4. Check logs for actual values (mask secrets)

### Neo4j Connection Fails

**Symptoms**: "Failed to connect to Neo4j"

**Solutions:**
1. Verify `NEO4J_URI` format: `neo4j+s://...`
2. Check credentials are correct
3. Verify Neo4j Aura instance is running
4. Check firewall rules (Dagster Cloud IPs)

### Schedules Not Running

**Symptoms**: Schedule exists but doesn't execute

**Solutions:**
1. Verify schedule is **enabled**
2. Check schedule definition in code
3. Verify timezone settings
4. Check execution history for errors

## Rollback to Docker Compose

If Dagster Cloud is unavailable, use Docker Compose failover:

```bash
# Stop Dagster Cloud deployments (if needed)
# Start local Docker Compose
make docker-up-prod

# Verify services
make docker-verify

# Access Dagster UI
open http://localhost:3000
```

See [Docker Guide](docker.md) for complete instructions.

## Support

### Dagster Cloud Support

- **Documentation**: [docs.dagster.io/deployment/dagster-plus](https://docs.dagster.io/deployment/dagster-plus)
- **Community Slack**: [dagster.io/slack](https://dagster.io/slack)
- **GitHub Issues**: [dagster-io/dagster](https://github.com/dagster-io/dagster)

### Project Support

- **Documentation**: [docs/](../index.md)
- **Issues**: [GitHub Issues](https://github.com/hollomancer/sbir-analytics/issues)

## Related Documentation

- [Docker Guide](docker.md) - Local development and failover
- [AWS Deployment](aws-deployment.md) - AWS Lambda and Step Functions
- [Testing Guide](../testing/index.md) - Testing in Dagster Cloud
- [Configuration Patterns](.kiro/steering/configuration-patterns.md) - Environment variables

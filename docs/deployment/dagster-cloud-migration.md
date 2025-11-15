# Dagster Cloud Solo Migration Guide

**Date**: January 2025  
**Status**: Primary deployment method (Docker Compose available as failover)

---

## Overview

This guide documents the migration from Docker Compose-based Dagster deployment to Dagster Cloud Solo Plan. Dagster Cloud is now the **primary** deployment method, with Docker Compose maintained as a **failover** option for local development and emergency scenarios.

**Deployment Options**:
- **UI-Based** (this guide): Configure via Dagster Cloud web interface
- **CLI-Based Serverless**: Deploy using `dagster-cloud` CLI - See `docs/deployment/dagster-cloud-serverless-cli.md`

## Benefits of Dagster Cloud

- ✅ No container orchestration management
- ✅ Built-in scheduling and monitoring
- ✅ Automatic scaling
- ✅ Integrated with GitHub for deployments
- ✅ Built-in alerting and notifications
- ✅ Asset lineage visualization
- ✅ Environment variable management via UI
- ✅ Automatic deployments on git push

## Prerequisites

- GitHub repository access
- Neo4j Aura instance (already configured)
- Dagster Cloud account (Solo Plan - $10/month after 30-day free trial)

---

## Step 1: Create Dagster Cloud Account

1. Visit [https://cloud.dagster.io](https://cloud.dagster.io)
2. Sign up with your GitHub account (recommended) or email
3. Start the **30-day free trial** (no credit card required)
4. Select **Solo Plan** ($10/month after trial)
   - 1 user
   - 1 code location
   - 7,500 Dagster Credits/month
   - 1 deployment

---

## Step 2: Connect GitHub Repository

1. In Dagster Cloud UI, navigate to **Settings** → **Code Locations**
2. Click **Connect Repository**
3. Authorize Dagster Cloud to access your GitHub account
4. Select the `sbir-etl` repository
5. Grant necessary permissions (read access to repository)

---

## Step 3: Create Code Location

1. In Dagster Cloud UI, click **Add Code Location**
2. Configure the code location:
   - **Name**: `sbir-etl-production`
   - **Type**: Python module
   - **Module**: `src.definitions`
   - **Branch**: `main` (or your preferred branch)
   - **Python Version**: 3.11
3. Click **Create Code Location**

**Important**: Your `pyproject.toml` must include a `[tool.dg.project]` block for Dagster Cloud (Dagster+) to recognize your project. This has already been configured in the repository:

```toml
[tool.dg.project]
root_module = "src"
defs_module = "src.definitions"
code_location_target_module = "src.definitions"
code_location_name = "sbir-etl-production"
```

Dagster Cloud will automatically detect your `pyproject.toml` and install dependencies.

---

## Step 4: Configure Environment Variables

Navigate to your code location → **Configuration** → **Environment Variables** and add:

### Required: Neo4j Aura Connection

```
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
NEO4J_DATABASE=neo4j
```

**Note**: If you have multiple Neo4j instances (free and paid), you can switch between them by updating these environment variables. See `docs/deployment/dagster-cloud-multiple-neo4j-instances.md` for detailed guidance on managing multiple instances.

### Optional: Pipeline Configuration

```
SBIR_ETL__PIPELINE__ENVIRONMENT=production
SBIR_ETL__LOGGING__LEVEL=INFO
PYTHONUNBUFFERED=1
```

### Optional: Schedule Overrides

If you need to override default schedule times:

```
SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB=0 2 * * *
SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB=0 2 * * *
SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB=0 6 * * *
```

**Note**: Environment variables can be updated at any time without redeployment.

---

## Step 5: Initial Deployment

1. After creating the code location, Dagster Cloud will automatically trigger the first deployment
2. Monitor the **Deployment** tab for build progress
3. Check build logs for any dependency issues
4. Once deployment completes, verify:
   - All 117 assets are visible
   - All 10 jobs are listed
   - All 3 schedules are configured
   - Sensor is registered

---

## Step 6: Verify Deployment

### Verify Assets and Jobs

1. Navigate to **Assets** tab in Dagster Cloud UI
2. Confirm all assets are visible (should show ~117 assets)
3. Navigate to **Jobs** tab
4. Verify all 10 jobs are listed:
   - `sbir_ingestion_job`
   - `sbir_etl_job`
   - `cet_full_pipeline_job`
   - `cet_drift_job`
   - `transition_mvp_job`
   - `transition_full_job`
   - `transition_analytics_job`
   - `usaspending_iterative_enrichment_job`
   - `fiscal_returns_mvp_job`
   - `fiscal_returns_full_job`

### Verify Schedules

1. Navigate to **Schedules** tab
2. Verify all 3 schedules are configured:
   - `daily_sbir_etl`: Runs daily at 02:00 UTC
   - `daily_cet_full_pipeline`: Runs daily at 02:00 UTC
   - `daily_cet_drift_detection`: Runs daily at 06:00 UTC

### Verify Sensor

1. Navigate to **Sensors** tab
2. Verify `usaspending_refresh_sensor` is registered and active

### Test Job Execution

1. Navigate to **Jobs** → `sbir_ingestion_job`
2. Click **Materialize** to trigger a manual run
3. Monitor execution in the **Runs** tab
4. Verify execution completes successfully
5. Check logs for any errors
6. Verify Neo4j connection works (check for successful writes)

---

## Step 7: Configure Automatic Deployments (Optional)

Dagster Cloud can automatically deploy on git push:

1. Navigate to code location settings
2. Enable **Auto-deploy on push**
3. Select branch (typically `main`)
4. Save settings

Now, every push to the selected branch will trigger an automatic deployment.

---

## Docker Compose Failover

Docker Compose remains available as a failover option for:

- **Local development**: Use Docker Compose for faster iteration
- **Emergency scenarios**: If Dagster Cloud is unavailable
- **Testing**: Isolated testing environment

### Using Docker Compose

```bash
# Start Docker Compose services
make docker-up-dev

# Or manually
docker compose --profile dev up -d

# Access Dagster UI
# http://localhost:3000
```

### When to Use Each

| Scenario | Use Dagster Cloud | Use Docker Compose |
|----------|-------------------|-------------------|
| Production deployments | ✅ Primary | ❌ |
| Scheduled jobs | ✅ Primary | ❌ |
| Local development | ⚠️ Optional | ✅ Recommended |
| Emergency failover | ❌ | ✅ |
| Testing new features | ⚠️ Optional | ✅ Recommended |

---

## Troubleshooting

### Deployment Fails

**Issue**: Code location fails to deploy

**Solutions**:
1. Check build logs in Dagster Cloud UI
2. Verify `pyproject.toml` has all required dependencies
3. Ensure Python version matches (3.11)
4. Check for syntax errors in `src/definitions.py`

### Missing PyProjectDagsterBlockException

**Issue**: Error message: `MissingPyProjectDagsterBlockException: Repository contains a pyproject.toml file that is missing or invalid tool.dagster / tool.dg.project block`

**Solution**: 
This error occurs because Dagster Cloud (Dagster+) requires a `[tool.dg.project]` block in `pyproject.toml`. Ensure your `pyproject.toml` includes:

```toml
[tool.dg.project]
root_module = "src"
defs_module = "src.definitions"
code_location_target_module = "src.definitions"
code_location_name = "sbir-etl-production"
```

This configuration has been added to the repository. If you're still seeing this error, ensure you've pulled the latest changes.

### Assets Not Loading

**Issue**: Assets don't appear in Dagster Cloud UI

**Solutions**:
1. Verify module path is correct (`src.definitions`)
2. Check that `Definitions` object is named `defs` in `src/definitions.py`
3. Review deployment logs for import errors
4. Ensure all asset modules are importable

### Environment Variables Not Working

**Issue**: Environment variables not being picked up

**Solutions**:
1. Verify variables are set in code location configuration (not deployment-level)
2. Check variable names match expected format (`NEO4J_URI`, `SBIR_ETL__...`)
3. Redeploy code location after adding variables
4. Check logs for environment variable errors

### Neo4j Connection Fails

**Issue**: Cannot connect to Neo4j Aura

**Solutions**:
1. Verify `NEO4J_URI` is correct (should start with `neo4j+s://`)
2. Check `NEO4J_USER` and `NEO4J_PASSWORD` are correct
3. Ensure Neo4j Aura instance is not paused (free tier auto-pauses after 3 days)
4. Check network connectivity from Dagster Cloud

### Schedules Not Running

**Issue**: Scheduled jobs don't execute

**Solutions**:
1. Verify schedules are enabled in Dagster Cloud UI
2. Check cron expressions are correct
3. Ensure code location deployment was successful
4. Check schedule execution logs for errors

---

## Monitoring and Observability

### Dagster Cloud UI Features

- **Asset Lineage**: Visualize asset dependencies
- **Run History**: View all job executions
- **Logs**: Access execution logs for debugging
- **Metrics**: Monitor job performance and success rates
- **Alerts**: Set up notifications for failures

### Accessing Logs

1. Navigate to **Runs** tab
2. Click on a specific run
3. View logs for each step/asset
4. Filter by log level (INFO, WARNING, ERROR)

---

## Cost Management

### Solo Plan Limits

- **7,500 Dagster Credits/month**
- Credits are consumed by:
  - Job executions
  - Asset materializations
  - Schedule runs

### Monitoring Usage

1. Navigate to **Settings** → **Usage**
2. View credit consumption
3. Monitor trends to ensure you stay within limits

### If You Exceed Limits

- Upgrade to Starter Plan ($100/month, 30,000 credits)
- Optimize job execution frequency
- Reduce unnecessary asset materializations

---

## Rollback to Docker Compose

If you need to rollback to Docker Compose:

1. Stop using Dagster Cloud (disable code location or pause schedules)
2. Start Docker Compose services:
   ```bash
   make docker-up-dev
   ```
3. Access Dagster UI at `http://localhost:3000`
4. All jobs, schedules, and sensors will work identically

**Note**: No code changes required - same `src/definitions.py` works for both.

---

## Support and Resources

- **Dagster Cloud Docs**: https://docs.dagster.io/dagster-cloud
- **Dagster Community**: https://dagster.io/community
- **Status Page**: https://status.dagster.io
- **Support**: Available via Dagster Cloud UI

---

## Migration Checklist

- [ ] Dagster Cloud account created
- [ ] GitHub repository connected
- [ ] Code location created (`sbir-etl-production`)
- [ ] Environment variables configured
- [ ] Initial deployment successful
- [ ] All 117 assets visible
- [ ] All 10 jobs visible and executable
- [ ] All 3 schedules configured correctly
- [ ] Sensor registered and functional
- [ ] Test job execution successful
- [ ] Neo4j Aura connection verified
- [ ] Automatic deployments configured (optional)
- [ ] Team notified of migration
- [ ] Documentation updated

---

## Testing Your Deployment

After setting up Dagster Cloud, follow the comprehensive testing guide to verify everything works:

**See**: `docs/deployment/dagster-cloud-testing-guide.md` for step-by-step testing instructions.

### Quick Test Checklist

1. ✅ Code location deploys successfully
2. ✅ All assets visible (~117 assets)
3. ✅ All jobs visible (10 jobs)
4. ✅ Environment variables configured
5. ✅ Neo4j connection works
6. ✅ Test job executes successfully
7. ✅ Data loads to Neo4j

## Next Steps

After successful migration and testing:

1. Monitor first few scheduled runs
2. Set up alerts for job failures
3. Configure team access (if upgrading to Starter Plan)
4. Document any custom configurations
5. Update CI/CD if needed to work with Dagster Cloud


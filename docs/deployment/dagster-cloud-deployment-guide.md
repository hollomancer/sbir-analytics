# Dagster Cloud Deployment Guide

This guide provides comprehensive instructions for deploying the SBIR ETL pipeline to Dagster Cloud, covering setup, configuration, deployment, testing, and advanced topics. Dagster Cloud is the **primary** deployment method, with Docker Compose maintained as a **failover** option for local development and emergency scenarios.

## Table of Contents

1.  [Overview](#1-overview)
2.  [Benefits of Dagster Cloud](#2-benefits-of-dagster-cloud)
3.  [Prerequisites](#3-prerequisites)
4.  [Setup: UI-Based Deployment](#4-setup-ui-based-deployment)
    *   [Step 1: Create Dagster Cloud Account](#step-1-create-dagster-cloud-account)
    *   [Step 2: Connect GitHub Repository](#step-2-connect-github-repository)
    *   [Step 3: Create Code Location](#step-3-create-code-location)
    *   [Step 4: Configure Environment Variables](#step-4-configure-environment-variables)
    *   [Step 5: Initial Deployment](#step-5-initial-deployment)
    *   [Step 6: Verify Deployment](#step-6-verify-deployment)
    *   [Step 7: Configure Automatic Deployments (Optional)](#step-7-configure-automatic-deployments-optional)
5.  [Setup: CLI-Based Serverless Deployment](#5-setup-cli-based-serverless-deployment)
    *   [Step 1: Install dagster-cloud CLI](#step-1-install-dagster-cloud-cli)
    *   [Step 2: Get Dagster Cloud API Token](#step-2-get-dagster-cloud-api-token)
    *   [Step 3: Create dagster_cloud.yaml](#step-3-create-dagster_cloudyaml)
    *   [Step 4: Authenticate with Dagster Cloud](#step-4-authenticate-with-dagster-cloud)
    *   [Step 5: Deploy to Serverless](#step-5-deploy-to-serverless)
    *   [Step 6: Configure Environment Variables (CLI)](#step-6-configure-environment-variables-cli)
    *   [Step 7: Verify CLI Deployment](#step-7-verify-cli-deployment)
6.  [Understanding Code Locations](#6-understanding-code-locations)
7.  [Managing Multiple Neo4j Instances](#7-managing-multiple-neo4j-instances)
    *   [Setup: Multiple Neo4j Instances](#setup-multiple-neo4j-instances)
    *   [Switching Between Instances](#switching-between-instances)
    *   [Recommended Workflow](#recommended-workflow)
    *   [Verification Steps](#verification-steps)
    *   [Best Practices](#best-practices)
    *   [Alternative: Upgrade to Starter Plan](#alternative-upgrade-to-starter-plan)
8.  [Testing Your Dagster Cloud Deployment](#8-testing-your-dagster-cloud-deployment)
    *   [Quick Start: 5-Minute Test](#quick-start-5-minute-test)
    *   [Test 1: Verify Code Location Deployment](#test-1-verify-code-location-deployment)
    *   [Test 2: Verify Assets and Jobs Load](#test-2-verify-assets-and-jobs-load)
    *   [Test 3: Verify Environment Variables](#test-3-verify-environment-variables)
    *   [Test 4: Test Neo4j Connection](#test-4-test-neo4j-connection)
    *   [Test 5: Test Job Execution (Small Job)](#test-5-test-job-execution-small-job)
    *   [Test 6: Test Neo4j Data Loading](#test-6-test-neo4j-data-loading)
    *   [Test 7: Test Multiple Neo4j Instance Switching](#test-7-test-multiple-neo4j-instance-switching)
    *   [Test 8: Test Schedules](#test-8-test-schedules)
    *   [Test 9: Test Sensor](#test-9-test-sensor)
    *   [Test 10: End-to-End Pipeline Test](#test-10-end-to-end-pipeline-test)
9.  [S3 Data Migration and Access](#9-s3-data-migration-and-access)
    *   [Overview](#overview)
    *   [Configuration](#configuration)
    *   [Data Migration Steps](#data-migration-steps)
    *   [How It Works](#how-it-works)
    *   [Testing S3 Access](#testing-s3-access)
    *   [AWS Credentials for Dagster Cloud](#aws-credentials-for-dagster-cloud)
10. [Troubleshooting](#10-troubleshooting)
    *   [Deployment Fails](#deployment-fails)
    *   [Missing PyProjectDagsterBlockException](#missing-pyprojectdagsterblockexception)
    *   [Assets Not Loading](#assets-not-loading)
    *   [Environment Variables Not Working](#environment-variables-not-working)
    *   [Neo4j Connection Fails](#neo4j-connection-fails)
    *   [Schedules Not Running](#schedules-not-running)
    *   [Authentication Fails (CLI)](#authentication-fails-cli)
    *   [Deployment Fails (CLI)](#deployment-fails-cli)
    *   [Environment Variables Not Working (CLI)](#environment-variables-not-working-cli)
    *   [Module Not Found (CLI)](#module-not-found-cli)
    *   [ConnectionResetError or RequestTimeout (CLI)](#connectionreseterror-or-requesttimeout-cli)
11. [Monitoring and Observability](#11-monitoring-and-observability)
12. [Cost Management](#12-cost-management)
13. [Rollback to Docker Compose](#13-rollback-to-docker-compose)
14. [Support and Resources](#14-support-and-resources)
15. [Deployment Checklist](#15-deployment-checklist)

---

## 1. Overview

This guide documents the migration from Docker Compose-based Dagster deployment to Dagster Cloud Solo Plan. Dagster Cloud is now the **primary** deployment method, with Docker Compose maintained as a **failover** option for local development and emergency scenarios.

**Deployment Options**:
- **UI-Based**: Configure via Dagster Cloud web interface
- **CLI-Based Serverless**: Deploy using `dagster-cloud` CLI

## 2. Benefits of Dagster Cloud

- ✅ No container orchestration management
- ✅ Built-in scheduling and monitoring
- ✅ Automatic scaling
- ✅ Integrated with GitHub for deployments
- ✅ Built-in alerting and notifications
- ✅ Asset lineage visualization
- ✅ Environment variable management via UI
- ✅ Automatic deployments on git push

## 3. Prerequisites

- GitHub repository access
- Neo4j Aura instance (already configured)
- Dagster Cloud account (Solo Plan - $10/month after 30-day free trial)

## 4. Setup: UI-Based Deployment

### Step 1: Create Dagster Cloud Account

1. Visit [https://cloud.dagster.io](https://cloud.dagster.io)
2. Sign up with your GitHub account (recommended) or email
3. Start the **30-day free trial** (no credit card required)
4. Select **Solo Plan** ($10/month after trial)
   - 1 user
   - 1 code location
   - 7,500 Dagster Credits/month
   - 1 deployment

### Step 2: Connect GitHub Repository

1. In Dagster Cloud UI, navigate to **Settings** → **Code Locations**
2. Click **Connect Repository**
3. Authorize Dagster Cloud to access your GitHub account
4. Select the `sbir-etl` repository
5. Grant necessary permissions (read access to repository)

### Step 3: Create Code Location

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

### Step 4: Configure Environment Variables

Navigate to your code location → **Configuration** → **Environment Variables** and add:

#### Required: Neo4j Aura Connection

```
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
NEO4J_DATABASE=neo4j
```

**Note**: If you have multiple Neo4j instances (free and paid), you can switch between them by updating these environment variables. See [Managing Multiple Neo4j Instances](#7-managing-multiple-neo4j-instances) for detailed guidance.

#### Optional: Pipeline Configuration

```
SBIR_ETL__PIPELINE__ENVIRONMENT=production
SBIR_ETL__LOGGING__LEVEL=INFO
PYTHONUNBUFFERED=1
```

#### Optional: Schedule Overrides

If you need to override default schedule times:

```
SBIR_ETL__DAGSTER__SCHEDULES__ETL_JOB=0 2 * * *
SBIR_ETL__DAGSTER__SCHEDULES__CET_FULL_PIPELINE_JOB=0 2 * * *
SBIR_ETL__DAGSTER__SCHEDULES__CET_DRIFT_JOB=0 6 * * *
```

**Note**: Environment variables can be updated at any time without redeployment.

### Step 5: Initial Deployment

1. After creating the code location, Dagster Cloud will automatically trigger the first deployment
2. Monitor the **Deployment** tab for build progress
3. Check build logs for any dependency issues
4. Once deployment completes, verify:
   - All 117 assets are visible
   - All 10 jobs are listed
   - All 3 schedules are configured
   - Sensor is registered

### Step 6: Verify Deployment

#### Verify Assets and Jobs

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

#### Verify Schedules

1. Navigate to **Schedules** tab
2. Verify all 3 schedules are configured:
   - `daily_sbir_etl`: Runs daily at 02:00 UTC
   - `daily_cet_full_pipeline`: Runs daily at 02:00 UTC
   - `daily_cet_drift_detection`: Runs daily at 06:00 UTC

#### Verify Sensor

1. Navigate to **Sensors** tab
2. Verify `usaspending_refresh_sensor` is registered and active

#### Test Job Execution

1. Navigate to **Jobs** → `sbir_ingestion_job`
2. Click **Materialize** to trigger a manual run
3. Monitor execution in the **Runs** tab
4. Verify execution completes successfully
5. Check logs for any errors
6. Verify Neo4j connection works (check for successful writes)

### Step 7: Configure Automatic Deployments (Optional)

Dagster Cloud can automatically deploy on git push:

1. Navigate to code location settings
2. Enable **Auto-deploy on push**
3. Select branch (typically `main`)
4. Save settings

Now, every push to the selected branch will trigger an automatic deployment.

## 5. Setup: CLI-Based Serverless Deployment

This section covers deploying to Dagster Cloud Serverless using the `dagster-cloud` CLI tool, which provides a command-line alternative to the UI-based deployment method.

### Step 1: Install dagster-cloud CLI

#### Option A: Using pip

```bash
pip install dagster-cloud
```

#### Option B: Using uv (Recommended)

```bash
```bash
pip install dagster-cloud
```

#### Option C: Add to Project Dependencies

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "dagster-cloud>=1.7.0,<2.0.0",
]
```

Then install:

```bash
uv sync
```

### Step 2: Get Dagster Cloud API Token

1. **Navigate to Dagster Cloud UI**
   - Go to https://cloud.dagster.io
   - Sign in to your account

2. **Generate API Token**
   - Go to **Settings** → **API Tokens**
   - Click **Create API Token**
   - Copy the token (you'll only see it once)
   - Save it securely

3. **Set Environment Variable**
   ```bash
   export DAGSTER_CLOUD_API_TOKEN="your-api-token-here"
   ```

   Or add to your shell profile (`~/.zshrc` or `~/.bashrc`):
   ```bash
   echo 'export DAGSTER_CLOUD_API_TOKEN="your-api-token-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

### Step 3: Create dagster_cloud.yaml

Create a `dagster_cloud.yaml` file in your project root:

```yaml
locations:
  - location_name: sbir-etl-production
    code_source:
      python_module: src.definitions
    build:
      python_version: "3.11"
```

**Configuration Options**:

- `location_name`: Name for your code location (matches `code_location_name` in `pyproject.toml`)
- `code_source.python_module`: Module path to your Definitions object (`src.definitions`)
- `build.python_version`: Python version to use

**Advanced Configuration**:

```yaml
locations:
  - location_name: sbir-etl-production
    code_source:
      python_module: src.definitions
    build:
      python_version: "3.11"
      # Optional: specify build steps
      # build_steps:
      #   - pip install -r requirements.txt
    # Optional: specify branch
    # git:
    #   branch: main
```

### Step 4: Authenticate with Dagster Cloud

```bash
dagster-cloud auth login
```

This will:
1. Prompt for your API token (or use `DAGSTER_CLOUD_API_TOKEN` env var)
2. Authenticate your CLI session
3. Save credentials locally

**Verify Authentication**:

```bash
dagster-cloud auth status
```

Should show your organization and deployment info.

### Step 5: Deploy to Serverless

**Important**: Serverless deployment requires Docker to be running, as it builds a Docker image of your code.

#### Prerequisites

1.  **Docker must be running**:
    ```bash
    # Check Docker status
    docker ps

    # If Docker isn't running, start Docker Desktop
    ```

2.  **Set Organization** (if not using default):
    ```bash
    export DAGSTER_CLOUD_ORGANIZATION="your-org-name"
    ```

#### Basic Deployment

**Deploy using module name**:

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions
```

This will:
1. Build a Docker image of your code
2. Upload to Dagster Cloud
3. Deploy to Serverless infrastructure
4. Show deployment progress

#### Deploy with Options

```bash
dagster-cloud serverless deploy-python-executable \
  --deployment prod \
  --location-name sbir-etl-production \
  --module-name src.definitions \
  --organization your-org-name
```

### Step 6: Configure Environment Variables (CLI)

#### Option A: Via CLI

```bash
dagster-cloud serverless set-env \
  --location sbir-etl-production \
  NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io \
  NEO4J_USER=neo4j \
  NEO4J_PASSWORD=your-password \
  NEO4J_DATABASE=neo4j
```

#### Option B: Via YAML File

Create `dagster_cloud_env.yaml`:

```yaml
locations:
  - location_name: sbir-etl-production
    env_vars:
      NEO4J_URI: neo4j+s://xxxxx.databases.neo4j.io
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: your-password
      NEO4J_DATABASE: neo4j
      NEO4J_INSTANCE_TYPE: paid
```

Then apply:

```bash
dagster-cloud serverless set-env --from-file dagster_cloud_env.yaml
```

### Step 7: Verify CLI Deployment

#### Check Deployment Status

```bash
dagster-cloud serverless status
```

#### List Code Locations

```bash
dagster-cloud serverless list-locations
```

#### View Deployment Logs

```bash
dagster-cloud serverless logs --location-name sbir-etl-production
```

#### Open in Browser

```bash
dagster-cloud serverless open
```

Opens Dagster Cloud UI in your browser.

## 6. Understanding Code Locations

In Dagster Cloud, a **code location** is a deployment unit that contains:
- A `Definitions` object (your assets, jobs, schedules, sensors)
- A way to load that code (GitHub repo + branch/path, or Docker image)
- Its own environment variables and configuration

Think of it as: **One code location = One deployment of your Dagster code**

Your current setup uses **1 code location** (one `Definitions` object), so:

- ✅ **Solo Plan ($10/month) would work** for a single deployment
- ✅ **Starter Plan ($100/month) gives you room to grow** (5 locations)
- ✅ **Pro Plan** only needed if you want unlimited locations

You'd want multiple code locations if you:

1.  **Separate Environments**: Production, Staging, Development
2.  **Separate Teams/Projects**: SBIR ETL Pipeline, USPTO Patent Pipeline, CET Classification Pipeline
3.  **Different Deployment Configurations**: Fast pipeline (runs every hour), Slow pipeline (runs daily)

## 7. Managing Multiple Neo4j Instances

**Challenge**: You have one Dagster Cloud instance (Solo Plan) but need to switch between multiple Neo4j instances (free and paid).

**Solution**: Update environment variables in Dagster Cloud UI to switch between Neo4j instances.

### Setup: Multiple Neo4j Instances

Keep track of your Neo4j instances:

**Free Instance (Development/Testing)**:
- URI: `neo4j+s://free-xxxxx.databases.neo4j.io`
- User: `neo4j`
- Password: `your-free-password`
- Database: `neo4j`
- Use case: Testing, development, small datasets

**Paid Instance (Production)**:
- URI: `neo4j+s://paid-xxxxx.databases.neo4j.io`
- User: `neo4j`
- Password: `your-paid-password`
- Database: `neo4j`
- Use case: Production workloads, full datasets

### Switching Between Instances

#### Method 1: Update Environment Variables (Recommended)

1.  **Navigate to Dagster Cloud UI**:
    *   Go to your code location (`sbir-etl-production`)
    *   Click **Configuration** → **Environment Variables**

2.  **Update Neo4j Connection Variables**:
    *   `NEO4J_URI` - Change to target instance URI
    *   `NEO4J_USER` - Usually `neo4j` (same for both)
    *   `NEO4J_PASSWORD` - Change to target instance password
    *   `NEO4J_DATABASE` - Usually `neo4j` (same for both)

3.  **Add Instance Identifier (Optional)**:
    *   `NEO4J_INSTANCE_TYPE` - Set to `free` or `paid` for tracking
    *   This helps identify which instance is active in logs

4.  **Save Changes**:
    *   Changes take effect immediately (no redeployment needed)
    *   Next job run will use the new instance

#### Method 2: Use Environment Variable Sets (If Available)

Some Dagster Cloud plans support environment variable sets. If available:
1. Create separate variable sets: `neo4j-free` and `neo4j-paid`
2. Switch between sets as needed
3. This keeps configurations organized

### Recommended Workflow

#### For Development/Testing

1.  **Set Free Instance Variables**:
    ```
    NEO4J_URI=neo4j+s://free-xxxxx.databases.neo4j.io
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your-free-password
    NEO4J_DATABASE=neo4j
    NEO4J_INSTANCE_TYPE=free
    ```

2.  **Run Tests/Development Jobs**:
    *   Use free instance for testing new features
    *   Verify jobs work correctly
    *   Check data loads properly

3.  **Switch to Paid Instance**:
    *   Update environment variables to paid instance
    *   Run production jobs

#### For Production

1.  **Set Paid Instance Variables**:
    ```
    NEO4J_URI=neo4j+s://paid-xxxxx.databases.neo4j.io
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your-paid-password
    NEO4J_DATABASE=neo4j
    NEO4J_INSTANCE_TYPE=paid
    ```

2.  **Run Production Jobs**:
    *   Execute scheduled jobs
    *   Monitor execution logs
    *   Verify data loads to correct instance

### Verification Steps

After switching instances, verify the connection:

1.  **Check Logs**:
    *   Navigate to **Runs** tab in Dagster Cloud UI
    *   View latest run logs
    *   Look for Neo4j connection messages
    *   Verify URI matches target instance

2.  **Test Connection**:
    *   Manually trigger a small job (e.g., `sbir_ingestion_job`)
    *   Check logs for successful Neo4j connection
    *   Verify data appears in correct Neo4j instance

3.  **Query Neo4j**:
    *   Connect to target Neo4j instance directly
    *   Run a query to verify data was loaded
    *   Check node/relationship counts

### Best Practices

1.  **Document Instance Details**: Keep a secure document (password manager) with instance URIs, usernames, passwords, use cases, and last switched date/time.
2.  **Use Naming Conventions**: Name instances clearly (e.g., `sbir-etl-free`, `sbir-etl-paid`).
3.  **Verify Before Production Runs**: Always verify environment variables before scheduled production runs.
4.  **Monitor Instance Usage**: Check Neo4j Aura console for both instances.
5.  **Use Instance Identifier Variable**: Add `NEO4J_INSTANCE_TYPE` to help track which instance is active.

### Alternative: Upgrade to Starter Plan

If you frequently switch between instances, consider upgrading to **Starter Plan** ($100/month):
- **5 code locations** - Create separate code locations for free/paid instances
- **Separate deployments** - Each instance gets its own deployment
- **Better organization** - No need to manually switch environment variables

**Trade-off**: Higher cost ($100/month vs $10/month) but better isolation and organization.

## 8. Testing Your Dagster Cloud Deployment

This section provides step-by-step instructions for testing your Dagster Cloud deployment to ensure everything is configured correctly.

### Quick Start: 5-Minute Test

**Fastest way to verify Dagster Cloud is working:**

1.  **Check Deployment**: Go to Dagster Cloud UI → Code Location → Verify deployment is "Active"
2.  **Check Assets**: Go to **Assets** tab → Verify ~117 assets are visible
3.  **Check Jobs**: Go to **Jobs** tab → Verify 10 jobs are listed
4.  **Test Connection**: Go to **Jobs** → `sbir_ingestion_job` → Click **Materialize** → Watch logs for Neo4j connection success
5.  **Verify Results**: Check **Runs** tab → Verify job completed successfully

If all 5 steps pass, your basic setup is working! Continue with detailed tests below for comprehensive verification.

### Test 1: Verify Code Location Deployment

1.  **Navigate to Dagster Cloud UI**
    *   Go to your code location (`sbir-etl-production`)
    *   Check the **Deployment** tab

2.  **Verify Deployment Status**
    *   ✅ Deployment should show "Success" or "Active"
    *   ✅ Build logs should show no errors
    *   ✅ Dependencies should be installed successfully

3.  **Check for Errors**
    *   Review build logs for any import errors
    *   Verify Python version matches (3.11)
    *   Check that all dependencies from `pyproject.toml` installed

### Test 2: Verify Assets and Jobs Load

1.  **Check Assets Tab**
    *   Navigate to **Assets** in Dagster Cloud UI
    *   Verify all assets are visible
    *   Expected: ~117 assets should appear

2.  **Check Jobs Tab**
    *   Navigate to **Jobs** in Dagster Cloud UI
    *   Verify all jobs are listed
    *   Expected jobs:
        *   `sbir_ingestion_job`
        *   `sbir_etl_job`
        *   `cet_full_pipeline_job`
        *   `cet_drift_job`
        *   `transition_mvp_job`
        *   `transition_full_job`
        *   `transition_analytics_job`
        *   `usaspending_iterative_enrichment_job`
        *   `fiscal_returns_mvp_job`
        *   `fiscal_returns_full_job`

3.  **Check Schedules Tab**
    *   Navigate to **Schedules** in Dagster Cloud UI
    *   Verify all 3 schedules are configured:
        *   `daily_sbir_etl` (02:00 UTC daily)
        *   `daily_cet_full_pipeline` (02:00 UTC daily)
        *   `daily_cet_drift_detection` (06:00 UTC daily)

4.  **Check Sensors Tab**
    *   Navigate to **Sensors** in Dagster Cloud UI
    *   Verify `usaspending_refresh_sensor` is registered

### Test 3: Verify Environment Variables

1.  **Check Environment Variables**
    *   Navigate to Code Location → **Configuration** → **Environment Variables**
    *   Verify all required variables are set:
        *   `NEO4J_URI`
        *   `NEO4J_USER`
        *   `NEO4J_PASSWORD`
        *   `NEO4J_DATABASE`

2.  **Verify Variable Values**
    *   Check that `NEO4J_URI` matches your Neo4j Aura instance
    *   Verify URI format: `neo4j+s://xxxxx.databases.neo4j.io`
    *   Confirm password is correct (not placeholder)

3.  **Test Variable Access (Optional)**
    *   Create a simple test asset that logs environment variables
    *   Or check logs from a job run to see if variables are accessible

### Test 4: Test Neo4j Connection

1.  **Run a Small Test Job**
    *   Navigate to **Jobs** → `sbir_ingestion_job`
    *   Click **Materialize** to trigger a manual run
    *   Or use a smaller test job if available

2.  **Monitor Execution**
    *   Go to **Runs** tab
    *   Click on the running job
    *   Watch logs in real-time

3.  **Check for Neo4j Connection Messages**
    *   Look for log messages like:
        *   "Connected to Neo4j"
        *   "Neo4j connection successful"
        *   Neo4j URI in connection logs
    *   Verify URI matches your configured instance

4.  **Check for Connection Errors**
    *   Look for errors like:
        *   "Connection refused"
        *   "Authentication failed"
        *   "Unable to connect"
    *   If errors occur, check environment variables

### Test 5: Test Job Execution (Small Job)

1.  **Choose a Small Test Job**
    *   Best option: `sbir_ingestion_job` (smaller, faster)
    *   Alternative: Any job that doesn't require large datasets

2.  **Trigger Manual Execution**
    *   Navigate to **Jobs** → Select job
    *   Click **Materialize** or **Launch Run**
    *   Monitor execution

3.  **Monitor Progress**
    *   Watch asset materialization progress
    *   Check for any errors or warnings
    *   Verify assets complete successfully

4.  **Check Results**
    *   Review execution logs
    *   Verify no critical errors
    *   Check that assets were materialized

### Test 6: Test Neo4j Data Loading

1.  **Run a Job That Writes to Neo4j**
    *   Example: `sbir_ingestion_job` (if it loads to Neo4j)
    *   Or any job that includes Neo4j loading assets

2.  **Monitor Neo4j Loading**
    *   Watch logs for Neo4j write operations
    *   Look for messages like:
        *   "Loading nodes to Neo4j"
        *   "Creating relationships"
        *   "MERGE operations"

3.  **Verify Data in Neo4j**
    *   Connect to your Neo4j Aura instance directly
    *   Run a query to check if data was loaded:
        ```cypher
        MATCH (n)
        RETURN count(n) as node_count
        LIMIT 1
        ```
    *   Or check for specific nodes:
        ```cypher
        MATCH (a:Award)
        RETURN count(a) as award_count
        ```

### Test 7: Test Multiple Neo4j Instance Switching

1.  **Note Current Instance**
    *   Check current `NEO4J_URI` in environment variables
    *   Note which instance is active (free or paid)

2.  **Switch to Different Instance**
    *   Update `NEO4J_URI` to different instance
    *   Update `NEO4J_PASSWORD` if different
    *   Update `NEO4J_INSTANCE_TYPE` to track switch
    *   Save changes

3.  **Verify Switch**
    *   Run a small test job
    *   Check logs for Neo4j connection URI
    *   Verify it matches the new instance

4.  **Verify Data Goes to Correct Instance**
    *   Connect to the new Neo4j instance
    *   Check if data appears there (not in old instance)
    *   Verify data isolation

5.  **Switch Back (If Needed)**
    *   Update environment variables back to original instance
    *   Verify connection works

### Test 8: Test Schedules

1.  **Verify Schedule Configuration**
    *   Navigate to **Schedules** tab
    *   Check all 3 schedules are enabled
    *   Verify cron expressions are correct

2.  **Test Schedule Manually (Optional)**
    *   Some Dagster Cloud plans allow manual schedule triggers
    *   Trigger a schedule manually to test
    *   Or wait for next scheduled run

3.  **Monitor Scheduled Run**
    *   Wait for next scheduled execution time
    *   Check **Runs** tab for scheduled runs
    *   Verify runs execute automatically

4.  **Check Schedule History**
    *   Review schedule execution history
    *   Verify runs execute at correct times
    *   Check for any failed scheduled runs

### Test 9: Test Sensor

1.  **Verify Sensor Status**
    *   Navigate to **Sensors** tab
    *   Check `usaspending_refresh_sensor` is active
    *   Verify sensor configuration

2.  **Monitor Sensor Activity**
    *   Watch sensor logs for activity
    *   Check if sensor detects changes
    *   Verify sensor triggers jobs when appropriate

3.  **Test Sensor Trigger (If Possible)**
    *   If sensor detects file changes or API updates
    *   Trigger the condition manually (if possible)
    *   Verify sensor responds correctly

### Test 10: End-to-End Pipeline Test

1.  **Run Full ETL Job**
    *   Navigate to **Jobs** → `sbir_etl_job`
    *   Trigger a manual run
    *   This tests the complete pipeline

2.  **Monitor All Stages**
    *   Watch extraction stage
    *   Monitor validation stage
    *   Check enrichment stage
    *   Verify transformation stage
    *   Confirm loading stage

3.  **Verify Data Flow**
    *   Check that data flows through all stages
    *   Verify no stage failures
    *   Check asset dependencies resolve correctly

4.  **Check Final Results**
    *   Verify data loads to Neo4j
    *   Check reports/metrics are generated
    *   Verify no critical errors

## 9. S3 Data Migration and Access

The SBIR ETL pipeline now supports S3-first data access with local fallback. This is crucial for Dagster Cloud deployments as it allows data to be stored and accessed from S3.

### Overview

The SBIR ETL pipeline now supports:
- **S3-first data access**: Automatically tries S3 before falling back to local files
- **Local fallback**: If S3 is unavailable or offline, uses local `data/raw/` directory
- **Automatic path resolution**: Builds S3 URLs from local paths when bucket is configured

### Configuration

Set the S3 bucket name via environment variable:

```bash
export SBIR_ETL__S3_BUCKET=sbir-etl-production-data
```

Or in Dagster Cloud UI:
- Go to **Settings** → **Environment Variables**
- Add: `SBIR_ETL__S3_BUCKET` = `sbir-etl-production-data`

### Data Migration Steps

1.  **Upload Files to S3**:
    ```bash
    # Upload SBIR CSV files
    aws s3 sync data/raw/sbir/ s3://sbir-etl-production-data/data/raw/sbir/ \
      --exclude "*.gitkeep" \
      --exclude ".DS_Store"

    # Upload USPTO CSV files (if needed)
    aws s3 sync data/raw/uspto/ s3://sbir-etl-production-data/data/raw/uspto/ \
      --exclude "*.gitkeep" \
      --exclude ".DS_Store"
    ```

2.  **Verify Upload**:
    ```bash
    # List files in S3
    aws s3 ls s3://sbir-etl-production-data/data/raw/sbir/ --recursive
    ```

3.  **Set Environment Variable**:
    *   **Dagster Cloud**:
        1.  Go to https://sbir.dagster.cloud/prod/settings/environment-variables
        2.  Add environment variable:
            *   Key: `SBIR_ETL__S3_BUCKET`
            *   Value: `sbir-etl-production-data`
        3.  Save changes (will trigger code location reload)

### How It Works

#### Path Resolution Flow

1.  **If `SBIR_ETL__S3_BUCKET` is set**:
    *   Builds S3 URL: `s3://sbir-etl-production-data/data/raw/sbir/awards_data.csv`
    *   Tries to access S3 file
    *   If S3 succeeds → downloads to temp cache and uses it
    *   If S3 fails → falls back to local `data/raw/sbir/awards_data.csv`

2.  **If `SBIR_ETL__S3_BUCKET` is not set**:
    *   Uses local path directly (backward compatible)

3.  **If `use_s3_first=False` (in `config/base.yaml`)**:
    *   Prefers local even if S3 is available

#### S3 File Caching

- S3 files are downloaded to `/tmp/sbir-etl-s3-cache/` (or system temp directory)
- Files are cached by MD5 hash of S3 path to avoid re-downloading
- Cache persists across runs within the same execution environment

### Testing S3 Access

1. Set `SBIR_ETL__S3_BUCKET` environment variable in Dagster Cloud UI
2. Materialize `raw_sbir_awards` asset
3. Check logs for:
    *   `"Using S3 file: s3://..."` (S3 success)
    *   `"Using local fallback: ..."` (S3 failed, using local)
    *   `"Downloaded awards_data.csv (X.XX MB)"` (S3 download)

### AWS Credentials for Dagster Cloud

Dagster Cloud Serverless uses IAM roles for S3 access. Configure:

1. Go to **Settings** → **AWS Integration**
2. Attach IAM role with S3 read permissions:
    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["s3:GetObject", "s3:ListBucket"],
          "Resource": [
            "arn:aws:s3:::sbir-etl-production-data",
            "arn:aws:s3:::sbir-etl-production-data/*"
          ]
        }
      ]
    }
    ```

## 10. Troubleshooting

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

### Authentication Fails (CLI)

**Issue**: `dagster-cloud auth login` fails

**Solutions**:
1. Verify API token is correct
2. Check `DAGSTER_CLOUD_API_TOKEN` environment variable
3. Try logging out and back in: `dagster-cloud auth logout && dagster-cloud auth login`

### Deployment Fails (CLI)

**Issue**: `dagster-cloud serverless deploy-python-executable` fails

**Solutions**:
1.  **Docker not running**: Ensure Docker Desktop is running (`docker ps` should work)
2.  **Missing location name**: Use `--location-name sbir-etl-production`
3.  **Missing module**: Use `--module-name src.definitions`
4.  Verify `pyproject.toml` has `[tool.dg.project]` block
5.  Check build logs: `dagster-cloud serverless logs --location-name sbir-etl-production`

**Common Error**: `Cannot connect to the Docker daemon`
- **Solution**: Start Docker Desktop and wait for it to fully initialize

**Common Error**: `rpy2-rinterface` compilation fails (library 'emutls_w' not found)
- **Cause**: Dagster Cloud's PEX builder is trying to compile `rpy2-rinterface` from source, which requires R and C compilation tools. The `rpy2` package is in `[project.optional-dependencies]` and is only needed for fiscal analysis features, not core ETL.
- **Solution**:
    1.  **Temporary workaround**: Comment out the `r` optional dependency in `pyproject.toml` before deploying:
        ```toml
        [project.optional-dependencies]
        # r = ["rpy2>=3.5.0,<4.0.0"]  # Temporarily disabled for Dagster Cloud deployment
        dev = [...] 
        ```
        Then restore it after deployment if needed for local development.

    2.  **Permanent solution**: If you don't need fiscal analysis features in Dagster Cloud, remove the `r` optional dependency group entirely from `pyproject.toml`.

    3.  **Alternative**: The code handles missing `rpy2` gracefully with try/except blocks, so the deployment should work even if `rpy2` fails to compile. However, Dagster Cloud's build process may fail before deployment if compilation errors occur.

### Environment Variables Not Working (CLI)

**Issue**: Variables set via CLI don't appear in UI

**Solutions**:
1. Verify location name matches exactly
2. Check variables are set at location level (not deployment level)
3. Redeploy after setting variables:
   ```bash
   dagster-cloud serverless deploy-python-executable \
     --deployment prod \
     --location-name sbir-etl-production \
     --module-name src.definitions
   ```

### Module Not Found (CLI)

**Issue**: `python_module: src.definitions` not found

**Solutions**:
1. Verify `src/definitions.py` exists
2. Check `defs` object is exported correctly
3. Verify Python path includes project root
4. Check `pyproject.toml` has correct `[tool.dg.project]` configuration

### ConnectionResetError or RequestTimeout (CLI)

**Symptoms**:
- `RequestTimeout: Your socket connection to the server was not read from or written to within the timeout period`
- `ConnectionResetError: Connection reset by peer`
- Upload fails with HTTP 400 or connection aborted errors

**Cause**: The PEX bundle is too large (500+ MB), causing network timeouts during upload to S3. This happens when unnecessary files (data/, reports/, docs/, tests/, etc.) are included in the bundle.

**Solutions**:

**Option 1: Verify MANIFEST.in is working** (already created)

1.  **Check `MANIFEST.in` exists** in project root (should already be there)

2.  **Verify `pyproject.toml` limits packages**:
    ```toml
    [tool.hatch.build.targets.wheel]
    packages = ["src"]
    ```

3.  **Note**: Hatchling may not fully respect `MANIFEST.in` for PEX builds. The PEX builder might include more files than expected.

4.  **Retry deployment** - sometimes network issues are transient:
    ```bash
    dagster-cloud serverless deploy-python-executable \
      --deployment prod \
      --location-name sbir-etl-production \
      --module-name src.definitions
    ```

**Option 2: Use Docker deployment instead** (Recommended for large codebases)

If PEX uploads continue to timeout, use Docker deployment which is more reliable for large codebases:

```bash
# Build Docker image locally (or use CI/CD)
docker build -t sbir-etl:latest --platform=linux/amd64 .

# Deploy using Docker instead of PEX
dagster-cloud serverless deploy \
  --deployment prod \
  --location-name sbir-etl-production \
  --package-name sbir-etl
```

**Benefits of Docker deployment**:
- More reliable for large codebases
- Better control over what's included (via `.dockerignore`)
- No upload timeout issues
- Can use multi-stage builds to reduce image size

**Note**: Docker deployment requires Docker to be running and may take longer to build, but avoids upload timeout issues.

## 11. Monitoring and Observability

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

## 12. Cost Management

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

## 13. Rollback to Docker Compose

If you need to rollback to Docker Compose:

1. Stop using Dagster Cloud (disable code location or pause schedules)
2. Start Docker Compose services:
   ```bash
   make docker-up-dev
   ```
3. Access Dagster UI at `http://localhost:3000`
4. All jobs, schedules, and sensors will work identically

**Note**: No code changes required - same `src/definitions.py` works for both.

## 14. Support and Resources

- **Dagster Cloud Docs**: https://docs.dagster.io/dagster-cloud
- **Dagster Community**: https://dagster.io/community
- **Status Page**: https://status.dagster.io
- **Support**: Available via Dagster Cloud UI

## 15. Deployment Checklist

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

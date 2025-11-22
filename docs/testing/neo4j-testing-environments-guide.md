# Neo4j Testing Environments Guide

This guide explains how to set up and use different Neo4j environments for testing the SBIR ETL pipeline, including Docker (local/CI) and Neo4j Aura (cloud). It covers their comparison, setup, and when to use each.

## Table of Contents

1.  [Overview](#1-overview)
2.  [Quick Comparison](#2-quick-comparison)
3.  [Overlap Analysis](#3-overlap-analysis)
4.  [Docker Test Setup](#4-docker-test-setup)
    *   [Docker Compose Profiles](#docker-compose-profiles)
    *   [GitHub Actions CI](#github-actions-ci)
5.  [Neo4j Aura Free Test Setup](#5-neo4j-aura-free-test-setup)
    *   [Aura Free Limitations](#aura-free-limitations)
    *   [Quick Start](#quick-start)
    *   [Configuration](#configuration)
    *   [Working Within Node Limits](#working-within-node-limits)
    *   [Monitoring and Validation](#monitoring-and-validation)
    *   [Best Practices](#best-practices)
    *   [CI Setup with Aura Free](#ci-setup-with-aura-free)
6.  [Recommended Testing Strategy](#6-recommended-testing-strategy)
    *   [When to Use What](#when-to-use-what)
7.  [Troubleshooting](#7-troubleshooting)
    *   [Common Issues (General)](#common-issues-general)
    *   [Aura Free Specific Issues](#aura-free-specific-issues)
    *   [Docker Specific Issues](#docker-specific-issues)
8.  [Additional Resources](#8-additional-resources)

---

## 1. Overview

This project supports both **Docker** (local/CI) and **Neo4j Aura** (cloud) for testing. CI now uses **Neo4j Aura Free by default** (with automatic cleanup), with Docker available as a manual fallback option.

## 2. Quick Comparison

| Feature | Docker (Local/CI) | Neo4j Aura Free | Paid Aura Professional |
|---------|------------------|-----------------|----------------------|
| **Setup Time** | 2-5 min (first run) | 2 min (one-time) | 2 min (one-time) |
| **Cost** | Free | Free | ~$65/month |
| **Node Limit** | Unlimited | 100,000 | Unlimited |
| **Dataset Size** | Full (300K+ awards) | Sample (5K awards) | Full (300K+ awards) |
| **Performance** | Fast (local resources) | Moderate (shared) | Fast (dedicated) |
| **Network Required** | No (runs locally) | Yes (cloud) | Yes (cloud) |
| **Persistence** | Optional (volumes) | Automatic backups | Automatic backups |
| **Best For** | Development, nightly tests | Quick CI checks, dev | Nightly/weekly comprehensive |

## 3. Overlap Analysis

### ✅ Both Can Be Used For:

1.  **Integration Tests**
    *   Testing Neo4j connection and queries
    *   Validating graph schema (constraints, indexes)
    *   Testing ETL pipeline with sample data
    *   CI/CD automated testing

2.  **Development**
    *   Local feature development
    *   Testing code changes before commit
    *   Debugging pipeline issues

3.  **Fast Tests (marked with `@pytest.mark.fast`)**
    *   Unit tests with mocked Neo4j
    *   Small integration tests (< 1000 records)
    *   Quick smoke tests

### ❌ Key Differences:

| Use Case | Docker | Aura Free | Why? |
|----------|--------|-----------|------|
| **Full dataset testing** | ✅ Yes | ❌ No | Aura Free 100K node limit |
| **Performance benchmarks** | ✅ Yes | ❌ No | Aura Free has shared resources |
| **Offline development** | ✅ Yes | ❌ No | Aura requires internet |
| **No Docker setup** | ❌ No | ✅ Yes | Aura is cloud-hosted |
| **Nightly tests** | ✅ Yes | ⚠️ Maybe | Depends on data volume |

## 4. Docker Test Setup

### Docker Compose Profiles

Your project has **two Docker profiles**:

#### 1. `dev` Profile (Development)

```bash
docker compose --profile dev up
```

**Services:**
- `neo4j`: Local Neo4j instance (no limits)
- `dagster-webserver`: Dagster UI for development
- `dagster-daemon`: Background scheduler
- `etl-runner`: Interactive runner for pipeline

**Neo4j Config:**
- Ports: `7687` (Bolt), `7474` (HTTP)
- Auth: `NEO4J_USER=neo4j`, `NEO4J_PASSWORD` from `.env`
- Volumes: Persistent (`neo4j_data`, `neo4j_logs`)
- Memory: 1GB heap, 256MB pagecache
- Plugins: APOC

**Best For:**
- Local development with full dataset
- Running Dagster UI for debugging
- Long-running development sessions

#### 2. `ci` Profile (CI/CD Testing)

```bash
docker compose --profile ci up
```

**Services:**
- `neo4j`: Test database (ephemeral)
- `app`: Test runner container
- Runs `pytest -m fast` automatically

**Neo4j Config:**
- Same as dev, but ephemeral
- Destroyed after test run
- Fresh instance each time

**Best For:**
- CI/CD pipeline testing
- Automated test runs
- Clean-room testing

### GitHub Actions CI

**Current CI Flow (.github/workflows/ci.yml):**

```yaml
services:
  neo4j:
    image: neo4j:5
    env:
      NEO4J_AUTH: none  # No password for CI
      NEO4J_ACCEPT_LICENSE_AGREEMENT: "yes"
```

**Steps:**
1. Spin up Neo4j service container
2. Wait for Neo4j to be ready
3. Install Python dependencies via uv (`uv sync`)
4. Run `pytest -m fast` (unit + fast integration tests)
5. Generate coverage report

**Tests Run in CI:**
- Unit tests (mocked, no real Neo4j needed)
- Fast integration tests (real Neo4j, small datasets)
- Not run: E2E tests, full pipeline tests

## 5. Neo4j Aura Free Test Setup

Neo4j Aura Free provides a small, cloud-hosted Neo4j instance perfect for testing and development.

### Aura Free Limitations

#### Hard Limits
- **Nodes:** 100,000 maximum
- **Properties:** 200,000 maximum
- **Relationships:** 200,000 maximum
- **Storage:** Limited by above counts
- **Compute:** Shared resources (may be slower than dedicated instances)

#### What This Means for SBIR ETL
- Full SBIR dataset (300K+ awards) **cannot** be loaded
- Must use **sample/subset** of data for testing
- Recommended: 3,000-5,000 awards maximum
- Monitor node count throughout pipeline execution

### Quick Start

#### Step 1: Create Your Aura Free Instance

1. Go to [Neo4j Aura Free](https://neo4j.com/product/auradb/)
2. Sign up for a free account
3. Click **Create Instance** → Select **Free** tier
4. Save your credentials (password is shown only once!)
5. Copy your connection URI (format: `neo4j+s://<instance-id>.databases.neo4j.io`)

#### Step 2: Configure SBIR ETL

1.  **Copy the template:**
    ```bash
    cp .env.test.aura .env.test
    ```

2.  **Edit `.env.test`** with your Aura credentials:
    ```bash
    # Your Aura Free instance details
    SBIR_ETL__NEO4J__URI=neo4j+s://your-instance-id.databases.neo4j.io
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_aura_password_here

    # Use development environment with Aura Free optimizations
    ENVIRONMENT=development
    NEO4J_AURA_FREE=true
    SBIR_ETL__NEO4J__MAX_NODES=95000
    SBIR_ETL__EXTRACTION__SBIR__SAMPLE_LIMIT=1000
    SBIR_ETL__NEO4J__BATCH_SIZE=500
    SBIR_ETL__NEO4J__PARALLEL_THREADS=2
    ```

3.  **Verify connection:**
    ```bash
    # Using the validation script
    python scripts/neo4j/validate_aura_connection.py
    ```

#### Step 3: Run Test Pipeline

```bash
# Set environment and Aura Free optimizations
export ENVIRONMENT=development
export NEO4J_AURA_FREE=true
export SBIR_ETL__NEO4J__MAX_NODES=95000
export SBIR_ETL__EXTRACTION__SBIR__SAMPLE_LIMIT=1000

# Load environment variables
source .env.test

# Run a sample data load (limited to 1000 awards for Aura Free)
python scripts/run_pipeline.py --sample 1000
```

### Configuration

### Environment Variables

The `.env.test.aura` template provides all necessary environment variables:

| Variable | Purpose | Example |
|----------|---------|---------|
| `SBIR_ETL__NEO4J__URI` | Aura connection URI | `neo4j+s://abc123.databases.neo4j.io` |
| `NEO4J_USER` | Username (always `neo4j` for Aura Free) | `neo4j` |
| `NEO4J_PASSWORD` | Password from Aura console | `your_secure_password` |
| `ENVIRONMENT` | Config profile to load | `development` |
| `NEO4J_AURA_FREE` | Enable Aura Free optimizations | `true` |
| `SBIR_ETL__EXTRACTION__SBIR__SAMPLE_LIMIT` | Max awards to process | `1000` (for Aura Free) |
| `SBIR_ETL__NEO4J__MAX_NODES` | Safety limit for nodes | `95000` |
| `SBIR_ETL__NEO4J__BATCH_SIZE` | Batch size for Neo4j operations | `500` |
| `SBIR_ETL__NEO4J__PARALLEL_THREADS` | Parallel threads for Neo4j | `2` |

### Configuration: `config/dev.yaml` with Environment Variables

The `development` environment with Aura Free optimizations provides:

-   **Reduced batch sizes** (500 vs 1000) for gentler load on free tier
-   **Sample limits** on data extraction (configurable via env vars)
-   **Smaller memory footprint** (2GB DuckDB limit vs 4GB)
-   **Relaxed quality thresholds** for test data
-   **Disabled heavy features** (statistical reporting, fiscal analysis)

**Note**: The `test-aura` environment is deprecated. Use `development` with the environment variables above instead.
-   **Increased logging** (DEBUG level) for troubleshooting

### Working Within Node Limits

#### Understanding Node Consumption

For a typical SBIR ETL pipeline run:

| Node Type | Avg Count (5K awards) | Avg Count (Full) |
|-----------|----------------------|------------------|
| Company | ~3,500 | ~45,000 |
| Award | 5,000 | ~300,000 |
| Agency | ~20 | ~25 |
| Program | ~5 | ~10 |
| Person/Researcher | ~1,000 | ~30,000 |
| Patent | ~500 | ~15,000 |
| **TOTAL** | **~10,025** | **~390,035** |

**Conclusion:** A 5,000 award sample fits comfortably within Aura Free limits.

#### Recommended Sample Sizes

| Use Case | Awards | Expected Nodes | Safe? |
|----------|--------|----------------|-------|
| Unit testing | 100 | ~500 | ✅ |
| Integration testing | 1,000 | ~3,000 | ✅ |
| Feature testing | 5,000 | ~10,000 | ✅ |
| Performance testing | 20,000 | ~40,000 | ✅ |
| Full dataset | 300,000 | ~390,000 | ❌ **Exceeds limit** |

### Monitoring and Validation

#### Pre-Load Validation

Before running a pipeline:

```bash
# Check if you have room for the planned load
python scripts/neo4j/validate_aura_capacity.py --planned-nodes 10000
```

#### During Pipeline Execution

The test configuration includes node count monitoring:

```yaml
neo4j:
  max_nodes: 95000  # Hard stop if exceeded
  check_node_count: true  # Validate before bulk ops
  enable_quota_monitoring: true  # Log usage stats
```

#### Post-Load Validation

After a pipeline run:

```bash
# Generate usage report
python scripts/neo4j/generate_usage_report.py
```

### Best Practices

1.  **Start Small, Scale Gradually**: Begin with minimal data and gradually increase.
2.  **Clean Up Between Runs**: Delete all nodes and relationships using Cypher or the cleanup script.
3.  **Use Constraints and Indexes Efficiently**: The test config automatically creates uniqueness constraints and indexes.
4.  **Monitor Instance Health**: Check Aura Console, query performance, and connection timeouts.
5.  **Handle Instance Pausing**: Aura Free instances pause after 3 days of inactivity; resume them from the console.
6.  **Backup Important Test Data**: Export test datasets for later restore.

### CI Setup with Aura Free

**Aura Free is now the default** for CI testing because:
- ✅ No Docker issues in GitHub Actions
- ✅ Cloud-hosted (no container management)
- ✅ Free tier available 24/7
- ✅ Fast connection (no container startup time)
- ✅ Automatic cleanup after tests

#### Quick Setup (5 minutes)

1.  **Create Neo4j Aura Free Instance**:
    *   Go to [Neo4j Aura Free](https://neo4j.com/product/auradb/)
    *   Create a new Aura Free instance (e.g., `sbir-analytics-ci`)
    *   Save credentials (Connection URI, Username `neo4j`, Password)

2.  **Add GitHub Secrets**:
    *   Go to your repository on GitHub → Settings → Secrets and variables → Actions
    *   Add these three secrets:
        *   `NEO4J_AURA_TEST_URI`: Your Aura connection URI
        *   `NEO4J_AURA_TEST_USERNAME`: `neo4j`
        *   `NEO4J_AURA_TEST_PASSWORD`: Password from Aura console

3.  **Verify Setup**:
    *   Trigger a test run (push to a PR or manually run workflow)
    *   Check workflow logs for `☁️ Using Neo4j Aura Free (cloud)` and `✅ Neo4j Aura Free connection successful!`

#### Aura Free Limits for CI

-   **100,000 nodes** maximum
-   **200,000 relationships** maximum
-   **200,000 properties** maximum

The CI workflow automatically:
- Limits sample size to **1,000 awards** (≈2,000 nodes)
- Checks node count **before tests**
- **Cleans up all test data** after tests (always runs)
- Warns if approaching limits

#### Automatic Cleanup

The CI workflow **automatically cleans up** after every test run:

```yaml
- name: Clean up Neo4j test data (Aura Free)
  if: always()  # Runs even if tests fail
  run: MATCH (n) DETACH DELETE n
```

## 6. Recommended Testing Strategy

### Tier 1: Fast Tests (< 5 min, < 5K awards)

**Use:** **Either Docker or Aura Free** (developer choice)

**Docker:**
```bash
# Quick local test
docker compose --profile dev up -d neo4j
export NEO4J_URI=bolt://localhost:7687
pytest -m fast
```

**Aura Free:**
```bash
# Quick cloud test
export ENVIRONMENT=development
export NEO4J_AURA_FREE=true
export SBIR_ETL__NEO4J__MAX_NODES=95000
source .env.test
pytest -m fast
```

**CI:** **Docker** (already configured in GitHub Actions)

### Tier 2: Integration Tests (10-30 min, 5K-50K awards)

**Use:** **Docker** (unlimited nodes, free)

```bash
docker compose --profile dev up -d
python scripts/run_pipeline.py --sample 50000
```

**Alternative:** **Paid Aura** (if team prefers cloud management)

### Tier 3: Nightly/Weekly Tests (1+ hour, full dataset)

**Use:** **Docker** or **Paid Aura**

**Docker:**
```bash
# Nightly cron job
docker compose --profile dev up -d
python scripts/run_pipeline.py  # Full dataset
```

**Paid Aura:**
```bash
# Configure .env.nightly with Aura Pro credentials
export ENVIRONMENT=nightly
python scripts/run_pipeline.py
```

### When to Use What

#### Use Docker When:
- ✅ You need to test with **full dataset** (300K+ awards, >100K nodes)
- ✅ You're doing **performance benchmarking** (need dedicated resources)
- ✅ You want to test **offline** (no internet required)
- ✅ You already have Docker running (dagster, other services)
- ✅ **CI/CD quick checks** (already configured, no secrets)

#### Use Aura Free When:
- ✅ You don't have Docker installed (quick start)
- ✅ You want **cloud backup** of test data (persistence across machines)
- ✅ You're testing a **small feature** with < 5K awards
- ✅ You want to **share a test database** with teammates (cloud URL)
- ✅ You're developing on a **resource-constrained machine** (Docker overhead)

#### Use Paid Aura Pro When:
- ✅ You need **reliable nightly/weekly tests** with full dataset
- ✅ You want **cloud-managed** infrastructure (no Docker maintenance)
- ✅ You need **better performance** than free tier
- ✅ You want **automatic backups** and monitoring

## 7. Troubleshooting

### Common Issues (General)

#### Connection failed:
```bash
# Check URI format (must be neo4j+s:// for Aura)
echo $SBIR_ETL__NEO4J__URI

# Verify password (no trailing spaces)
echo $NEO4J_PASSWORD | cat -A

# Check instance status at console.neo4j.io
```

#### Node limit exceeded:
```bash
# Reduce sample size
export SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=1000

# Or clean up existing data
MATCH (n) DETACH DELETE n;
```

#### Instance paused:
```bash
# Visit console.neo4j.io
# Click "Resume" on your instance
# Wait 30-60 seconds, then retry
```

### Aura Free Specific Issues

#### Problem: "Neo4j Aura credentials not configured"

**Symptom:**
```
⚠️  Warning: Neo4j Aura credentials not configured in GitHub secrets
```

**Solution:**
1. Verify secrets exist: Settings → Secrets and variables → Actions
2. Check exact names: `NEO4J_AURA_TEST_URI`, `NEO4J_AURA_TEST_USERNAME`, `NEO4J_AURA_TEST_PASSWORD`
3. Re-add secrets if misspelled

#### Problem: "Neo4j Aura Free connection failed"

**Symptom:**
```
❌ Neo4j Aura Free connection failed: ServiceUnavailable
```

**Possible Causes:**

1.  **Instance paused** (inactive for 3 days):
    *   Go to https://console.neo4j.io/
    *   Click **Resume** on your instance
    *   Wait 30-60 seconds
    *   Re-run workflow

2.  **Wrong URI format**:
    *   Should be: `neo4j+s://...` (not `bolt://` or `neo4j://`)
    *   Include the `+s` for TLS

3.  **Wrong password**:
    *   Password is case-sensitive
    *   Re-check in Aura console (can reset if lost)

4.  **Instance deleted** (inactive for 6 months):
    *   Create a new Aura Free instance
    *   Update GitHub secrets with new credentials

#### Problem: "Node count approaching limit"

**Symptom:**
```
⚠️  WARNING: Node count (98,000) approaching Aura Free limit (100,000)
```

**Solution:**

Manual cleanup via cypher-shell or Neo4j Browser:
```cypher
// Delete all nodes
MATCH (n) DETACH DELETE n;

// Verify cleanup
MATCH (n) RETURN count(n);  // Should return 0
```

Or run cleanup script:
```bash
python scripts/neo4j/cleanup_database.py --confirm
```

**Prevention:**
- Cleanup should run automatically after CI
- If it's not running, check workflow logs for errors

#### Problem: "Tests timing out"

**Symptom:**
```
Tests taking >10 minutes (normally < 2 min)
```

**Possible Causes:**

1.  **Aura Free shared resources** (slower than Docker):
    *   Expected: Aura Free may be 2-3x slower than local Docker
    *   Solution: Use Docker fallback for performance-sensitive tests

2.  **Too much test data**:
    *   Check: `SBIR_ETL__EXTRACTION__SAMPLE_LIMIT` should be ≤1000
    *   Reduce sample size in test-aura.yaml

3.  **Network latency**:
    *   Aura requires internet connectivity
    *   Slower if GitHub runners are far from Aura region

#### Problem: Workflow fails with "secrets not available"

**Symptom:**
```
secrets.NEO4J_AURA_TEST_URI not found
```

**Cause:** Forks don't have access to repository secrets (security feature)

**Solution for forks:**
1. Fork owner must add their own Aura Free credentials
2. Or use Docker fallback (manual workflow dispatch)

### Docker Specific Issues

#### Problem: Docker Compose not starting

**Symptom:** Services fail to start, network errors.

**Solution:**
1. Ensure Docker Desktop is running.
2. Check for port conflicts (e.g., Neo4j ports 7474, 7687).
3. Review Docker Compose logs for specific errors.

#### Problem: Tests are slow in Docker

**Symptom:** Tests take longer than expected.

**Solution:**
1. Allocate more resources (CPU, RAM) to Docker Desktop.
2. Ensure Docker volumes are performing well (e.g., not on slow network drives).
3. Use `pytest-xdist` for parallel test execution.

## 8. Additional Resources

-   **Neo4j Aura Documentation:** https://neo4j.com/docs/aura/
-   **Neo4j Aura Console:** https://console.neo4j.io/
-   **Neo4j Cypher Manual:** https://neo4j.com/docs/cypher-manual/current/introduction/
-   **SBIR ETL Issues:** https://github.com/your-org/sbir-analytics/issues
-   **Configuration schema:** [src/config/schemas/pipeline.py](../../src/config/schemas/pipeline.py)
-   **Environment examples:** [.env.example](../../.env.example), [.env.test.aura](../../.env.test.aura)

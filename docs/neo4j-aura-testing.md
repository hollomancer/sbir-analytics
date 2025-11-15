# Neo4j Aura Free Testing Setup

This guide explains how to use Neo4j Aura Free for testing the SBIR ETL pipeline. Neo4j Aura Free provides a small, cloud-hosted Neo4j instance perfect for testing and development.

## Table of Contents

- [Overview](#overview)
- [Aura Free Limitations](#aura-free-limitations)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Working Within Node Limits](#working-within-node-limits)
- [Monitoring and Validation](#monitoring-and-validation)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Neo4j Aura Free offers:
- **100,000 nodes** maximum
- **200,000 properties** maximum
- **200,000 relationships** maximum
- Cloud-hosted (no local installation required)
- Automatic backups
- Secure connections (TLS/SSL)
- Free forever (with usage limits)

**Important:** Free instances pause after **3 days of inactivity** and are deleted after **6 months** of inactivity.

### Testing Strategy

**Aura Free is designed for FAST, LIGHTWEIGHT tests only.**

| Test Type | Environment | Recommended Instance |
|-----------|-------------|---------------------|
| **Fast unit/integration tests** | Developer local, CI quick checks | ✅ **Neo4j Aura Free** |
| **Nightly integration tests** | CI/CD nightly runs | ⚡ **Paid Neo4j Aura or Local** |
| **Weekly comprehensive tests** | CI/CD weekly runs | ⚡ **Paid Neo4j Aura Professional** |
| **Performance benchmarks** | Staging/Performance | ⚡ **Paid Neo4j Aura or Enterprise** |

**Why this strategy?**
- Aura Free's 100K node limit = ~5,000 SBIR awards max
- Full dataset (300K+ awards) requires paid tier
- Fast tests (< 5 min) stay within free tier capabilities
- Comprehensive tests need more resources and data

**This documentation focuses on fast test setup using Aura Free.**

## Aura Free Limitations

### Hard Limits
- **Nodes:** 100,000 maximum
- **Properties:** 200,000 maximum
- **Relationships:** 200,000 maximum
- **Storage:** Limited by above counts
- **Compute:** Shared resources (may be slower than dedicated instances)

### What This Means for SBIR ETL
- Full SBIR dataset (300K+ awards) **cannot** be loaded
- Must use **sample/subset** of data for testing
- Recommended: 3,000-5,000 awards maximum
- Monitor node count throughout pipeline execution

## Quick Start

### Step 1: Create Your Aura Free Instance

1. Go to [Neo4j Aura Free](https://neo4j.com/cloud/aura-free/)
2. Sign up for a free account
3. Click **Create Instance** → Select **Free** tier
4. Save your credentials (password is shown only once!)
5. Copy your connection URI (format: `neo4j+s://<instance-id>.databases.neo4j.io`)

### Step 2: Configure SBIR ETL

1. **Copy the template:**
   ```bash
   cp .env.test.aura .env.test
   ```

2. **Edit `.env.test`** with your Aura credentials:
   ```bash
   # Your Aura Free instance details
   SBIR_ETL__NEO4J__URI=neo4j+s://your-instance-id.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_aura_password_here

   # Set environment to use test-aura config
   ENVIRONMENT=test-aura
   ```

3. **Verify connection:**
   ```bash
   # Using the validation script (created below)
   python scripts/neo4j/validate_aura_connection.py
   ```

### Step 3: Run Test Pipeline

```bash
# Set environment
export ENVIRONMENT=test-aura

# Load environment variables
source .env.test

# Run a sample data load (limited to 5000 awards)
python scripts/run_pipeline.py --sample 5000
```

## Configuration

### Environment Variables

The `.env.test.aura` template provides all necessary environment variables:

| Variable | Purpose | Example |
|----------|---------|---------|
| `SBIR_ETL__NEO4J__URI` | Aura connection URI | `neo4j+s://abc123.databases.neo4j.io` |
| `NEO4J_USER` | Username (always `neo4j` for Aura Free) | `neo4j` |
| `NEO4J_PASSWORD` | Password from Aura console | `your_secure_password` |
| `ENVIRONMENT` | Config profile to load | `test-aura` |
| `SBIR_ETL__EXTRACTION__SAMPLE_LIMIT` | Max awards to process | `5000` |
| `SBIR_ETL__NEO4J__MAX_NODES` | Safety limit for nodes | `95000` |

### Configuration File: `config/test-aura.yaml`

The `test-aura.yaml` configuration file provides:

- **Reduced batch sizes** (500 vs 1000) for gentler load on free tier
- **Sample limits** on data extraction (5000 awards, 2000 patents)
- **Smaller memory footprint** (2GB DuckDB limit vs 4GB)
- **Relaxed quality thresholds** for test data
- **Disabled heavy features** (statistical reporting, fiscal analysis)
- **Increased logging** (DEBUG level) for troubleshooting

## Working Within Node Limits

### Understanding Node Consumption

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

### Recommended Sample Sizes

| Use Case | Awards | Expected Nodes | Safe? |
|----------|--------|----------------|-------|
| Unit testing | 100 | ~500 | ✅ |
| Integration testing | 1,000 | ~3,000 | ✅ |
| Feature testing | 5,000 | ~10,000 | ✅ |
| Performance testing | 20,000 | ~40,000 | ✅ |
| Full dataset | 300,000 | ~390,000 | ❌ **Exceeds limit** |

### Monitoring Node Count

Use the validation script to check current usage:

```bash
python scripts/neo4j/check_node_count.py
```

Example output:
```
Neo4j Aura Free - Resource Usage
================================
Nodes:        12,543 / 100,000 (12.5%)
Relationships: 28,432 / 200,000 (14.2%)
Properties:    45,231 / 200,000 (22.6%)

Status: ✅ Within limits
```

## Monitoring and Validation

### Pre-Load Validation

Before running a pipeline:

```bash
# Check if you have room for the planned load
python scripts/neo4j/validate_aura_capacity.py --planned-nodes 10000
```

### During Pipeline Execution

The test configuration includes node count monitoring:

```yaml
neo4j:
  max_nodes: 95000  # Hard stop if exceeded
  check_node_count: true  # Validate before bulk ops
  enable_quota_monitoring: true  # Log usage stats
```

### Post-Load Validation

After a pipeline run:

```bash
# Generate usage report
python scripts/neo4j/generate_usage_report.py
```

## Best Practices

### 1. Start Small, Scale Gradually

```bash
# Start with minimal data
SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=100 python scripts/run_pipeline.py

# Gradually increase
SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=1000 python scripts/run_pipeline.py
SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=5000 python scripts/run_pipeline.py
```

### 2. Clean Up Between Runs

```cypher
// Delete all nodes and relationships
MATCH (n) DETACH DELETE n;

// Verify cleanup
MATCH (n) RETURN count(n) as node_count;
```

Or use the cleanup script:
```bash
python scripts/neo4j/cleanup_database.py --confirm
```

### 3. Use Constraints and Indexes Efficiently

The test config automatically creates:
- Uniqueness constraints on IDs (prevents duplicates)
- Indexes on frequently queried properties

```yaml
neo4j:
  create_constraints: true  # Essential
  create_indexes: true      # Essential
```

### 4. Monitor Instance Health

- **Aura Console:** Check instance status at https://console.neo4j.io/
- **Query Performance:** Slow queries indicate resource constraints
- **Connection Timeouts:** May indicate instance paused or overloaded

### 5. Handle Instance Pausing

Aura Free instances pause after 3 days of inactivity:

1. Visit Aura console
2. Click **Resume** on your instance
3. Wait 30-60 seconds for startup
4. Reconnect from SBIR ETL

### 6. Backup Important Test Data

```bash
# Export test dataset for later restore
cypher-shell -u neo4j -p yourpassword -a neo4j+s://your-instance.databases.neo4j.io \
  "CALL apoc.export.cypher.all('backup.cypher', {})"
```

**Note:** APOC may not be available on Aura Free. Use `neo4j-admin dump` alternative or manual export.

## Troubleshooting

### Connection Errors

**Error:** `ServiceUnavailable: Cannot connect to Neo4j Aura`

**Solutions:**
1. Verify URI format: `neo4j+s://` (not `bolt://` or `neo4j://`)
2. Check password (case-sensitive, no extra spaces)
3. Ensure instance is not paused (check Aura console)
4. Verify network/firewall allows outbound HTTPS

### Node Limit Exceeded

**Error:** `Neo4jError: Node quota exceeded`

**Solutions:**
1. Reduce `SBIR_ETL__EXTRACTION__SAMPLE_LIMIT`
2. Clean up existing data: `MATCH (n) DETACH DELETE n`
3. Check node count: `MATCH (n) RETURN count(n)`
4. Consider upgrading to paid tier for larger datasets

### Slow Performance

**Symptoms:** Queries take minutes instead of seconds

**Solutions:**
1. Aura Free uses shared resources - expect slower performance
2. Reduce batch sizes in `test-aura.yaml`
3. Add indexes on frequently queried properties
4. Simplify complex queries (reduce Cartesian products)
5. Consider local Neo4j for performance testing

### Instance Paused

**Error:** `Unable to connect to database`

**Solutions:**
1. Log into https://console.neo4j.io/
2. Click **Resume** on your instance
3. Wait 30-60 seconds
4. Retry connection

### Authentication Failed

**Error:** `AuthError: Invalid username or password`

**Solutions:**
1. Username is always `neo4j` for Aura Free
2. Password is case-sensitive
3. Reset password in Aura console if forgotten
4. Check for trailing spaces in `.env.test`

## Migrating from Local to Aura

If you're currently using local Neo4j via Docker:

1. **Export your local data:**
   ```bash
   docker exec neo4j neo4j-admin dump --to=/backups/local-backup.dump
   ```

2. **Configure for Aura:**
   ```bash
   export ENVIRONMENT=test-aura
   source .env.test
   ```

3. **Import to Aura** (if data is small enough):
   ```bash
   # Use Cypher export/import or manual data loading
   # Note: Aura Free doesn't support direct dump restore
   ```

4. **Alternative:** Use sampling:
   ```bash
   # Load a representative sample instead of full dataset
   python scripts/sample_and_load.py --sample-size 5000 --seed 42
   ```

## Additional Resources

- **Neo4j Aura Documentation:** https://neo4j.com/docs/aura/
- **Neo4j Aura Console:** https://console.neo4j.io/
- **Neo4j Cypher Manual:** https://neo4j.com/docs/cypher-manual/current/
- **SBIR ETL Issues:** https://github.com/your-org/sbir-etl/issues

## Summary

### Neo4j Aura Free is Excellent For (Fast Tests Only):
- ✅ **Quick unit/integration tests** (< 5 min, < 5K awards)
- ✅ **Feature development and validation** with sample data
- ✅ **CI/CD quick checks** (PR validation, fast feedback)
- ✅ **Learning and experimentation**
- ✅ **Local developer testing** without Docker overhead

### Not Suitable For:
- ❌ **Nightly integration tests** (use paid Aura or local Neo4j)
- ❌ **Weekly comprehensive tests** (use paid Aura Professional)
- ❌ **Full SBIR dataset** (300K+ awards - exceeds 100K node limit)
- ❌ **Production deployments**
- ❌ **Performance benchmarking** (shared resources, inconsistent performance)
- ❌ **High-throughput workloads**

### Recommended Instances by Test Tier

| Test Tier | Dataset Size | Duration | Recommended Instance | Cost |
|-----------|--------------|----------|---------------------|------|
| **Fast** | 100-5K awards | < 5 min | Neo4j Aura Free | Free |
| **Nightly** | 10K-50K awards | 10-30 min | Local Docker / Aura Pro | Free / ~$65/mo |
| **Weekly** | Full (300K+ awards) | 1+ hour | Aura Professional | ~$65/mo |
| **Performance** | Full + load testing | Variable | Aura Enterprise / Self-hosted | Custom |

**This guide focuses on setting up the Fast test tier using Aura Free.**

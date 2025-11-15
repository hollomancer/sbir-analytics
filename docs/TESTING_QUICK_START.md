# Testing Quick Start Guide

Quick reference for setting up and running tests with different Neo4j instances.

## Test Tiers

| Tier | Instance | Dataset | Duration | Setup |
|------|----------|---------|----------|-------|
| **Fast** | Aura Free | 100-5K awards | < 5 min | See [Fast Tests](#fast-tests-aura-free) |
| **Nightly** | Local/Paid | 10K-50K awards | 10-30 min | See [Nightly Tests](#nightly-tests) |
| **Weekly** | Paid Aura Pro | Full (300K+) | 1+ hr | See [Weekly Tests](#weekly-tests) |

---

## Fast Tests (Aura Free)

**Purpose:** Quick validation during development, PR checks, fast CI feedback.

### 1. One-Time Setup

```bash
# Get Neo4j Aura Free instance
# Visit: https://neo4j.com/cloud/aura-free/
# Save your URI and password!

# Copy and configure
cp .env.test.aura .env.test

# Edit .env.test with your Aura details:
# SBIR_ETL__NEO4J__URI=neo4j+s://your-instance.databases.neo4j.io
# NEO4J_PASSWORD=your_password_here
```

### 2. Run Fast Tests

```bash
# Set environment
export ENVIRONMENT=test-aura
source .env.test

# Check connection
python scripts/neo4j/check_aura_usage.py

# Run pipeline with sample data
python scripts/run_pipeline.py --sample 1000

# Verify results
python scripts/neo4j/check_aura_usage.py --detailed
```

### 3. Clean Up Between Runs

```bash
# Connect via cypher-shell or Neo4j Browser
MATCH (n) DETACH DELETE n;

# Or use cleanup script (if available)
python scripts/neo4j/cleanup_database.py --confirm
```

**Limits:** Max ~5,000 awards, ~10K nodes, < 5 minute runtime.

---

## Nightly Tests

**Purpose:** Broader integration testing with more realistic data volumes.

### Setup

```bash
# Option 1: Local Docker Neo4j
docker-compose up -d neo4j

# Option 2: Paid Aura instance
# Configure with larger limits in .env.nightly
```

### Run

```bash
export ENVIRONMENT=nightly
python scripts/run_pipeline.py --sample 50000
```

**Limits:** 10K-50K awards, 10-30 minute runtime.

---

## Weekly Tests

**Purpose:** Full dataset validation, comprehensive regression testing.

### Setup

```bash
# Use paid Aura Professional or Enterprise
# Configure in .env.weekly
export ENVIRONMENT=weekly
```

### Run

```bash
# Full pipeline with no sampling
python scripts/run_pipeline.py
```

**Limits:** Full dataset (300K+ awards), 1+ hour runtime.

---

## Useful Commands

### Check Neo4j Usage

```bash
# Current usage
python scripts/neo4j/check_aura_usage.py

# With planned additions
python scripts/neo4j/check_aura_usage.py --planned-nodes 5000

# Detailed breakdown
python scripts/neo4j/check_aura_usage.py --detailed
```

### Database Operations

```bash
# Count nodes
MATCH (n) RETURN count(n);

# Count by label
MATCH (n:Company) RETURN count(n);

# Delete all data
MATCH (n) DETACH DELETE n;

# Check constraints
CALL db.constraints();

# Check indexes
CALL db.indexes();
```

### Common Issues

**Connection failed:**
```bash
# Check URI format (must be neo4j+s:// for Aura)
echo $SBIR_ETL__NEO4J__URI

# Verify password (no trailing spaces)
echo $NEO4J_PASSWORD | cat -A

# Check instance status at console.neo4j.io
```

**Node limit exceeded:**
```bash
# Reduce sample size
export SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=1000

# Or clean up existing data
MATCH (n) DETACH DELETE n;
```

**Instance paused:**
```bash
# Visit console.neo4j.io
# Click "Resume" on your instance
# Wait 30-60 seconds, then retry
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `.env.test.aura` | Template for Aura Free config |
| `config/test-aura.yaml` | Fast test settings (sample limits, small batches) |
| `config/dev.yaml` | Local development (Docker Neo4j) |
| `scripts/neo4j/check_aura_usage.py` | Usage monitoring script |

---

## Environment Variables Quick Reference

```bash
# Neo4j Connection (REQUIRED)
export SBIR_ETL__NEO4J__URI="neo4j+s://your-instance.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Environment Profile (loads corresponding .yaml)
export ENVIRONMENT="test-aura"  # or dev, nightly, weekly

# Data Sampling (optional, override config)
export SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=5000
export SBIR_ETL__EXTRACTION__USPTO__SAMPLE_LIMIT=2000

# Neo4j Batch Sizes (optional)
export SBIR_ETL__NEO4J__BATCH_SIZE=500
export SBIR_ETL__NEO4J__PARALLEL_THREADS=2

# Safety Limits (optional)
export SBIR_ETL__NEO4J__MAX_NODES=95000
export SBIR_ETL__NEO4J__CHECK_NODE_COUNT=true
```

---

## For More Details

- **Full Aura Free guide:** [docs/neo4j-aura-testing.md](./neo4j-aura-testing.md)
- **Configuration schema:** [src/config/schemas.py](../src/config/schemas.py)
- **Environment examples:** [.env.example](./.env.example), [.env.test.aura](./.env.test.aura)

---

## Quick Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ServiceUnavailable` error | Wrong URI or instance paused | Check console.neo4j.io, resume instance |
| `AuthError` | Wrong password | Verify password in .env.test |
| `Node quota exceeded` | Too much data | Reduce SAMPLE_LIMIT, clean database |
| Slow performance | Aura Free shared resources | Normal for free tier, use local for speed |
| Can't connect | URI format wrong | Must be `neo4j+s://` for Aura (not `bolt://`) |

**Need help?** See full troubleshooting guide in [docs/neo4j-aura-testing.md](./neo4j-aura-testing.md#troubleshooting)

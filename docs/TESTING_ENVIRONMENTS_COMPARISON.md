# Testing Environments Comparison

This document explains the overlap between Neo4j Aura Free and Docker-based testing, and when to use each.

> **📣 UPDATE (January 2025):** CI now uses **Neo4j Aura Free by default** (with automatic cleanup).
> Docker is available as a manual fallback option. See [CI_AURA_SETUP.md](./CI_AURA_SETUP.md) for setup.

## Quick Comparison

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

---

## Where They Overlap

### ✅ Both Can Be Used For:

1. **Integration Tests**
   - Testing Neo4j connection and queries
   - Validating graph schema (constraints, indexes)
   - Testing ETL pipeline with sample data
   - CI/CD automated testing

2. **Development**
   - Local feature development
   - Testing code changes before commit
   - Debugging pipeline issues

3. **Fast Tests (marked with `@pytest.mark.fast`)**
   - Unit tests with mocked Neo4j
   - Small integration tests (< 1000 records)
   - Quick smoke tests

### ❌ Key Differences:

| Use Case | Docker | Aura Free | Why? |
|----------|--------|-----------|------|
| **Full dataset testing** | ✅ Yes | ❌ No | Aura Free 100K node limit |
| **Performance benchmarks** | ✅ Yes | ❌ No | Aura Free has shared resources |
| **Offline development** | ✅ Yes | ❌ No | Aura requires internet |
| **No Docker setup** | ❌ No | ✅ Yes | Aura is cloud-hosted |
| **Nightly tests** | ✅ Yes | ⚠️ Maybe | Depends on data volume |

---

## Current Docker Test Setup

### Docker Compose Profiles

Your project has **two Docker profiles**:

#### 1. **`dev` Profile** (Development)
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

#### 2. **`ci` Profile** (CI/CD Testing)
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
3. Install Python dependencies via Poetry
4. Run `pytest -m fast` (unit + fast integration tests)
5. Generate coverage report

**Tests Run in CI:**
- Unit tests (mocked, no real Neo4j needed)
- Fast integration tests (real Neo4j, small datasets)
- Not run: E2E tests, full pipeline tests

---

## Overlap Analysis

### Scenario 1: Developer Wants to Test Locally

| Task | Docker | Aura Free | Recommendation |
|------|--------|-----------|----------------|
| Test feature with 100 records | ✅ Good | ✅ Good | **Either** - use what's easier |
| Test feature with 50K records | ✅ Good | ❌ Too big | **Docker** |
| Don't have Docker installed | ❌ No | ✅ Good | **Aura Free** |
| Already running Docker services | ✅ Good | ⚠️ Extra | **Docker** (already running) |
| Test offline (plane, poor internet) | ✅ Good | ❌ No | **Docker** |

**Verdict:** Docker is more flexible, but Aura Free is easier if you don't have Docker or want cloud backup.

---

### Scenario 2: CI/CD Quick Checks (PR Validation)

| Requirement | Docker (GitHub Actions) | Aura Free | Winner |
|-------------|------------------------|-----------|--------|
| No setup per run | ✅ Service container | ⚠️ Need credentials | **Docker** |
| Speed | ✅ Fast (local runner) | ⚠️ Network latency | **Docker** |
| Cost | ✅ Free (included) | ✅ Free | **Tie** |
| No secrets needed | ✅ `NEO4J_AUTH=none` | ❌ Need password | **Docker** |
| Persistence across runs | ❌ Ephemeral | ✅ Cloud backup | **Aura Free** |

**Verdict:** **Docker is better for CI quick checks** (already configured, no secrets needed, faster).

**Current CI already uses Docker services** - no need to change.

---

### Scenario 3: Nightly Integration Tests

| Requirement | Docker | Aura Free | Paid Aura |
|-------------|--------|-----------|-----------|
| Full dataset (300K awards) | ✅ Yes | ❌ No (100K limit) | ✅ Yes |
| Cost | ✅ Free | ✅ Free (but can't fit) | ~$65/mo |
| Setup complexity | ⚠️ Manage Docker | ✅ Cloud managed | ✅ Cloud managed |
| Performance | ✅ Dedicated | ⚠️ Shared | ✅ Dedicated |

**Verdict:** **Docker** (free, unlimited) or **Paid Aura** (managed, reliable). Aura Free can't handle full dataset.

---

### Scenario 4: Weekly Comprehensive Tests

| Requirement | Docker | Aura Free | Paid Aura |
|-------------|--------|-----------|-----------|
| Full dataset | ✅ Yes | ❌ No | ✅ Yes |
| Performance testing | ✅ Yes | ❌ No (shared resources) | ✅ Yes |
| Reliability | ⚠️ Depends on runner | ⚠️ May pause | ✅ Always on |
| Cost | ✅ Free | ✅ Free (but limited) | ~$65/mo |

**Verdict:** **Paid Aura** (best reliability) or **Docker** (free but requires runner maintenance).

---

## Recommended Testing Strategy

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
export ENVIRONMENT=test-aura
source .env.test
pytest -m fast
```

**CI:** **Docker** (already configured in GitHub Actions)

---

### Tier 2: Integration Tests (10-30 min, 5K-50K awards)

**Use:** **Docker** (unlimited nodes, free)

```bash
docker compose --profile dev up -d
python scripts/run_pipeline.py --sample 50000
```

**Alternative:** **Paid Aura** (if team prefers cloud management)

---

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

---

## When to Use What

### Use Docker When:
- ✅ You need to test with **full dataset** (300K+ awards, >100K nodes)
- ✅ You're doing **performance benchmarking** (need dedicated resources)
- ✅ You want to test **offline** (no internet required)
- ✅ You already have Docker running (dagster, other services)
- ✅ **CI/CD quick checks** (already configured, no secrets)

### Use Aura Free When:
- ✅ You don't have Docker installed (quick start)
- ✅ You want **cloud backup** of test data (persistence across machines)
- ✅ You're testing a **small feature** with < 5K awards
- ✅ You want to **share a test database** with teammates (cloud URL)
- ✅ You're developing on a **resource-constrained machine** (Docker overhead)

### Use Paid Aura Pro When:
- ✅ You need **reliable nightly/weekly tests** with full dataset
- ✅ You want **cloud-managed** infrastructure (no Docker maintenance)
- ✅ You need **better performance** than free tier
- ✅ You want **automatic backups** and monitoring

---

## Migration Path: Docker → Aura Free

If you're currently using Docker and want to try Aura Free:

### Step 1: Export Sample Data from Docker

```bash
# Start Docker Neo4j
docker compose --profile dev up -d neo4j

# Export first 5000 awards to Cypher
docker exec sbir-neo4j cypher-shell -u neo4j -p password \
  "MATCH (a:Award) WITH a LIMIT 5000 RETURN a" > sample_awards.cypher

# Or use APOC export (if available)
docker exec sbir-neo4j cypher-shell -u neo4j -p password \
  "CALL apoc.export.cypher.query('MATCH (n) RETURN n LIMIT 10000', 'sample.cypher', {})"
```

### Step 2: Configure Aura Free

```bash
cp .env.test.aura .env.test
# Edit with your Aura credentials
```

### Step 3: Import to Aura (Small Sample)

```bash
export ENVIRONMENT=test-aura
source .env.test

# Run pipeline with sample
python scripts/run_pipeline.py --sample 5000
```

---

## Configuration File Overlap

| File | Used By | Purpose |
|------|---------|---------|
| `config/dev.yaml` | Docker dev profile | Development settings, local paths |
| `config/docker.yaml` | Docker compose | Container-specific overrides |
| `config/test-aura.yaml` | **Aura Free** | Sample limits, reduced batches |
| `.env.example` | Docker | Template for local Docker config |
| `.env.test.aura` | **Aura Free** | Template for Aura credentials |

**No conflicts!** Each environment loads its own config via `ENVIRONMENT` variable.

---

## Summary: Docker vs Aura Free

### Docker Tests (Current Setup)
- **Profiles:** `dev` (persistent), `ci` (ephemeral)
- **CI:** GitHub Actions service container
- **Limits:** None (unlimited nodes)
- **Best for:** Full dataset, nightly tests, development

### Aura Free (New Setup)
- **Profile:** `test-aura` config
- **CI:** Could be used, but Docker is better (no secrets)
- **Limits:** 100K nodes (≈5K awards max)
- **Best for:** Quick tests, no Docker, cloud backup

### Recommendation

**Keep your current Docker setup for:**
- CI/CD (already configured, works great)
- Nightly/weekly tests (full dataset)
- Local development (most flexible)

**Add Aura Free as an option for:**
- Developers without Docker
- Quick cloud-backed tests
- Sharing test instances with teammates
- Testing on resource-constrained machines

**No replacement needed** - they complement each other!

---

## Example Workflows

### Workflow 1: Quick PR Check (Developer)

**Option A: Docker (if already running)**
```bash
# Already have docker compose up
pytest -m fast  # Uses local Neo4j
```

**Option B: Aura Free (if Docker not running)**
```bash
export ENVIRONMENT=test-aura
source .env.test
pytest -m fast  # Uses Aura Free
```

### Workflow 2: CI/CD PR Validation (GitHub Actions)

**Current (Docker):**
```yaml
services:
  neo4j:
    image: neo4j:5
    # ... config ...
steps:
  - run: poetry run pytest -m fast
```

**No change needed!** Docker is optimal here.

### Workflow 3: Nightly Integration Tests

**Option A: Docker (free, unlimited)**
```bash
# Cron job
docker compose --profile dev up -d
python scripts/run_pipeline.py
```

**Option B: Paid Aura Pro**
```bash
export ENVIRONMENT=nightly
source .env.nightly  # Aura Pro credentials
python scripts/run_pipeline.py
```

---

## Action Items

Based on this analysis:

1. ✅ **Keep Docker for CI** - already configured, works great
2. ✅ **Keep Docker for nightly tests** - free, unlimited
3. ✅ **Add Aura Free as optional developer tool** - for those who prefer it
4. ⚠️ **Consider Paid Aura for weekly tests** - if Docker maintenance becomes burden
5. 📝 **Document both options** - let developers choose

**No breaking changes needed!** Aura Free is an *addition*, not a replacement.

# Neo4j Aura E2E Testing

This document describes how E2E tests use Neo4j Aura free tier for integration testing in CI.

## Overview

The `e2e-aura` job in `.github/workflows/ci.yml` runs end-to-end tests against a Neo4j Aura free instance instead of a local Docker container. This provides:

- **Persistent database** between test runs
- **Cloud environment** matching production
- **No startup time** (database always running)
- **Realistic testing** with actual cloud infrastructure

## Setup

### 1. Create Neo4j Aura Free Instance

1. Go to [Neo4j Aura](https://neo4j.com/cloud/aura/)
2. Sign up for a free account
3. Create a new **AuraDB Free** instance
4. Save the connection URI, username, and password

**Example URI:** `neo4j+s://0ad2b169.databases.neo4j.io`

### 2. Configure Repository Secrets

Add the following secrets to your GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value | Example |
|-------------|-------|---------|
| `NEO4J_AURA_URI` | Connection URI | `neo4j+s://0ad2b169.databases.neo4j.io` |
| `NEO4J_AURA_USER` | Username | `neo4j` |
| `NEO4J_AURA_PASSWORD` | Password | Your Aura password |

### 3. Verify Setup

Once secrets are configured, the `e2e-aura` job will run automatically on pushes to `main` or `develop`.

Check the workflow run to verify:

- ✅ Database cleared before tests
- ✅ E2E tests pass
- ✅ Node/relationship counts within limits

## Aura Free Tier Limits

| Resource | Limit | Test Configuration |
|----------|-------|-------------------|
| Nodes | 200,000 | Uses 1,000 sample (AURA_SAMPLE_LIMIT) |
| Relationships | 400,000 | Proportional to nodes |
| Storage | 1 GB | Well within limit |
| Concurrent connections | 3 | Single test runner |

## Test Workflow

The `e2e-aura` job performs the following steps:

1. **Clear database** - Removes all nodes and relationships
2. **Run E2E tests** - Executes `tests/e2e/` with sample data
3. **Verify data** - Checks node/relationship counts
4. **Cleanup on failure** - Clears database if tests fail

## Database Cleanup

The database is automatically cleared:

- **Before tests** - Ensures clean state
- **After failure** - Prevents state pollution

Manual cleanup (if needed):

```bash
# Using cypher-shell
cypher-shell -a neo4j+s://0ad2b169.databases.neo4j.io \
  -u neo4j -p <password> \
  "MATCH (n) DETACH DELETE n"

# Using Python
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    'neo4j+s://0ad2b169.databases.neo4j.io',
    auth=('neo4j', '<password>')
)
with driver.session() as session:
    session.run('MATCH (n) DETACH DELETE n')
driver.close()
"
```

## Monitoring

### Check Node Count

```cypher
MATCH (n)
RETURN count(n) as nodes
```

### Check Relationship Count

```cypher
MATCH ()-[r]->()
RETURN count(r) as relationships
```

### Check Database Size

```cypher
CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store sizes')
YIELD attributes
RETURN attributes.TotalStoreSize.value as size
```

## Troubleshooting

### Job Skipped

**Symptom:** `e2e-aura` job shows as "skipped"

**Cause:** Repository secrets not configured

**Fix:** Add `NEO4J_AURA_URI`, `NEO4J_AURA_USER`, and `NEO4J_AURA_PASSWORD` secrets

### Connection Timeout

**Symptom:** Tests fail with connection timeout

**Cause:** Aura instance paused or network issue

**Fix:**

1. Check Aura console - instance may be paused
2. Resume instance if needed
3. Verify URI is correct (must use `neo4j+s://` protocol)

### Node Limit Exceeded

**Symptom:** Warning about exceeding 200k nodes

**Cause:** Sample size too large

**Fix:** Reduce `AURA_SAMPLE_LIMIT` in workflow (currently 1000)

### Database Not Cleared

**Symptom:** Tests fail due to existing data

**Cause:** Cleanup step failed in previous run

**Fix:** Manually clear database (see cleanup commands above)

## Local Testing with Aura

To test locally against Aura:

```bash
# Set environment variables
export NEO4J_URI="neo4j+s://0ad2b169.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"
export SBIR_ETL__PIPELINE__SAMPLE_SIZE=1000

# Run E2E tests
uv run pytest tests/e2e/ -v
```

## Comparison: Docker vs Aura

| Feature | Docker (cet-dev-e2e) | Aura (e2e-aura) |
|---------|---------------------|-----------------|
| **Startup time** | ~30 seconds | 0 seconds |
| **Isolation** | Complete | Shared instance |
| **Node limit** | Unlimited | 200k |
| **Cleanup** | Automatic (container removed) | Manual (DETACH DELETE) |
| **Cost** | Free | Free (tier) |
| **Use case** | Fast iteration, large datasets | Cloud testing, realistic env |

## Best Practices

1. **Keep sample sizes small** - Use 1000 nodes or less
2. **Always clear before tests** - Prevent state pollution
3. **Monitor limits** - Check node/relationship counts
4. **Clean up on failure** - Don't leave test data
5. **Use for integration only** - Not for unit tests

## Related Documentation

- [Neo4j Aura Documentation](https://neo4j.com/docs/aura/)
- [E2E Testing Guide](../testing/e2e-testing.md)
- [CI Workflow Documentation](../deployment/ci-cd.md)

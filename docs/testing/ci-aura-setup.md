# CI Setup with Neo4j Aura Free

This guide explains how to configure GitHub Actions CI to use Neo4j Aura Free for testing.

## Why Aura Free for CI?

**Aura Free is now the default** for CI testing because:
- ✅ No Docker issues in GitHub Actions
- ✅ Cloud-hosted (no container management)
- ✅ Free tier available 24/7
- ✅ Fast connection (no container startup time)
- ✅ Automatic cleanup after tests

**Docker is available as a fallback** if Aura Free is unavailable.

---

## Quick Setup (5 minutes)

### Step 1: Create Neo4j Aura Free Instance

1. **Go to** [Neo4j Aura Free](https://neo4j.com/cloud/aura-free/)
2. **Sign up** (free account, no credit card required)
3. **Create a new Aura Free instance**:
   - Name: `sbir-etl-ci` (or any name)
   - Region: Choose closest to your GitHub Actions runners (US regions recommended)
   - Click **Create**

4. **Save credentials immediately!**
   - **Connection URI**: `neo4j+s://<instance-id>.databases.neo4j.io`
   - **Username**: `neo4j` (always this for Aura Free)
   - **Password**: Auto-generated (shown only once!)

   Example URI: `neo4j+s://a1b2c3d4.databases.neo4j.io`

### Step 2: Add GitHub Secrets

1. **Go to your repository** on GitHub
2. **Navigate to**: Settings → Secrets and variables → Actions
3. **Click "New repository secret"** and add these **three secrets**:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `NEO4J_AURA_TEST_URI` | Your Aura connection URI | `neo4j+s://a1b2c3d4.databases.neo4j.io` |
| `NEO4J_AURA_TEST_USERNAME` | Neo4j username | `neo4j` |
| `NEO4J_AURA_TEST_PASSWORD` | Password from Aura console | `your-secure-password-here` |

**Important:**
- Use the **exact secret names** shown above (note the `_TEST` suffix for test environment)
- Include `neo4j+s://` in the URI (the `+s` enables TLS)
- Don't add quotes around values

### Step 3: Verify Setup

**Trigger a test run:**

1. **Push to a PR** or **manually run workflow**:
   - Go to Actions tab → CI workflow → "Run workflow"
   - Leave "Use Docker Neo4j" **unchecked** (default)
   - Click "Run workflow"

2. **Check the workflow logs**:
   - Look for: `☁️  Using Neo4j Aura Free (cloud)`
   - Verify connection: `✅ Neo4j Aura Free connection successful!`
   - Check cleanup: `✅ Cleanup complete! Nodes after: 0`

**That's it!** Your CI now uses Aura Free by default.

---

## Aura Free Limits for CI

### Hard Limits (Aura Free)
- **100,000 nodes** maximum
- **200,000 relationships** maximum
- **200,000 properties** maximum

### CI Configuration (Automatic)
The CI workflow automatically:
- Limits sample size to **1,000 awards** (≈2,000 nodes)
- Checks node count **before tests**
- **Cleans up all test data** after tests (always runs)
- Warns if approaching limits

### Test Requirements
**All tests must stay within limits:**
```python
# Good: Creates ~100 nodes
@pytest.mark.fast
def test_small_dataset():
    # Test with 50 records
    pass

# Bad: Creates 50K+ nodes (exceeds limit)
@pytest.mark.slow  # Don't mark as "fast" - won't run in CI
def test_large_dataset():
    # Test with 10K records
    pass
```

**CI only runs `@pytest.mark.fast` tests** to stay within limits.

---

## Automatic Cleanup

The CI workflow **automatically cleans up** after every test run:

```yaml
- name: Clean up Neo4j test data (Aura Free)
  if: always()  # Runs even if tests fail
  run: MATCH (n) DETACH DELETE n
```

**Cleanup happens:**
- ✅ After successful tests
- ✅ After failed tests
- ✅ After cancelled workflow
- ✅ Always (no manual intervention needed)

**Monitoring:**
- Before tests: Shows current node count
- After tests: Verifies cleanup (should be 0 nodes)

---

## Using Docker Fallback (Optional)

If Aura Free is down or you want to test with Docker:

### Via Workflow Dispatch (Manual Run)

1. **Go to** Actions → CI workflow → "Run workflow"
2. **Check** "Use Docker Neo4j instead of Aura Free"
3. **Click** "Run workflow"

**The workflow will:**
- Use local Docker Neo4j service container
- Skip Aura Free connection check
- Skip cleanup (Docker is ephemeral)

### Via Code (Permanent Change)

Not recommended, but if you want Docker by default:

```yaml
# .github/workflows/ci.yml
workflow_dispatch:
  inputs:
    use_docker:
      default: true  # Change from false to true
```

---

## Troubleshooting

### Problem: "Neo4j Aura credentials not configured"

**Symptom:**
```
⚠️  Warning: Neo4j Aura credentials not configured in GitHub secrets
```

**Solution:**
1. Verify secrets exist: Settings → Secrets and variables → Actions
2. Check exact names: `NEO4J_AURA_TEST_URI`, `NEO4J_AURA_TEST_USERNAME`, `NEO4J_AURA_TEST_PASSWORD`
3. Re-add secrets if misspelled

---

### Problem: "Neo4j Aura Free connection failed"

**Symptom:**
```
❌ Neo4j Aura Free connection failed: ServiceUnavailable
```

**Possible Causes:**

1. **Instance paused** (inactive for 3 days):
   - Go to https://console.neo4j.io/
   - Click **Resume** on your instance
   - Wait 30-60 seconds
   - Re-run workflow

2. **Wrong URI format**:
   - Should be: `neo4j+s://...` (not `bolt://` or `neo4j://`)
   - Include the `+s` for TLS

3. **Wrong password**:
   - Password is case-sensitive
   - Re-check in Aura console (can reset if lost)

4. **Instance deleted** (inactive for 6 months):
   - Create a new Aura Free instance
   - Update GitHub secrets with new credentials

---

### Problem: "Node count approaching limit"

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

---

### Problem: "Tests timing out"

**Symptom:**
```
Tests taking >10 minutes (normally < 2 min)
```

**Possible Causes:**

1. **Aura Free shared resources** (slower than Docker):
   - Expected: Aura Free may be 2-3x slower than local Docker
   - Solution: Use Docker fallback for performance-sensitive tests

2. **Too much test data**:
   - Check: `SBIR_ETL__EXTRACTION__SAMPLE_LIMIT` should be ≤1000
   - Reduce sample size in test-aura.yaml

3. **Network latency**:
   - Aura requires internet connectivity
   - Slower if GitHub runners are far from Aura region

---

### Problem: Workflow fails with "secrets not available"

**Symptom:**
```
secrets.NEO4J_AURA_TEST_URI not found
```

**Cause:** Forks don't have access to repository secrets (security feature)

**Solution for forks:**
1. Fork owner must add their own Aura Free credentials
2. Or use Docker fallback (manual workflow dispatch)

**For organization repos:**
- Secrets are shared across org repos if configured at org level
- Check: Organization Settings → Secrets
- Use same names: `NEO4J_AURA_TEST_URI`, `NEO4J_AURA_TEST_USERNAME`, `NEO4J_AURA_TEST_PASSWORD`

---

## Cost and Limits

### Aura Free
- **Cost:** $0 (free forever)
- **Nodes:** 100,000 max
- **Compute:** Shared resources
- **Pauses:** After 3 days inactivity
- **Deleted:** After 6 months inactivity

**Recommended for:** Fast CI tests with sample data

### Aura Professional (Paid)
- **Cost:** ~$65/month (smallest instance)
- **Nodes:** Unlimited
- **Compute:** Dedicated resources
- **Always on:** Never pauses

**Recommended for:** Nightly/weekly tests with full dataset

### Docker (Free)
- **Cost:** $0 (uses GitHub Actions runners)
- **Nodes:** Unlimited
- **Compute:** Limited by runner (7GB RAM)
- **Ephemeral:** Fresh instance each run

**Recommended for:** Fallback option

---

## Best Practices

### 1. Keep Tests Small
```python
# ✅ Good - Fast test with small dataset
@pytest.mark.fast
def test_company_enrichment():
    sample_size = 100  # Small sample
    # ... test logic

# ❌ Bad - Large dataset for CI
@pytest.mark.slow  # Won't run in CI by default
def test_full_pipeline():
    sample_size = 50000  # Too large for Aura Free
    # ... test logic
```

### 2. Use Fixtures for Cleanup
```python
@pytest.fixture
def neo4j_test_data(neo4j_client):
    """Create test data and clean up after."""
    # Setup: Create test nodes
    yield neo4j_client

    # Teardown: Always cleanup
    with neo4j_client.session() as session:
        session.run("MATCH (n:TestNode) DETACH DELETE n")
```

### 3. Monitor Node Count
```bash
# Before making changes
python scripts/neo4j/check_aura_usage.py

# After tests
python scripts/neo4j/check_aura_usage.py --detailed
```

### 4. Set Sample Limits in Config
```yaml
# config/test-aura.yaml
extraction:
  sbir:
    sample_limit: 1000  # CI-safe limit

  uspto:
    sample_limit: 500  # Keep it small

neo4j:
  max_nodes: 95000  # Safety buffer
  check_node_count: true
```

---

## Migration from Docker to Aura Free

### What Changed?

| Before (Docker) | After (Aura Free) |
|----------------|-------------------|
| Local service container | Cloud-hosted database |
| `bolt://localhost:7687` | `neo4j+s://<id>.databases.neo4j.io` |
| `NEO4J_AUTH: none` | Username + password required |
| Auto cleanup (ephemeral) | Manual cleanup (persistent) |
| Startup time: ~30s | Startup time: 0s (always on) |

### What Stays the Same?

- ✅ Same test commands (`pytest -m fast`)
- ✅ Same configuration system (`ENVIRONMENT=test-aura`)
- ✅ Same Neo4j client code
- ✅ Same Cypher queries

### Rollback to Docker

If you need to revert:

1. **Manual trigger:**
   - Actions → CI → Run workflow → Check "Use Docker"

2. **Update workflow default:**
   ```yaml
   use_docker:
     default: true  # Change to Docker by default
   ```

---

## Summary

**Aura Free for CI is:**
- ✅ **Default** for all PR and push builds
- ✅ **Free** (no cost)
- ✅ **Fast setup** (5 minutes)
- ✅ **Automatic cleanup** (after every run)
- ✅ **Reliable** (no Docker issues)

**Next steps:**
1. ✅ Create Aura Free instance
2. ✅ Add GitHub secrets
3. ✅ Push a PR to test
4. ✅ Verify cleanup in logs

**Need help?** See [TESTING_QUICK_START.md](./TESTING_QUICK_START.md) or [neo4j-aura-testing.md](./neo4j-aura-testing.md)

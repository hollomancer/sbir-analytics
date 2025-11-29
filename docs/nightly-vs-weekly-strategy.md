# Nightly vs Weekly Testing Strategy

## Current State (After On-Demand Changes)

**Current:** All tests run weekly (Sunday 2 AM)
**CI Minutes:** ~0 nightly, ~120-180 weekly

## Optimal Split: Fast Nightly + Comprehensive Weekly

### Nightly (Fast Feedback - ~10-15 min)
**Schedule:** Every night at 3 AM UTC
**Purpose:** Quick smoke tests and security scans
**CI Minutes:** ~10-15/night = ~300-450/month

**Jobs to run nightly:**
1. **Security scans** (~5 min total)
   - `security-scan` (Bandit) - ~2 min
   - `secret-detection` (detect-secrets) - ~2 min
   - `markdown-lint` - ~1 min

2. **Neo4j smoke test** (~5 min)
   - `neo4j-smoke` (dry-run mode) - ~5 min
   - Validates Neo4j connectivity and schema

3. **Developer verification** (~5 min)
   - `verify-local-workflow` - ~3 min
   - `verify-ml-workflow` - ~2 min

**Total nightly:** ~15 minutes
**Why nightly:** Catch security issues and breaking changes early

### Weekly (Comprehensive - ~120-180 min)
**Schedule:** Sunday 2 AM UTC
**Purpose:** Deep testing, performance profiling, auto-repair
**CI Minutes:** ~120-180/week = ~480-720/month

**Jobs to run weekly:**
1. **Extended test suites** (~60-90 min)
   - `tests` (slow-unit, integration, e2e-smoke) - ~30 min
   - `comprehensive-tests` (full suite with real data) - ~90 min
   - `real-data-validation` - ~30 min
   - `performance-profiling` - ~30 min

2. **Auto-repair workflow** (~30 min)
   - `diagnose` - ~5 min
   - `attempt_repair` - ~15 min
   - `fallback_issue` - ~5 min

**Total weekly:** ~120-180 minutes
**Why weekly:** Expensive tests that catch regressions

## Comparison

| Strategy | Nightly CI Min | Weekly CI Min | Monthly Total | Annual Total |
|----------|----------------|---------------|---------------|--------------|
| **Current (weekly only)** | 0 | 120-180 | 480-720 | 5,760-8,640 |
| **Proposed (nightly + weekly)** | 10-15 | 120-180 | 780-1,170 | 9,360-14,040 |
| **Previous (full nightly)** | 30-45 | 120-180 | 1,380-1,830 | 16,560-21,960 |

## Recommendation: Lightweight Nightly

**Add back nightly schedule with ONLY:**
- Security scans (5 min)
- Neo4j smoke test (5 min)
- Developer verification (5 min)

**Benefits:**
- Early detection of security issues
- Daily validation of core infrastructure
- Only ~300-450 CI minutes/month (vs ~900-1,350 for full nightly)
- Saves ~600-900 CI minutes/month vs previous full nightly
- Better than weekly-only (catches issues 6 days earlier)

**Cost:**
- Additional ~300-450 CI minutes/month
- Still saves ~600-900 CI minutes/month vs previous approach

## Implementation

### Option 1: Split into Two Workflows (Recommended)

**`nightly.yml`** - Fast security & smoke tests
```yaml
on:
  schedule:
    - cron: "0 3 * * *"  # 3 AM UTC daily
  workflow_dispatch:

jobs:
  security-scan: ...
  secret-detection: ...
  markdown-lint: ...
  neo4j-smoke: ...
  verify-local-workflow: ...
  verify-ml-workflow: ...
```

**`weekly.yml`** - Comprehensive tests
```yaml
on:
  schedule:
    - cron: "0 2 * * 0"  # Sunday 2 AM UTC
  workflow_dispatch:

jobs:
  tests: ...
  diagnose: ...
  attempt_repair: ...
  comprehensive-tests: ...
  real-data-validation: ...
  performance-profiling: ...
```

### Option 2: Single Workflow with Conditional Jobs

Keep `weekly.yml` but add nightly schedule with job-level conditionals:

```yaml
on:
  schedule:
    - cron: "0 3 * * *"   # Nightly
    - cron: "0 2 * * 0"   # Weekly

jobs:
  # Nightly jobs (run on both schedules)
  security-scan:
    if: always()

  # Weekly-only jobs
  comprehensive-tests:
    if: github.event.schedule == '0 2 * * 0' || github.event.inputs.test_level == 'comprehensive'
```

## Decision Matrix

| Factor | Weekly Only | Lightweight Nightly | Full Nightly |
|--------|-------------|---------------------|--------------|
| **CI Minutes/Month** | 480-720 | 780-1,170 | 1,380-1,830 |
| **Issue Detection Speed** | 7 days | 1 day | 1 day |
| **Security Scan Frequency** | Weekly | Daily | Daily |
| **Cost Efficiency** | ✅ Best | ✅ Good | ❌ Poor |
| **Early Warning** | ❌ Slow | ✅ Good | ✅ Best |
| **Maintenance Burden** | ✅ Low | ✅ Low | ❌ High |

## Recommendation

**Implement Lightweight Nightly (Option 1: Split Workflows)**

**Why:**
- Balances cost (~780-1,170 min/month) with early detection
- Daily security scans catch vulnerabilities quickly
- Daily smoke tests catch breaking changes early
- Still saves ~600-900 CI minutes/month vs previous full nightly
- Clean separation of concerns (fast nightly vs comprehensive weekly)

**Next Steps:**
1. Create `nightly.yml` with 6 fast jobs (~15 min total)
2. Keep `weekly.yml` with comprehensive tests (~120-180 min)
3. Monitor for 2 weeks to validate timing estimates
4. Adjust if nightly runs exceed 20 minutes

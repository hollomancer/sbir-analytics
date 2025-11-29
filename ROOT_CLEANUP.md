# Root Directory Cleanup Recommendations

**Date**: 2025-11-29
**Status**: Proposed

## Current State

Root directory has **42 files** with several cleanup opportunities.

## Cleanup Opportunities

### Priority 1: Archive Completed Summary Files (High Impact)

**Files to Archive:**
```
CLOUD_INFRASTRUCTURE_SUMMARY.md       → archive/summaries/
ENVIRONMENT_CONSOLIDATION_SUMMARY.md  → archive/summaries/
WORKFLOW_CLEANUP.md                   → archive/summaries/
TEST_FIXES_NEEDED.md                  → archive/summaries/
```

**Rationale**: These are point-in-time completion summaries, not living documents.

**Impact**: -4 files from root

### Priority 2: Move Analysis Scripts to scripts/ (Medium Impact)

**Files to Move:**
```
analyze_test_failures.py  → scripts/analysis/
verify_refactor.py        → scripts/analysis/
```

**Rationale**: Utility scripts belong in scripts/ directory, not root.

**Impact**: -2 files from root

### Priority 3: Consolidate Requirements Files (Medium Impact)

**Current:**
```
requirements.txt          (main - used by Docker)
requirements-core.txt     (minimal deps)
requirements-full.txt     (all deps)
```

**Recommendation**: Keep only `requirements.txt` (used by Docker)

**Rationale**:
- `requirements.txt` is generated from uv.lock (source of truth)
- `requirements-core.txt` and `requirements-full.txt` may be stale
- `pyproject.toml` + `uv.lock` are the real source of truth

**Action**:
1. Verify requirements-core.txt and requirements-full.txt aren't used
2. If unused, delete them
3. Keep only requirements.txt (Docker needs it)

**Impact**: -2 files from root (if unused)

### Priority 4: Consolidate Environment Examples (Low Impact)

**Current:**
```
.env.example              (main example)
.env.example.staging      (staging-specific)
.env.test.aura            (Aura testing)
```

**Recommendation**: Keep all three - they serve different purposes

**Rationale**:
- `.env.example` - Local development
- `.env.example.staging` - Staging deployment
- `.env.test.aura` - Neo4j Aura testing

**Action**: No change needed

### Priority 5: Review Markdown Files (Low Impact)

**Current:**
```
AGENTS.md                 (AI agent instructions) ✓ Keep
CONTRIBUTING.md           (Contribution guide) ✓ Keep
README.md                 (Main readme) ✓ Keep
coverage_report.md        (Coverage report) ? Archive or regenerate
walkthrough.md            (Walkthrough guide) ? Review if current
QUICKSTART_MULTI_SOURCE_TESTING.md  ? Review if current
```

**Recommendations:**
- `coverage_report.md` - Archive if point-in-time, or move to reports/
- `walkthrough.md` - Review if still current, consider moving to docs/guides/
- `QUICKSTART_MULTI_SOURCE_TESTING.md` - Review if still current, consider moving to docs/testing/

### Priority 6: Review Config Files (Keep)

**Current:**
```
.dockerignore             ✓ Keep (Docker)
.gitignore                ✓ Keep (Git)
.markdownlint.yaml        ✓ Keep (Linting)
.pre-commit-config.yaml   ✓ Keep (Pre-commit)
.python-version           ✓ Keep (Python version)
.secrets.baseline         ✓ Keep (Secret scanning)
dagster_cloud.yaml        ✓ Keep (Dagster Cloud)
docker-compose.yml        ✓ Keep (Docker Compose)
lifecycle.json            ✓ Keep (Lifecycle config)
mkdocs.yml                ✓ Keep (MkDocs)
pyproject.toml            ✓ Keep (Python project)
uv.lock                   ✓ Keep (UV lock)
workspace.yaml            ✓ Keep (Workspace config)
Dockerfile*               ✓ Keep (Docker builds)
Makefile                  ✓ Keep (Build automation)
MANIFEST.in               ✓ Keep (Package manifest)
LICENSE                   ✓ Keep (License)
```

**Action**: No changes needed - all serve active purposes

## Implementation Plan

### Step 1: Archive Summaries (2 minutes)

```bash
mkdir -p archive/summaries
git mv CLOUD_INFRASTRUCTURE_SUMMARY.md archive/summaries/
git mv ENVIRONMENT_CONSOLIDATION_SUMMARY.md archive/summaries/
git mv WORKFLOW_CLEANUP.md archive/summaries/
git mv TEST_FIXES_NEEDED.md archive/summaries/
```

### Step 2: Move Scripts (2 minutes)

```bash
mkdir -p scripts/analysis
git mv analyze_test_failures.py scripts/analysis/
git mv verify_refactor.py scripts/analysis/
```

### Step 3: Check Requirements Files (5 minutes)

```bash
# Check if requirements-core.txt and requirements-full.txt are used
grep -r "requirements-core" . --exclude-dir=.git
grep -r "requirements-full" . --exclude-dir=.git

# If not used, remove them
git rm requirements-core.txt requirements-full.txt
```

### Step 4: Review Markdown Files (10 minutes)

```bash
# Check if coverage_report.md is current
ls -la coverage_report.md

# Review walkthrough.md and QUICKSTART_MULTI_SOURCE_TESTING.md
# Decide: keep, move to docs/, or archive
```

**Total Time**: ~20 minutes

## Expected Results

### File Count

| Category | Before | After | Change |
|----------|--------|-------|--------|
| Root files | 42 | 34-36 | -6 to -8 |
| Archived | 0 | 4 | +4 |
| Scripts moved | 0 | 2 | +2 |

### Benefits

1. **Cleaner root**: Fewer files to navigate
2. **Better organization**: Scripts in scripts/, summaries in archive/
3. **Easier maintenance**: Clear what's active vs. historical
4. **Reduced confusion**: Obvious which files matter

## Summary

**High Priority** (Do Now):
- Archive 4 summary files
- Move 2 analysis scripts
- Check and remove unused requirements files

**Low Priority** (Review Later):
- Review coverage_report.md
- Review walkthrough.md
- Review QUICKSTART_MULTI_SOURCE_TESTING.md

**Keep As-Is**:
- All config files (.gitignore, .dockerignore, etc.)
- Core documentation (README.md, CONTRIBUTING.md, AGENTS.md)
- Build files (Makefile, Dockerfile, docker-compose.yml)
- Package files (pyproject.toml, uv.lock, requirements.txt)

## Related

- [Documentation Consolidation V2](docs/DOCUMENTATION_CONSOLIDATION_V2_COMPLETE.md)
- [Documentation Assessment V3](docs/DOCUMENTATION_IMPROVEMENTS_V3.md)

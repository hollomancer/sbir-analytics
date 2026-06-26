# Pre-commit and CI Consistency

This document explains how SBIR Analytics maintains consistency between local development (`pre-commit` hooks) and CI (`GitHub Actions` workflows). This consistency ensures that code which passes local checks will also pass CI, and vice versa.

**Document Type:** Explanation
**Owner:** @hollomancer
**Last-Reviewed:** 2025-11-28
**Status:** Active

## Overview

### Why Consistency Matters

Developers should never encounter a situation where:

- Code passes local pre-commit checks but fails in CI
- Code fails locally but passes in CI
- Different tools are used in different environments

This document defines the **single source of truth** for code quality tools and ensures all developers and CI use identical configurations.

### Architecture

```text
Local pre-commit hook            Runs in CI as
─────────────────────            ──────────────
Standard file checks       →     (local only)
Ruff (lint/format)         →     ci.yml · code-quality job
MyPy (types)               →     ci.yml · code-quality job (sbir_etl)
                                 ci.yml · package-type-checks job (packages)
Bandit (security)          →     weekly.yml · security-scan job
Detect-secrets             →     weekly.yml · security-scan job (detect-secrets scan)
(no local hook)            →     ci.yml · workflow-lint job
```

**Key Principle:** Pre-commit hooks define what developers must fix locally. CI runs the same Ruff + MyPy + (removed-src) gates as the `code-quality` job, with per-package MyPy and tests as additional jobs. Bandit and Detect-secrets currently run only as pre-commit hooks locally, not as standalone CI jobs.

---

## Tool Scope Mapping

All tools are configured to run on consistent scopes:

| Tool | Local Scope | CI Scope | Configuration | Notes |
|------|------------|----------|---------------|-------|
| **Ruff** (lint) | `packages/` `sbir_etl/` `tests/` | `packages/` `sbir_etl/` `tests/` | `.pre-commit-config.yaml` + `pyproject.toml` | Code style and import ordering |
| **Ruff** (format) | `packages/` `sbir_etl/` `tests/` | `packages/` `sbir_etl/` `tests/` | `.pre-commit-config.yaml` + `pyproject.toml` | Format check (not auto-fix in CI) |
| **MyPy** (types) | `packages/` `sbir_etl/` only | `packages/` `sbir_etl/` only | `.pre-commit-config.yaml` + `pyproject.toml` | Excludes: `scripts/`, `tests/`, `examples/`, `migrations/` |
| **Bandit** (security) | `packages/` `sbir_etl/` only | `packages/` `sbir_etl/` only | `.pre-commit-config.yaml` + `pyproject.toml` | Security scanning |
| **Standard hooks** | All files | N/A | `.pre-commit-config.yaml` | YAML validation, EOL, trailing whitespace (local only) |
| **Detect-secrets** | All files* | N/A | `.pre-commit-config.yaml` | Secret detection (local best practice) |

*Excludes: vendor directories, build artifacts, docs, environment files (see `.pre-commit-config.yaml`)

### Scope Rationale

**Why `packages/` and `sbir_etl/` only for MyPy and Bandit?**

- Tests, scripts, examples, and migrations are not production code
- These files often use different patterns and are lower priority
- Focusing on production packages ensures production code quality

**Why production packages + `tests/` for Ruff?**

- Tests should follow the same code style as production code
- Ruff is fast and catches important issues (unused imports, naming)
- Consistent formatting improves readability

**Why all files for standard hooks?**

- File integrity checks apply universally
- YAML validation, EOL/whitespace fixes are safe and important
- Low overhead

---

## Local Development Setup

### Installation

1. **Ensure pre-commit is installed:**

   ```bash
   pip install pre-commit
   # or via uv (already in dev dependencies)
   uv pip install pre-commit
   ```

2. **Enable hooks in this repository:**

   ```bash
   cd sbir-analytics
   pre-commit install
   ```

3. **Verify installation:**

   ```bash
   pre-commit --version
   ls -la .git/hooks/pre-commit
   ```

### Usage

**Automatic (on every commit):**

```bash
git commit -m "Your message"
# Hooks run automatically
# If issues found, fix and re-add files
git add .  # Re-add after fixes
git commit -m "Your message"
```

**Manual (check before committing):**

```bash
# Check all changed files
pre-commit run

# Check all files (useful for onboarding)
pre-commit run --all-files

# Check specific tool
pre-commit run ruff --all-files
pre-commit run mypy --all-files
```

**Bypass hooks (use with caution):**

```bash
git commit --no-verify
# This skips hooks, but CI will still check!
```

### Understanding Hook Failures

When a hook fails, you'll see output like:

```console
ruff (legacy alias)......................................................Failed
- hook id: ruff
- exit code: 1

Some rule failed
  --> sbir_etl/file.py:10:5
```

**Common issues:**

- **Ruff errors:** Run `ruff check sbir_etl packages/sbir-analytics/sbir_analytics packages/sbir-ml/sbir_ml packages/sbir-graph/sbir_graph tests --fix` to auto-fix many issues
- **MyPy errors:** Read the error message and add type hints or `# type: ignore` comments
- **Bandit alerts:** Review and fix security issues, or add `# nosec` if false positive
- **Detect-secrets alerts:** Review the secret, or add to `.secrets.baseline` if approved

---

## CI Configuration

### Workflow: `.github/workflows/ci.yml`

This workflow runs on:

- Every push to `main` or `develop`
- Every pull request

**Jobs (in parallel/sequence):**

1. **code-quality**
   - Runs: `ruff check`, `ruff format --check`, `mypy sbir_etl`, and a removed-source-root reference check (`scripts/ci/check_removed_src_references.py`, the "Reject removed source-root references" step).
   - Purpose: Pull-request and push quality gate for checks that mirror the local Ruff/MyPy pre-commit hooks.
   - Time: ~5-10 minutes.

2. **package-type-checks**
   - Runs: package-specific MyPy checks for `sbir-analytics`, `sbir-ml`, and `sbir-graph`.
   - Purpose: Package-level type-checking visibility beyond the core `sbir_etl` check.
   - Time: ~1-2 minutes per package.

3. **workflow-lint**
   - Runs: GitHub Actions workflow syntax/lint validation.
   - Purpose: Keeps the current workflow set valid as `.github/workflows/` changes.

4. **test**, **container-build-test**, **performance-check**, **e2e-docker**, and related CI jobs
   - Runs: unit/integration tests, container checks, performance regression checks, E2E Docker checks, and transition MVP checks as configured in `ci.yml`.
   - Purpose: Keeps PR/push feedback consolidated in the current CI workflow.

### Why Multiple Jobs?

- **code-quality:** Ensures core local style checks pass in CI
- **Individual jobs:** Provide clear, separate visibility in GitHub checks for linting, typing, workflow validation, tests, containers, performance, and E2E coverage
- **Parallelization:** Faster overall execution
- **Debugging:** Easier to identify which check failed

---

## Maintaining Consistency

### When to Update Tool Versions

Tool versions are pinned in:

- `.pre-commit-config.yaml` (local)
- `.github/workflows/ci.yml` (CI)
- `pyproject.toml` (tool configuration)

**Update process:**

1. **Update all three locations together:**

   ```bash
   # Don't update just one - keep them in sync!
   # Update in:
   # - .pre-commit-config.yaml (rev field)
   # - .github/workflows/ci.yml (setup-python-uv action versions)
   # - pyproject.toml (if tool config changes)
   ```

2. **Test locally:**

   ```bash
   pre-commit run --all-files
   ```

3. **Commit the changes:**

   ```bash
   git add .pre-commit-config.yaml .github/workflows/ci.yml pyproject.toml
   git commit -m "chore: update pre-commit tools to [version]"
   ```

4. **PR will verify CI consistency**

### Current Tool Versions

| Tool | Version | Source |
|------|---------|--------|
| Pre-commit hooks | v6.0.0 | `.pre-commit-config.yaml` |
| Ruff | v0.14.4 | `.pre-commit-config.yaml` |
| MyPy | v1.18.2 | `.pre-commit-config.yaml` |
| Bandit | 1.8.6 | `.pre-commit-config.yaml` |
| Detect-secrets | v1.5.0 | `.pre-commit-config.yaml` |

### Configuration Locations

| Item | Local | CI | Notes |
|------|-------|----|----|
| Tool versions | `.pre-commit-config.yaml` | `.pre-commit-config.yaml` | Identical |
| Ruff scope | `.pre-commit-config.yaml` | `ci.yml` | Both: all production roots plus `tests` |
| Ruff config | `pyproject.toml` | `pyproject.toml` | Identical |
| MyPy scope | `pyproject.toml` + `.pre-commit-config.yaml` | `ci.yml` | Local: `sbir_etl`. CI: `sbir_etl` (code-quality) **plus** per-package MyPy for `sbir-analytics`, `sbir-ml`, `sbir-graph` (package-type-checks job) |
| MyPy config | `pyproject.toml` | `pyproject.toml` | Identical |
| Bandit scope | `.pre-commit-config.yaml` | `weekly.yml` security-scan job | Scheduled security scan for production roots |
| Bandit config | `pyproject.toml` | `pyproject.toml` | Identical |

---

## Troubleshooting

### "Pre-commit check failed locally but passed in CI"

**This should not happen.** If it does:

1. Verify pre-commit version matches:

   ```bash
   pre-commit --version
   ```

2. Update pre-commit hooks:

   ```bash
   pre-commit autoupdate
   pre-commit run --all-files
   ```

3. Check `.pre-commit-config.yaml` against `.github/workflows/ci.yml`

4. **Report as bug:** This indicates a configuration mismatch

### "Ruff passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit runs on packages/ sbir_etl/ and tests/
# CI runs on packages/ sbir_etl/ and tests/
# Make sure you're checking the same files

pre-commit run ruff --all-files  # Should match CI

# Or manually
ruff check packages sbir_etl tests
ruff format --check packages sbir_etl tests
```

### "MyPy passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit runs on packages/ sbir_etl/ only
# CI runs on packages/ sbir_etl/ only via: mypy packages sbir_etl

# These should match
pre-commit run mypy --all-files
uv run python -m mypy packages sbir_etl
```

### "Hook modified files I didn't touch"

Some hooks auto-fix issues:

- **end-of-file-fixer:** Adds newlines
- **trailing-whitespace:** Removes trailing spaces
- **Ruff**: Auto-fixes with `--fix` flag

**Solution:**

1. Review changes: `git diff`
2. Re-add: `git add .`
3. Re-commit: `git commit -m "..."`

### "Detect-secrets keeps flagging a false positive"

1. Review the suspected secret cautiously
2. If approved, add to baseline:

   ```bash
   git add .secrets.baseline
   git commit -m "chore: add approved secret to detect-secrets baseline"
   ```

3. New secrets will still be flagged

---

## Common Questions

### Do I have to use pre-commit?

No, but it's strongly recommended. Pre-commit:

- Catches issues before CI
- Saves time by fixing issues locally
- Prevents failed PRs
- Ensures team consistency

If you skip it: `git commit --no-verify`, but CI will still check.

### What if pre-commit is slow?

- Pre-commit skips unchanged files (fast on subsequent runs)
- First run processes everything (slower)
- Individual tools are parallelized

**Speed tips:**

```bash
# Skip non-essential hooks (not recommended)
git commit --no-verify

# Run only changed files (automatic on commit)
pre-commit run

# Or check specific tool
pre-commit run ruff
```

### How do I add a new pre-commit hook?

1. Add to `.pre-commit-config.yaml`
2. Add equivalent CI job to `.github/workflows/ci.yml`
3. Update this documentation
4. Test locally: `pre-commit run --all-files`
5. Submit PR with changes to all three files

### Why are some files excluded from MyPy?

MyPy configuration in `pyproject.toml` has:

```toml
exclude = [
    "scripts/",
    "tests/",
    "examples/",
    "migrations/",
]
```

**Reason:** These are not production code. Focusing on `packages/` and `sbir_etl/` ensures critical code is type-safe while allowing flexibility in test/example code.

If you need type checking for a specific file, add:

```python
# mypy: check_untyped_defs
```

---

## References

- **Pre-commit documentation:** <https://pre-commit.com/>
- **Ruff documentation:** <https://docs.astral.sh/ruff/>
- **MyPy documentation:** <https://mypy.readthedocs.io/en/stable/>
- **Bandit documentation:** <https://bandit.readthedocs.io/en/latest/>
- **Detect-secrets:** <https://github.com/Yelp/detect-secrets>

Project files:

- `.pre-commit-config.yaml` - Local hook configuration
- `.github/workflows/ci.yml` - CI configuration
- `pyproject.toml` - Tool-specific configuration

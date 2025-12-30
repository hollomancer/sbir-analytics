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
Developer's Machine                    GitHub Actions (CI)
└─ git commit                          └─ Pull Request / Push
   └─ pre-commit hooks run            └─ .github/workflows/static-analysis.yml
      ├─ Standard file checks            ├─ pre-commit-check job
      ├─ Ruff (lint/format)             │  (runs all pre-commit hooks)
      ├─ MyPy (types)                   │
      ├─ Bandit (security)              ├─ lint job (Ruff)
      ├─ Detect-secrets                 ├─ types job (MyPy)
                                        ├─ security job (Bandit)
                                        ├─ docs-link-check job
```

**Key Principle:** Pre-commit hooks define what developers must fix locally. The same tools run in CI. Individual CI jobs provide visibility and parallelization.

---

## Tool Scope Mapping

All tools are configured to run on consistent scopes:

| Tool | Local Scope | CI Scope | Configuration | Notes |
|------|------------|----------|---------------|-------|
| **Ruff** (lint) | `src/` `tests/` | `src/` `tests/` | `.pre-commit-config.yaml` + `pyproject.toml` | Code style and import ordering |
| **Ruff** (format) | `src/` `tests/` | `src/` `tests/` | `.pre-commit-config.yaml` + `pyproject.toml` | Format check (not auto-fix in CI) |
| **MyPy** (types) | `src/` only | `src/` only | `.pre-commit-config.yaml` + `pyproject.toml` | Excludes: `scripts/`, `tests/`, `examples/`, `migrations/` |
| **Bandit** (security) | `src/` only | `src/` only | `.pre-commit-config.yaml` + `pyproject.toml` | Security scanning |
| **Standard hooks** | All files | N/A | `.pre-commit-config.yaml` | YAML validation, EOL, trailing whitespace (local only) |
| **Detect-secrets** | All files* | N/A | `.pre-commit-config.yaml` | Secret detection (local best practice) |

*Excludes: vendor directories, build artifacts, docs, environment files (see `.pre-commit-config.yaml`)

### Scope Rationale

**Why `src/` only for MyPy and Bandit?**

- Tests, scripts, examples, and migrations are not production code
- These files often use different patterns and are lower priority
- Focusing on `src/` ensures production code quality

**Why `src/` + `tests/` for Ruff?**

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
  --> src/file.py:10:5
```

**Common issues:**

- **Ruff errors:** Run `ruff check src tests --fix` to auto-fix many issues
- **MyPy errors:** Read the error message and add type hints or `# type: ignore` comments
- **Bandit alerts:** Review and fix security issues, or add `# nosec` if false positive
- **Detect-secrets alerts:** Review the secret, or add to `.secrets.baseline` if approved

---

## CI Configuration

### Workflow: `.github/workflows/static-analysis.yml`

This workflow runs on:

- Every push to `main` or `develop`
- Every pull request

**Jobs (in parallel):**

1. **pre-commit-check** (NEW)
   - Runs: `pre-commit run --all-files`
   - Purpose: Comprehensive local/CI consistency check
   - Covers: All pre-commit hooks (Ruff, MyPy, Bandit, Detect-secrets, Standard checks)
   - Time: ~5-10 minutes

2. **lint** (Ruff)
   - Runs: `ruff check src tests` + `ruff format --check src tests`
   - Purpose: Visibility into linting results
   - Time: ~1-2 minutes

3. **types** (MyPy)
   - Runs: `mypy src`
   - Purpose: Type checking visibility
   - Time: ~1-2 minutes

4. **security** (Bandit)
   - Runs: `bandit -r src -c pyproject.toml`
   - Purpose: Security scanning visibility
   - Time: ~1 minute

5. **docs-link-check** (on docs changes)
   - External link validation
   - Not included in pre-commit (external checks)

### Why Multiple Jobs?

- **pre-commit-check:** Ensures all local checks pass in CI
- **Individual jobs:** Provide clear, separate visibility in GitHub checks
- **Parallelization:** Faster overall execution
- **Debugging:** Easier to identify which check failed

---

## Maintaining Consistency

### When to Update Tool Versions

Tool versions are pinned in:

- `.pre-commit-config.yaml` (local)
- `.github/workflows/static-analysis.yml` (CI)
- `pyproject.toml` (tool configuration)

**Update process:**

1. **Update all three locations together:**

   ```bash
   # Don't update just one - keep them in sync!
   # Update in:
   # - .pre-commit-config.yaml (rev field)
   # - .github/workflows/static-analysis.yml (setup-python-uv action versions)
   # - pyproject.toml (if tool config changes)
   ```

2. **Test locally:**

   ```bash
   pre-commit run --all-files
   ```

3. **Commit the changes:**

   ```bash
   git add .pre-commit-config.yaml .github/workflows/static-analysis.yml pyproject.toml
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
| Ruff scope | `.pre-commit-config.yaml` | `static-analysis.yml` | Both: `src tests` |
| Ruff config | `pyproject.toml` | `pyproject.toml` | Identical |
| MyPy scope | `pyproject.toml` + `.pre-commit-config.yaml` | `static-analysis.yml` | Both: `src` only |
| MyPy config | `pyproject.toml` | `pyproject.toml` | Identical |
| Bandit scope | `.pre-commit-config.yaml` | `static-analysis.yml` | Both: `-r src` |
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

3. Check `.pre-commit-config.yaml` against `.github/workflows/static-analysis.yml`

4. **Report as bug:** This indicates a configuration mismatch

### "Ruff passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit runs on src/ and tests/
# CI runs on src/ and tests/
# Make sure you're checking the same files

pre-commit run ruff --all-files  # Should match CI

# Or manually
ruff check src tests
ruff format --check src tests
```

### "MyPy passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit runs on src/ only
# CI runs on src/ only via: mypy src

# These should match
pre-commit run mypy --all-files
uv run python -m mypy src
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
2. Add equivalent CI job to `.github/workflows/static-analysis.yml`
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

**Reason:** These are not production code. Focusing on `src/` ensures critical code is type-safe while allowing flexibility in test/example code.

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
- `.github/workflows/static-analysis.yml` - CI configuration
- `pyproject.toml` - Tool-specific configuration
- `CONTRIBUTING.md` - Development guidelines

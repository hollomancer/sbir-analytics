# Pre-commit and CI Consistency

This document records how local development checks (`pre-commit` hooks) relate
to CI (`GitHub Actions` workflows). The scopes overlap, but are not identical:
CI is authoritative and deliberately runs checks that have no local hook.

**Document Type:** Explanation
**Owner:** @hollomancer
**Last-Reviewed:** 2026-08-15
**Status:** Active

## Overview

### Why Consistency Matters

Developers should not encounter an *undocumented* difference where:

- Code passes local pre-commit checks but fails in CI
- Code fails locally but passes in CI
- Different tools are used in different environments

This document explains the differences. The executable configurations remain
the source of truth: `.pre-commit-config.yaml` for local hooks and
`.github/workflows/ci.yml` for CI. For architecture / epistemic-tier / identity /
config / hygiene / study guards, `make lint-boundaries` must match the CI quality
job's guard step; if they diverge, CI is authoritative.

### Architecture

```text
Local pre-commit hook            Runs in CI as
─────────────────────            ──────────────
Standard file checks       →     (local only)
Ruff (prod roots + tests)  →     ci.yml · quality job (whole repo via `ruff check .`)
MyPy (sbir_etl only)       →     ci.yml · quality job (also sbir-graph + sbir-ml)
(no local hook)            →     make lint-boundaries / ci.yml quality guards
(no local hook)            →     ci.yml · security job (Bandit)
(no local hook)            →     ci.yml · security job (detect-secrets)
(no local hook)            →     ci.yml · quality job (actionlint)
```

**Key Principle:** Pre-commit provides fast local feedback. CI supersets local
Ruff and MyPy scope, and adds blocking security, boundary, and workflow checks.
Use `make lint` and `make lint-boundaries` before pushing when you need the
CI-equivalent local run.

**Intentional local gaps:** Bandit and detect-secrets are not pre-commit hooks.
Both run in CI's blocking `security` / "Security Scan" job. The local
reproduction commands are documented at the foot of `.pre-commit-config.yaml`.

---

## Tool Scope Mapping

The scopes below are the current contract, including intentional differences:

| Tool | Local Scope | CI Scope | Configuration | Notes |
|------|------------|----------|---------------|-------|
| **Ruff** (lint) | Four production roots + `tests/` | Whole repository (`ruff check .`) | `.pre-commit-config.yaml` + `pyproject.toml` | Local hook is narrower; use `make lint` for CI parity |
| **Ruff** (format) | Four production roots + `tests/` | Whole repository (`ruff format --check .`) | `.pre-commit-config.yaml` + `pyproject.toml` | Same intentional gap as lint |
| **MyPy** (types) | `sbir_etl/` | `sbir_etl/`, `sbir-graph`, `sbir-ml` | `.pre-commit-config.yaml` + `pyproject.toml` | CI is deliberately broader |
| **Boundary guards** | No hook; `make lint-boundaries` | Same scripts as Make | `Makefile` + `ci.yml` | Must stay identical |
| **Bandit** (security) | No hook | `sbir_etl/` and `packages/` | `ci.yml` + `pyproject.toml` | Blocking `security` job |
| **Standard hooks** | All files | N/A | `.pre-commit-config.yaml` | YAML validation, EOL, trailing whitespace (local only) |
| **Detect-secrets** | No hook | Working tree against `.secrets.baseline` | `ci.yml` + `.secrets.baseline` | Blocking `security` job |

### Scope Rationale

**Why is local MyPy limited to `sbir_etl/`?**

- Tests, scripts, and examples are not production code
- CI adds the production `sbir-graph` and `sbir-ml` roots
- The narrower local hook keeps commit-time feedback fast; run the CI command
  below before pushing changes to either additional package

**Why does Bandit scan `sbir_etl/` and all of `packages/` only in CI?**

- The security job provides one blocking, repository-controlled scan
- Bandit's `pyproject.toml` configuration excludes tests
- Avoiding a local hook keeps pre-commit focused on fast checks

**Why is local Ruff narrower than CI?**

- Pre-commit stays fast on the production packages and tests most PRs touch
- CI / `make lint` run `ruff check .` so exploratory `scripts/` and notebooks
  cannot silently drift outside the formatter/linter contract
- Use `make lint` before pushing when you edited scripts or notebooks

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

### Understanding Local and CI Failures

When a hook fails, you'll see output like:

```console
ruff (legacy alias)......................................................Failed
- hook id: ruff
- exit code: 1

Some rule failed
  --> sbir_etl/file.py:10:5
```

**Common issues:**

- **Ruff errors:** Run `make format` or `uv run ruff check . --fix` for CI-parity
  fixes; the pre-commit hook only auto-fixes production roots + tests
- **MyPy errors:** Read the error message and add type hints or `# type: ignore` comments
- **CI Bandit alerts:** Review and fix security issues, or add a justified `# nosec` for a false positive
- **CI detect-secrets alerts:** Review the secret, or update `.secrets.baseline` if approved
- **Boundary / hygiene failures:** Run `make lint-boundaries` locally (same scripts as CI)

---

## CI Configuration

### Workflow: `.github/workflows/ci.yml`

This workflow runs on:

- Every push to `main` or `develop`
- Every pull request

**Jobs (in parallel/sequence):**

1. **quality** ("Lint, Types, and Guards")
   - Runs: `ruff check .`, `ruff format --check .`, `mypy sbir_etl packages/sbir-graph/sbir_graph packages/sbir-ml/sbir_ml`, Dagster definition validation, the architecture/documentation/hygiene guards (same scripts as `make lint-boundaries`), compose-file validation, and actionlint.
   - Purpose: Pull-request and push quality gate. Ruff covers the whole repository
     (broader than the local pre-commit hook); MyPy adds `sbir-graph` and `sbir-ml`
     to the local `sbir_etl` scope.
   - Time: ~5-10 minutes.

   There is no separate package-type-check job: all three type-checked roots are
   arguments to the single blocking MyPy step above. `sbir-analytics` is not yet
   type-checked in CI.

2. **security** ("Security Scan")
   - Runs: `bandit -r sbir_etl packages -c pyproject.toml` and
     `detect-secrets scan --baseline .secrets.baseline`.
   - Purpose: Blocking security coverage that has no local pre-commit hook.

3. **test**, **container-build-test**, **performance-check**, **e2e-docker**, and related CI jobs
   - Runs: unit/integration tests, container checks, performance regression checks, E2E Docker checks, and transition MVP checks as configured in `ci.yml`.
   - Purpose: Keeps PR/push feedback consolidated in the current CI workflow.

### Why Multiple Jobs?

- **quality:** Ensures core local style checks pass in CI
- **security:** Runs the blocking Bandit and detect-secrets scans
- **Individual jobs:** Provide clear, separate visibility in GitHub checks for linting, typing, workflow validation, tests, containers, performance, and E2E coverage
- **Parallelization:** Faster overall execution
- **Debugging:** Easier to identify which check failed

---

## Maintaining Consistency

### When to Update Tool Versions

Local hook environments and CI select tool versions independently:

- `.pre-commit-config.yaml` pins local hook repository revisions.
- `uv.lock` pins the tools installed by CI's locked environment sync.
- `pyproject.toml` constrains CI dependencies and holds shared tool settings.
- detect-secrets is currently installed without a version pin in `ci.yml`.

**Update process:**

1. **Review each version source:**

   ```bash
   # Local hook revisions
   pre-commit autoupdate

   # CI dependency resolution, after editing pyproject.toml constraints
   uv lock
   ```

   Exact local/CI version alignment is preferred for Ruff and MyPy but is not
   guaranteed by the current configuration, so verify both after an update.

2. **Test locally:**

   ```bash
   pre-commit run --all-files
   ```

3. **Commit only the files that changed:**

   ```bash
   git add .pre-commit-config.yaml pyproject.toml uv.lock
   git commit -m "chore: update pre-commit tools to [version]"
   ```

4. **The PR will verify the CI-installed versions and behavior.**

### Current Tool Versions

| Tool | Local pre-commit | CI | Source |
|------|------------------|----|--------|
| Standard hooks | v6.0.0 | Not run | `.pre-commit-config.yaml` |
| Ruff | v0.14.4 | 0.14.5 | `.pre-commit-config.yaml`; `uv.lock` |
| MyPy | v1.18.2 | 1.18.2 | `.pre-commit-config.yaml`; `uv.lock` |
| Bandit | No hook | 1.8.6 | `uv.lock` |
| Detect-secrets | No hook | Not pinned | `uv pip install detect-secrets` in `ci.yml` |

### Configuration Locations

| Item | Local | CI | Notes |
|------|-------|----|----|
| Ruff scope | `.pre-commit-config.yaml` | `ci.yml` | Local: production roots + tests. CI / `make lint`: whole repo |
| Ruff config | `pyproject.toml` | `pyproject.toml` | Identical |
| MyPy scope | `pyproject.toml` + `.pre-commit-config.yaml` | `ci.yml` | Local: `sbir_etl`. CI: `sbir_etl` **plus** `sbir-graph` and `sbir-ml`, all in the `quality` job |
| MyPy config | `pyproject.toml` | `pyproject.toml` | Identical |
| Boundary guards | `Makefile` `lint-boundaries` | `ci.yml` quality job | Must stay identical |
| Bandit scope | No hook; manual command available | `ci.yml` | CI scans `sbir_etl/` and `packages/` in the `security` job |
| Bandit config | `pyproject.toml` | `pyproject.toml` | Same when reproduced locally |
| Detect-secrets scope | No hook; manual command available | `ci.yml` | CI scans the working tree against `.secrets.baseline` |

---

## Troubleshooting

### "Pre-commit check failed locally but passed in CI"

This can happen because standard file hooks are local-only and Ruff can modify
files locally. If the same tool and file fail differently:

1. Record the local runner and hook output:

   ```bash
   pre-commit --version
   pre-commit run --all-files --verbose
   ```

2. Rebuild the pinned local hook environments if they are stale:

   ```bash
   pre-commit clean
   pre-commit install-hooks
   pre-commit run --all-files
   ```

3. Check `.pre-commit-config.yaml` against `.github/workflows/ci.yml`

4. **Report as bug:** This indicates a configuration mismatch

### "Ruff passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit: production roots + tests only
pre-commit run ruff --all-files

# CI / make lint: whole repository
make lint
# or
uv run python -m ruff check .
uv run python -m ruff format --check .
```

### "MyPy passes locally but fails in CI"

**Check scope:**

```bash
# Local pre-commit checks sbir_etl/ only
pre-commit run mypy --all-files
uv run python -m mypy sbir_etl

# CI deliberately adds sbir-graph and sbir-ml
uv run python -m mypy sbir_etl packages/sbir-graph/sbir_graph packages/sbir-ml/sbir_ml
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

### "The CI detect-secrets scan flags a false positive"

1. Review the suspected secret cautiously
2. Install and rerun the scanner exactly as CI does:

   ```bash
   uv pip install detect-secrets
   uv run detect-secrets scan --baseline .secrets.baseline
   ```

3. If the baseline change is approved, commit it:

   ```bash
   git add .secrets.baseline
   git commit -m "chore: add approved secret to detect-secrets baseline"
   ```

4. New secrets will still be flagged

---

## Common Questions

### Do I have to use pre-commit?

No, but it's strongly recommended. Pre-commit:

- Catches issues before CI
- Saves time by fixing issues locally
- Prevents failed PRs
- Ensures team consistency

If you skip it: `git commit --no-verify`, but CI will still check.
CI also runs broader MyPy and security checks, regardless of whether the local
hooks are enabled.

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
2. Decide whether CI should run the same tool and document any scope difference
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
]
```

**Reason:** These are not production code. Local pre-commit focuses on
`sbir_etl/`; CI also type-checks the `sbir-graph` and `sbir-ml` production
packages while leaving tests, scripts, and examples out of scope.

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

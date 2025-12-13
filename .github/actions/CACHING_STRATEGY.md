# GitHub Actions Caching Strategy

This document describes the caching strategy used across GitHub Actions workflows to improve performance and reduce costs.

## Overview

Caching in GitHub Actions helps:

- **Speed up CI runs** by reusing previously built artifacts
- **Reduce costs** by avoiding redundant work
- **Improve reliability** by using known-good cached artifacts

## Caching Principles

1. **Cache key determinism**: Cache keys must be deterministic and based on input files (e.g., `uv.lock`, `package-lock.json`)
2. **Cache invalidation**: Caches automatically expire after 7 days of no use
3. **Cache size limits**: GitHub provides 10GB free storage per repository
4. **Cache scoping**: Caches are scoped to the repository and branch

## Cached Artifacts

### 1. Python Virtual Environment (UV)

**Location**: `.venv/`

**Cache Key**: `venv-{os}-{python-version}-{hash(uv.lock)}`

**Action**: `.github/actions/setup-python-uv`

**How it works**:

- Cache key includes OS, Python version, and hash of `uv.lock`
- Cache is restored before dependency installation
- Cache is saved after successful installation
- Automatically invalidates when `uv.lock` changes

**Example**:

```yaml
- name: Cache UV virtual environment
  uses: actions/cache@v4
  with:
    path: .venv
    key: venv-${{ runner.os }}-${{ inputs.python-version }}-${{ hashFiles('**/uv.lock') }}
    restore-keys: |
      venv-${{ runner.os }}-${{ inputs.python-version }}-
```

### 2. UV Binary

**Location**: `$HOME/.cargo/bin/uv`, `$HOME/.local/bin/uv`

**Cache Key**: `uv-binary-{os}-latest`

**Action**: `.github/actions/setup-python-uv`

**How it works**:

- UV is installed via `curl` script
- Binary location is cached to avoid re-downloading
- Cache key is OS-specific only (UV version managed separately)

### 3. Pytest Cache

**Location**: `.pytest_cache/`

**Cache Key**: `pytest-{os}-{python-version}-{hash(test-files)}`

**Action**: `.github/actions/setup-python-uv` (optional)

**How it works**:

- Only enabled when `cache-pytest: "true"` is set
- Cache key includes hash of test files
- Helps pytest skip unchanged tests (with `--lf` flag)

**Usage**:

```yaml
- uses: ./.github/actions/setup-python-uv
  with:
    cache-pytest: "true"  # Enable pytest cache
```

### 4. Pip Packages (for pyreadstat)

**Location**: `~/.cache/pip/`

**Cache Key**: `pip-packages-{os}-{hash(uv.lock)}`

**Action**: `.github/actions/setup-python-uv`

**How it works**:

- Only used when `install-pyreadstat: "true"` is set
- Caches pip packages downloaded for pyreadstat
- Reduces download time on subsequent runs

### 5. Docker Build Cache (Planned)

**Location**: Docker BuildKit cache

**Cache Key**: `docker-build-{hash(Dockerfile,deps)}`

**Status**: Not yet standardized across all workflows

**Future implementation**:

- Use `docker buildx build --cache-from` and `--cache-to`
- Cache Docker layer builds
- Significantly speeds up Docker image builds

**Example**:

```yaml
- name: Build Docker image with cache
  run: |
    docker buildx build \
      --cache-from type=gha \
      --cache-to type=gha,mode=max \
      -t myimage:latest .
```

## Cache Management

### Manual Cache Invalidation

To manually invalidate a cache:

1. **GitHub UI**: Go to repository → Actions → Caches → Delete cache
2. **API**: Use GitHub API to delete cache entries
3. **Workflow**: Modify cache key to force invalidation

### Cache Size Monitoring

Monitor cache usage:

- **GitHub UI**: Settings → Actions → Caches
- **API**: `GET /repos/{owner}/{repo}/actions/cache/usage`

### Best Practices

1. **Include file hashes in keys**: This ensures caches invalidate when dependencies change
2. **Use restore-keys**: Allows partial cache hits for faster restoration
3. **Don't cache secrets**: Never cache files containing secrets or credentials
4. **Limit cache size**: Be mindful of the 10GB limit per repository
5. **Document cache keys**: Use descriptive names that indicate what's cached

## Cache Performance Metrics

Monitor cache hit rates to measure effectiveness:

- **High hit rate (>80%)**: Cache is working well
- **Low hit rate (<50%)**: May need to adjust cache keys or strategy
- **Cache misses**: Check if cache keys are too specific or frequently changing

## Troubleshooting

### Cache Not Restoring

1. Check cache key matches exactly (including OS, Python version)
2. Verify files used in hash exist and are tracked
3. Check if cache expired (7 days of no use)

### Cache Too Large

1. Exclude unnecessary files from cache path
2. Use more specific cache keys to reduce cache size
3. Manually delete old caches via GitHub UI

### Slow Cache Restoration

1. Use `restore-keys` to allow partial matches
2. Split large caches into smaller, more targeted caches
3. Consider using `actions/cache/save` to save in parallel with other work

## Future Improvements

1. **Docker layer caching**: Standardize Docker BuildKit cache across all workflows
2. **Artifact caching**: Cache large build artifacts between runs
3. **Test result caching**: Cache test results for faster re-runs
4. **Dependency download caching**: Cache package manager downloads (already done for pip)

## References

- [GitHub Actions Caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [actions/cache documentation](https://github.com/actions/cache)
- [Docker BuildKit cache](https://docs.docker.com/build/cache/)

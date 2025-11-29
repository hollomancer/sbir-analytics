# Composite Actions

This directory contains reusable composite actions that encapsulate common patterns used across workflows.

## Available Actions

### 1. `setup-environment`
Complete environment setup for CI jobs.

**Usage:**
```yaml
- name: Setup environment
  uses: ./.github/actions/setup-environment
  with:
    python-version: "3.11"
    install-dev-deps: "true"
    setup-aws: "false"
```

**Includes:**
- Checkout code
- Setup AWS credentials (optional)
- Setup Python and UV with caching

### 2. `setup-and-test`
Common pattern for running tests with sharding support.

**Usage:**
```yaml
- name: Run tests
  uses: ./.github/actions/setup-and-test
  with:
    python-version: "3.11"
    test-marker: "fast"
    shard-id: "1"
    num-shards: "4"
    coverage: "true"
```

**Features:**
- Automatic sharding support
- Coverage reporting
- JSON test results
- Parallel execution with pytest-xdist

### 3. `setup-and-build-docker`
Docker build with caching.

**Usage:**
```yaml
- name: Build Docker image
  uses: ./.github/actions/setup-and-build-docker
  with:
    image-name: ${{ github.repository }}
    tags: |
      myimage:latest
      myimage:${{ github.sha }}
    push: "true"
    cache-scope: "main"
```

**Features:**
- BuildKit caching (GHA + registry)
- Automatic registry login
- Multi-platform support via Buildx

## Benefits

- **DRY**: Eliminate duplicate code across workflows
- **Consistency**: Ensure same patterns everywhere
- **Maintainability**: Update once, apply everywhere
- **Readability**: Clearer workflow files

## Usage Statistics

- `setup-environment`: Used in lint, type-check, and other jobs
- `setup-and-test`: Can replace test setup in multiple workflows
- `setup-and-build-docker`: Used in container-build-test

## Migration Guide

### Before:
```yaml
steps:
  - uses: actions/checkout@v4
  - name: Setup Python and UV
    uses: ./.github/actions/setup-python-uv
    with:
      python-version: "3.11"
      install-dev-deps: "true"
      cache-venv: "true"
  - name: Run tests
    run: pytest -m fast
```

### After:
```yaml
steps:
  - name: Setup and test
    uses: ./.github/actions/setup-and-test
    with:
      test-marker: "fast"
```

**Lines saved:** 8 → 3 (62% reduction)

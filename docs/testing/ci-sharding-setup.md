# CI Test Sharding Setup

## Overview

The CI pipeline uses pytest test sharding to parallelize test execution across multiple jobs, reducing total CI time.

## Required Plugins

Added to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest-shard>=0.1.2",      # Test sharding across jobs
    "pytest-json-report>=1.5.0", # JSON test reports
    # ... other dev dependencies
]
```

## Usage in CI

The `.github/workflows/ci.yml` workflow uses a matrix strategy to run tests in parallel:

```yaml
strategy:
  matrix:
    shard: [0, 1, 2, 3]  # 4 parallel jobs

steps:
  - name: Run fast tests (sharded)
    run: |
      uv run pytest -m fast \
        --cov=src \
        --cov-report=xml \
        --shard-id=${{ matrix.shard }} \
        --num-shards=4 \
        --json-report \
        --json-report-file=test-results-shard-${{ matrix.shard }}.json \
        -n 2  # 2 workers per shard via pytest-xdist
```

## How It Works

1. **Test Sharding**: `pytest-shard` divides tests into N equal groups
   - `--shard-id=0 --num-shards=4` runs 1/4 of tests (shard 0)
   - Each shard runs independently in parallel CI jobs

2. **Parallel Execution**: `pytest-xdist` runs tests within each shard in parallel
   - `-n 2` uses 2 workers per shard
   - Total parallelism: 4 shards × 2 workers = 8 parallel test processes

3. **JSON Reports**: `pytest-json-report` generates structured test results
   - Used for test result aggregation across shards
   - Enables detailed test analytics and failure tracking

## Local Testing

Test sharding locally:

```bash
# Run shard 0 of 4
uv run pytest --shard-id=0 --num-shards=4

# Run with parallel execution
uv run pytest --shard-id=0 --num-shards=4 -n 2

# Generate JSON report
uv run pytest --json-report --json-report-file=test-results.json
```

## Performance Benefits

- **Without sharding**: ~60s for all unit tests sequentially
- **With sharding (4 jobs)**: ~15-20s per shard = 4x speedup
- **With xdist (2 workers)**: Additional 1.5-2x speedup per shard

**Total speedup**: ~6-8x faster CI test execution

## Troubleshooting

### Missing Plugin Error

```
pytest: error: unrecognized arguments: --shard-id
```

**Solution**: Install dev dependencies with extras:

```bash
uv sync --extra dev
```

### Uneven Shard Distribution

If one shard takes much longer than others, adjust the number of shards or use pytest-xdist's load balancing:

```bash
# Use more shards for better distribution
--num-shards=8

# Or rely on xdist load balancing with more workers
-n auto  # Uses all CPU cores
```

## Related Documentation

- [pytest-shard documentation](https://pypi.org/project/pytest-shard/)
- [pytest-json-report documentation](https://pypi.org/project/pytest-json-report/)
- [pytest-xdist documentation](https://pytest-xdist.readthedocs.io/)

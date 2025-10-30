---
Type: Guide
Owner: qa@project
Last-Reviewed: 2025-10-30
Status: active
---

# Quality Assurance

This guide centralizes performance and data quality practices.

## Performance monitoring
- Utilities: `src/utils/performance_*.py`
- Baselines: `reports/benchmarks/baseline.json`
- Thresholds: `config/base.yaml`

## Data quality
- Utilities: `src/utils/quality_*.py`
- Alerts: `reports/alerts/*.json`

## CI
- Performance regression checks in `.github/workflows/performance-regression-check.yml`
- Smoke tests against Neo4j in `.github/workflows/neo4j-smoke.yml`

Ensure PRs that change performance-sensitive paths update baselines/thresholds when appropriate.

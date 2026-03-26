---

Type: Guide
Owner: qa@project
Last-Reviewed: 2025-10-30
Status: active

---

# Quality Assurance

This guide centralizes performance and data quality practices.

## Performance monitoring

- Utilities: `sbir_etl/utils/performance_*.py`
- Baselines: `reports/benchmarks/baseline.json`
- Thresholds: `config/base.yaml`

## Data quality

- Utilities: `sbir_etl/utils/quality_*.py`
- Alerts: `reports/alerts/*.json`

## CI

- CI checks in `.github/workflows/ci.yml`
- Nightly tests in `.github/workflows/nightly.yml`

Ensure PRs that change performance-sensitive paths update baselines/thresholds when appropriate.

## Related Documentation

- **Statistical Reporting**: [`statistical-reporting.md`](statistical-reporting.md) - Report generation and analysis
- **Performance Monitoring**: [`../performance.md`](../performance.md) - Performance baselines and alerts
- **Testing Documentation**: [`../testing/README.md`](../testing/README.md) - Testing guides and coverage

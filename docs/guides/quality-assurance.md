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

- CI checks in `.github/workflows/ci.yml` — the only workflow. Lint, types, and
  guards run on every PR alongside the fast unit suite; the full suite runs on
  `main`.
- Scheduled work (data refresh, reporting, security scans, image builds) does
  not run in GitHub Actions. See
  [`../deployment/mac-mini-server.md`](../deployment/mac-mini-server.md).

## Related Documentation

- **Statistical Reporting**: [`statistical-reporting.md`](statistical-reporting.md) - Report generation and analysis
- **Performance Monitoring**: [`../performance.md`](../performance.md) - Performance baselines and alerts
- **Testing Documentation**: [`../testing/README.md`](../testing/README.md) - Testing guides and coverage

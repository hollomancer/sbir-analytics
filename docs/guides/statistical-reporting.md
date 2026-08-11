---
Type: Guide
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-03
Status: active
---

# Statistical Reporting

`sbir_etl.utils.statistical_reporter.StatisticalReporter` converts explicitly supplied pipeline
metrics into JSON, HTML, and Markdown artifacts. It is a reporting utility, not a scheduled
workflow, evidence validator, PR commenter, or publication system.

## Public interface

```python
from datetime import UTC, datetime
from pathlib import Path

from sbir_etl.utils.statistical_reporter import StatisticalReporter

reporter = StatisticalReporter(output_dir=Path("reports/statistical"))

module = reporter.generate_module_report(
    module_name="sbir_enrichment",
    run_id="example-run",
    stage="enrich",
    metrics_data={
        "records_in": 100,
        "records_processed": 98,
        "records_failed": 2,
        "start_time": datetime.now(UTC),
        "end_time": datetime.now(UTC),
    },
)

collection = reporter.generate_reports(
    {
        "run_id": "example-run",
        "pipeline_name": "sbir-analytics",
        "modules": {"sbir_enrichment": module.model_dump()},
    }
)
```

The maintained public methods are:

- `generate_module_report(...)` for one module's normalized metrics;
- `generate_reports(run_context)` for a multi-format `ReportCollection`;
- `aggregate_module_reports(...)` for the older `ModuleReport` model path.

Executive-summary creation is private implementation detail. There are no public
`generate_executive_summary()`, `generate_executive_dashboard()`,
`identify_success_stories()`, or `calculate_program_effectiveness()` methods.

## Output and CI boundary

The default output directory is `reports/statistical/`; callers may supply another `Path`. The
reporter detects CI environment metadata, but `.github/workflows/ci.yml` does not currently upload
these reports or post them to pull requests. Document that behavior only if a workflow begins
calling the reporter and publishing its artifacts.

Reports describe metrics supplied by the caller. They do not prove source completeness, validate a
research estimand, or make findings citable. Use the [data-quality contract](../steering/data-quality.md)
for pipeline checks and [study contracts](../../studies/README.md) for research evidence.

## Verification

Focused behavior is covered by `tests/unit/utils/test_statistical_reporter.py` and
`tests/unit/utils/reporting/`. Run:

```bash
uv run pytest tests/unit/utils/test_statistical_reporter.py tests/unit/utils/reporting/ -q
```

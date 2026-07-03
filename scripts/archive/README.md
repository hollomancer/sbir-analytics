# Archived scripts

One-off research and analysis scripts whose outputs have already landed in
`docs/research/` (or that were superseded by Dagster assets). They are kept
here — runnable and greppable — for reproducing published analyses, but they
are **not** part of the operational pipeline: nothing in CI, the Makefile,
docker-compose, or the Dagster deployment invokes them.

Archived 2026-07-02 as part of the scripts/ triage:

- `data/` — Form D / DoD leverage cluster, M&A exit analyses, Phase III
  universe builders, USAspending lookups, benchmark dataset generators.
  Their published outputs live in `docs/research/`.
- `validation/` — manual spot-check validators referenced only by archived
  docs.
- Top level — `extract_federal_contracts.py` / `extract_sbir_vendors.py`
  (superseded extraction paths), `run_cet_drift.py` (superseded by the
  `validated_cet_drift_detection` Dagster asset), `run_transition.py`
  (superseded by `transition_mvp_job` / `transition_full_job`),
  `run_full_enrichment.py`, `pipeline_status.py`, `pipeline_metrics.py`
  (orphaned operator conveniences).

Archived 2026-07-03, second triage pass (resolving the "unclear" bucket
from the first pass — each was unreferenced by any workflow/Makefile/
docker-compose, confirmed by grep and, where feasible, by running it):

- `merge_company_search.py` — premise (merging multiple `company_search_*.csv`
  exports) doesn't match how the categorization workflow actually ingests
  this data today (a single named export).
- `get_usaspending_stats.py` — superseded by the `usaspending_profile_report`
  Dagster asset, which reads the same `reports/usaspending_subset_profile.json`
  and surfaces the same fields.
- `generate_fixture.py` / `generate_sbir_sample.py` — both claim to (re)generate
  `tests/fixtures/sbir_sample.csv`, but neither's column order/header matches
  the real fixture the test suite depends on (`tests/conftest.py`,
  `tests/unit/extractors/test_sbir_extractor.py`); running either would
  silently corrupt that fixture.
- `generate_usaspending_test_data.py` — no test or doc consumes its output;
  the extractor tests build their own inline fixtures instead.
- `validation/validate_dagster.py` — calls Dagster `Definitions` methods
  (`get_all_asset_specs` etc.) removed from the pinned Dagster version;
  confirmed to fail immediately with `AttributeError`.
- `validation/validate_enrichment_quality.py` — imports
  `scripts.lib.cli_utils`, a module that has never existed anywhere in this
  repo's history; has never run successfully.
- `validation/validate_transition_detection.py` / `validate_performance.py` —
  manual smoke tests for `TransitionDetector` superseded by the real
  assertion-based suite in `tests/unit/transition/detection/` (correctness)
  and `scripts/performance/detect_performance_regression.py` (perf, which
  has an actual CI-tracked baseline these scripts lack).
- `validation/validate_patent_etl_deployment.py` — its default input file
  was never committed (fails immediately by default), and its later
  "asset check"/"query pattern" stages are simulated rather than real —
  they don't execute against Neo4j.

Unit tests for archived scripts live in `tests/unit/scripts/archive/` and
still run in CI, so the archived code keeps passing until someone decides to
delete it for good. (None of the second-pass scripts above had tests to
move — confirmed by grep across `tests/`.)

Note: `scripts/init_cet_baseline.py`, `scripts/promote_cet_baseline.py`,
`scripts/run_benchmark.py` (the shippable Commercialization Benchmark CLI —
see `docs/commercialization-benchmark-methodology.md`), and
`scripts/setup_congressional_districts.py` (bootstraps the ZIP→Congressional-
District crosswalk `CongressionalDistrictResolver` depends on) were
deliberately **not** archived — each is either documented as a live tool or
serves a data dependency for tested library code.

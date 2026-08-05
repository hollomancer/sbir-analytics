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
- Top level — `extract_federal_contracts.py` (superseded extraction path),
  `run_cet_drift.py` (superseded by the
  `validated_cet_drift_detection` Dagster asset), `run_transition.py`
  (superseded by `transition_mvp_job` / `transition_full_job`),
  `run_full_enrichment.py`, `pipeline_status.py`, `pipeline_metrics.py`
  (orphaned operator conveniences).

The broken and superseded scripts identified in the 2026-07-03 second triage
were deleted in 2026-08. They included obsolete company-search and
USAspending helpers, fixture generators that did not match the real fixtures,
and validators that either could not run or had assertion-based replacements.
None had active callers, documentation references, or tests.

Unit tests for the remaining archived research scripts live in
`tests/unit/scripts/archive/` and still run in CI so the reproducibility paths
keep passing.

Note: `scripts/init_cet_baseline.py`, `scripts/promote_cet_baseline.py`,
`scripts/run_benchmark.py` (the shippable Commercialization Benchmark CLI —
see `docs/commercialization-benchmark-methodology.md`), and
`scripts/setup_congressional_districts.py` (bootstraps the ZIP→Congressional-
District crosswalk `CongressionalDistrictResolver` depends on) were
deliberately **not** archived — each is either documented as a live tool or
serves a data dependency for tested library code.

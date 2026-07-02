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

Unit tests for archived scripts live in `tests/unit/scripts/archive/` and
still run in CI, so the archived code keeps passing until someone decides to
delete it for good.

Note: `scripts/init_cet_baseline.py` and `scripts/promote_cet_baseline.py`
were deliberately **not** archived — they are the manual baseline
bootstrap/promotion pair that the CET drift asset expects an operator to run.

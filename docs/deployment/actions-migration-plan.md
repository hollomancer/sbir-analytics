# GitHub Actions Migration Plan

Move the five scheduled workloads that used to run in GitHub Actions onto the
Mac mini, as Dagster schedules or host cron. GitHub Actions is now tests only:
fast unit tests on PRs, the full suite on `main`.

**Depends on** [#501](https://github.com/hollomancer/sbir-analytics/pull/501),
which deletes the workflows described here. Until that merges, the workflows
still exist (though `weekly.yml` has been in an invalid state and not running).

See [the Mac mini runbook](mac-mini-server.md) for the target host, and
[the AWS decommission plan](aws-decommission-plan.md) for the earlier phase that
moved ingestion off Actions. This plan finishes that job.

## What is already done

The hard part — ingestion — landed in the AWS decommission. Four source-download
jobs and three chaining sensors run on the mini, and `monthly_phase_transition`
already carries the phase-transition half of `monthly-analysis.yml`. This plan
covers what was left behind.

## Patterns to follow

Three conventions already exist in the repo. Use them rather than inventing new
ones; each of the migrations below is a straightforward application.

**Schedules** go in the `_HOST_SCHEDULES` tuple in
`packages/sbir-analytics/sbir_analytics/definitions.py` as
`(job_name, schedule_name, default_cron, label)`. The loop below it builds a
`ScheduleDefinition` with env-var overrides
(`SBIR_ETL__DAGSTER__SCHEDULES__<NAME>_CRON` and `…_ENABLED`) and
`default_status` **stopped**. Keep that default: the runbook requires an
operator to confirm a manual run on the host before enabling.

**Wrapping a script as a job** follows
`assets/jobs/phase_transition_archive.py` — an `@op` that `subprocess.run`s the
script, logs the stderr tail and raises on a non-zero exit, composed into a
`@job`. None of the five scripts below are wrapped in Dagster yet, so each needs
this.

**Durable output** matters more than it did. Every retired workflow uploaded
GitHub artifacts with 7–90 day retention, and those expire. The phase-transition
archive already solves this by writing dated directories under
`<data_root>/processed/…/history/<date>/`. Each migration needs an equivalent
or its output series is lost.

**Document each schedule** in a runbook table in `mac-mini-server.md`, matching
the existing "Source-data downloads" and "Monthly analysis" sections.

## Cross-cutting work

Do these once, not per workload.

**Failure notification is the real risk.** GitHub Actions emailed on a failed
scheduled run. Dagster schedules on a Tailscale-only host surface failures only
in a UI nobody is looking at, and they default to stopped — so a migrated job
can silently never run. This is exactly the failure mode that let `weekly.yml`
sit dead: broken, and nothing said so. Decide on a notification path (Dagster
run-failure sensor → email/Slack/ntfy) **before** migrating, not after.

**Secrets move to `.env.server`.** `OPENAI_API_KEY` and `SAM_GOV_API_KEY` are
needed by items 2, 3, and 4. Once migrated, delete the now-unused repository
secrets in GitHub settings — `NEO4J_USER`, `NEO4J_PASSWORD`, `S3_BUCKET`, and
`AWS_ROLE_ARN` have no remaining consumer.

**Keep crons in UTC.** Every workflow cron below is UTC and Dagster's
`ScheduleDefinition` is UTC here too, so times port unchanged. The mini is on
local time; do not convert.

## The five workloads

Ordered by priority, which is not the order of difficulty.

### 1. Nightly security scan — do this first

| | |
|---|---|
| Was | `weekly.yml` · `security-scan` job |
| Cron | `0 3 * * *` |
| Runs | `bandit -r sbir_etl packages -c pyproject.toml`, then `detect-secrets scan --baseline .secrets.baseline` |
| Secrets | none |
| Target | **host cron**, not Dagster |

First because it is the only item with **no fallback at all**. Bandit and
detect-secrets ran nowhere else — they are not pre-commit hooks, despite
comments that used to claim otherwise. Right now the repo has no automated
security scanning.

Host cron rather than Dagster: this scans the source tree, not the data. It has
no assets, no lineage, and no reason to sit in an orchestrator. A cron entry
running the two commands against the server checkout and writing output to a
dated file is the whole job. Adding them to `.pre-commit-config.yaml` as a
manual-stage hook is a reasonable complement but not a substitute — nothing
guarantees a hook runs.

Verify: introduce a known finding (a hardcoded test credential on a scratch
branch), confirm the scan reports it and the failure reaches you.

### 2. Weekly awards report

| | |
|---|---|
| Was | `weekly.yml` · `weekly-awards-report` job |
| Cron | `0 12 * * 1` (Monday) |
| Runs | `scripts/data/weekly_awards_report.py --days 7 --output reports/weekly-awards.md` |
| Secrets | `OPENAI_API_KEY`, `SAM_GOV_API_KEY` |
| Output | job summary + 30-day artifact |
| Target | Dagster job + schedule |

The simplest data migration and a good first exercise of the pattern: one
script, one flag, no chaining. Wrap as `weekly_awards_report_job`, schedule as
`weekly_awards_report`, and write the markdown to
`<data_root>/reports/weekly_awards/<date>/weekly-awards.md` so the weekly series
accumulates instead of expiring.

Verify: run the job by hand on the host, confirm the report matches a recent
Actions artifact for the same lookback window, then enable the schedule.

### 3. Monthly benchmark evaluation — diagnose before porting

| | |
|---|---|
| Was | `monthly-analysis.yml` · `benchmark` job |
| Cron | `0 6 1 * *` |
| Runs | `scripts/data/run_benchmark_analysis.py --usaspending-api --fy … --margin-awards … --margin-ratio …`, then `scripts/ci/benchmark_summary.py` |
| Secrets | none (USAspending API is unauthenticated) |
| Output | four artifacts, 30-day retention: SBIR awards input, USAspending API cache + obligations, per-company evaluation detail, and the results set (`run_manifest.json`, `artifact_manifest.json`, `benchmark_evaluation.json`, `sensitivity_report_fy*.md`, `at_risk.json`) |
| Target | Dagster job + schedule, after diagnosis |

**Do not port this as-is.** The run history shows the same shape every month
since May: a ~30-second `failure` at around 06:50 UTC, then a ~60-second
`success` later the same day. The job budgets 180 minutes with a 90-minute
timeout on the benchmark step. A benchmark that finishes in 60 seconds is not
computing what the timeout suggests it should.

Establish what the successful runs actually produced — pull a recent
`run_manifest.json` and `benchmark_evaluation.json` artifact before they expire —
then port the behaviour you want rather than the behaviour you have.

The `actions/cache` of `usaspending_api_cache.json` becomes a plain file on the
SSD, which is strictly better: no cache-key churn, no eviction.

Note the phase-transition half of this workflow is already migrated
(`monthly_phase_transition`); only the benchmark job remains.

### 4. Monthly procurement transition report — diagnose before porting

| | |
|---|---|
| Was | `monthly-procurement-transition.yml` |
| Cron | `0 13 2 * *` |
| Runs | five scripts in sequence: `download_sam_opportunities.py` → `enrich_procurement_awards.py` → `hydrate_candidate_opportunity_descriptions.py` → `build_phase_iii_opportunity_candidates.py` → `monthly_procurement_transition_report.py --ai` |
| Secrets | `SAM_GOV_API_KEY`, `OPENAI_API_KEY` |
| Output | 90-day artifact: report dir, candidates/evidence parquet, cohort + coverage, opportunities parquet + hydration + raw ndjson |
| Target | Dagster job + schedule, after diagnosis |

**This has never succeeded.** Its only run (2026-08-02, run `30750087110`)
failed at "Download current public data" after 5 seconds. Five seconds is too
fast for a network timeout, which points at `curl --fail` receiving a non-200
from the SBIR bulk CSV endpoint, or `download_sam_opportunities.py` rejecting a
missing or expired `SAM_GOV_API_KEY` — SAM keys expire roughly every 60 days.
Reproduce on the host before writing any Dagster code.

Two simplifications the move makes available:

- The step curls `data.www.sbir.gov/…/award_data.csv` directly. On the mini,
  `sbir_awards_download_job` already fetches that CSV weekly. Consume that
  vintage instead of re-downloading, and the failing step disappears.
- The month-over-month diff uses `actions/cache` to carry
  `latest_awards.csv` forward as `previous_awards.csv`. On the SSD that is just
  two paths and a copy — no cache key, no chance of a silent restore-key miss
  producing a diff against the wrong month.

This is the most complex of the five. Given it has never produced output, treat
it as new work with a reference implementation rather than as a port.

### 5. Weekly image rebuild — lowest priority

| | |
|---|---|
| Was | `build-images.yml` |
| Cron | `0 4 * * 0` (Sunday) plus push-path triggers |
| Built | `python-base` (amd64 + arm64), `etl`, `full` → GHCR |
| Target | host cron, or nothing |

Last because it already degrades gracefully. `make server-up` falls back to
building `Dockerfile.python-base` locally when GHCR has no manifest for the
Mac's architecture (`mac-mini-server.md:139`), and the server compose profile
builds its app images locally with a `:local` tag rather than pulling. Nothing
is broken today; a first build just takes several minutes.

If you want the weekly refresh back, a host cron doing an arm64-only local
build is enough — the amd64 half of the multi-arch manifest existed to serve
CI, which no longer builds images. Accepting on-demand rebuilds when
dependencies change is also a defensible answer.

## Deliberately not migrated

Recorded so these are not resurrected by accident.

| Dropped | Why |
|---|---|
| Performance regression check | PR-scoped, gated on a baseline cached against a git ref. Meaningless outside CI, and it was `continue-on-error` so it blocked nothing. |
| Transition MVP gate | Already `workflow_dispatch`-only because runners cannot reach the bulk data. If the gate is wanted, the data is local on the mini and it becomes a Dagster job — but it was gating nothing in practice. |
| Container build + smoke, E2E docker job | Covered by `test-full` on `main`, which runs the whole suite against a real Neo4j. |
| PR test-summary comment, CI summary job | GitHub's own checks UI shows which job failed. |
| Weekly auto-repair chain | Never fired once in nine months — no `ci:triage` issue and no `bot/ci-fix/*` branch ever existed. `ruff --fix` is a pre-commit concern. |
| Markdown lint, setup-script verification, local/ML workflow verification, Neo4j smoke | Dev-environment smoke tests, not scheduled production work. Run them by hand when changing the relevant setup. |

## Sequencing

1. **Failure notification** (cross-cutting) — without it every step below can
   fail silently.
2. **Security scan** — the only true gap; cheapest to close.
3. **Weekly awards report** — simplest, proves the pattern end to end.
4. **Monthly benchmark** — diagnose the 60-second success first.
5. **Monthly procurement transition** — diagnose the download failure first;
   largest scope.
6. **Image rebuild** — optional; a working fallback already exists.

Steps 2 and 3 are independent and can proceed in parallel. Steps 4 and 5 both
start with a diagnosis that can happen before any code is written.

## Definition of done

- Each migrated workload has run successfully by hand on the host.
- Each has a `_HOST_SCHEDULES` entry and a runbook table row.
- Each writes durable dated output under `<data_root>`, not somewhere that
  expires.
- A failed run reaches a human without anyone opening the Dagster UI.
- Unused GitHub repository secrets are deleted.

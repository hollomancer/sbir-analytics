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
(`SBIR_ETL__DAGSTER__SCHEDULES__<NAME>_CRON` and
`SBIR_ETL__DAGSTER__SCHEDULES__<NAME>_ENABLED`) and
`default_status` **stopped**. Keep that default: the runbook requires an
operator to confirm a manual run on the host before enabling.

**Wrapping a script as a job** follows
`packages/sbir-analytics/sbir_analytics/assets/jobs/phase_transition_archive.py` — an `@op` that `subprocess.run`s the
script, logs the stderr tail and raises on a non-zero exit, composed into a
`@job`. None of the five scripts below are wrapped in Dagster yet, so each needs
this.

**Durable output** matters more than it did. Every retired workflow uploaded
GitHub artifacts with 7–90 day retention, and those expire. The phase-transition
archive already solves this by writing dated directories under
`<data_root>/processed/phase_transition/history/<date>/`. Each migration needs
an equivalent or its output series is lost.

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
needed by items 2 and 4. Item 3 needs none — the USAspending API is
unauthenticated. Once migrated, delete the now-unused repository
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
| Measured cost | **~37s of scan** — bandit 10.7s, detect-secrets 25.8s |
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

**It is cheap.** Measured on the current tree: bandit 10.7s, detect-secrets
25.8s, so about 37 seconds of actual work. A nightly cron costs nothing; there
is no argument for deferring this one on runtime grounds.

**It fails today.** `bandit -r sbir_etl packages -c pyproject.toml` currently
exits 1 with four findings — one High/High:

| Severity | Finding | Location |
|---|---|---|
| High / High | `B324` weak SHA1 hash | `assets/phase_iii_candidates/assets.py:243` |
| Medium | `B104` bind to all interfaces | `api/__main__.py:11` |
| Low ×2 | `B105` hardcoded password (`token-set`, `token-sort`) | `identity/company_names.py:49-50` |

The two Low hits look like false positives — they are algorithm names for a
token-matching strategy, not credentials. The B324 SHA1 is likely a content
hash rather than a security primitive and probably wants
`usedforsecurity=False`. Trivial to resolve, but resolve them *before* wiring
the cron, or the first run fails and gets muted, which is how the previous
scan ended up ignored.

Verify: after fixing, introduce a known finding (a hardcoded test credential on
a scratch branch), confirm the scan reports it and the failure reaches you.

### 2. Weekly awards report — DONE

| | |
|---|---|
| Was | `weekly.yml` · `weekly-awards-report` job |
| Now | `weekly_awards_report_job` / `weekly_awards_report` schedule, Monday 12:00 UTC |
| Secrets | `OPENAI_API_KEY`, `SAM_GOV_API_KEY` in `.env.server` |
| Output | `<data_root>/reports/weekly_awards/<date>/weekly-awards.md` |

Migrated in this PR, and the first exercise of the pattern end to end: one op
shelling out to `scripts/data/weekly_awards_report.py`, one `@job`, one
`_HOST_SCHEDULES` entry inheriting the workflow's Monday 12:00 UTC slot,
default **STOPPED**.

The report now lands in a dated directory instead of a 30-day artifact, so the
weekly series accumulates. The op treats an exit-0 run that wrote nothing as a
failure: the script can succeed while producing no report, and trusting its
exit code would reproduce exactly the silent-rot failure mode this whole
migration is trying to avoid.

Lookback defaults to 7 days, overridable with
`SBIR_ETL__REPORTS__WEEKLY_AWARDS_DAYS` for a backfill.

**Executed, not just unit-tested.** Running the job for real surfaced an
undeclared prerequisite: it resolves the SBIR awards CSV from disk and fails
with `FileNotFoundError` when no vintage exists. The crons already order this
correctly — `weekly_sbir_awards_download` at Monday 09:00 UTC, the report at
12:00 — but both default to STOPPED, so enabling the report alone fails every
week. Recorded in the runbook. The failure was loud and wrote no partial
report, which is the error handling behaving as designed.

**Remaining operator step:** run it by hand on the host, confirm the report
matches a recent Actions artifact for the same window, then set
`SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_AWARDS_REPORT_ENABLED=true`.

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

### 5. Docker image generation — build validation DONE, publishing optional

| | |
|---|---|
| Was | `build-images.yml` (Sunday 04:00 + push paths) and `ci.yml`'s container-build-test |
| Built | `python-base` (amd64 + arm64), `etl`, `full` → GHCR; plus a compose smoke test |
| Target | **split**: a path-filtered CI job for validation, the mini for the images it runs |

These two concerns got deleted together, and they should not be restored
together, because they were never the same thing.

**Publishing is genuinely optional.** `make server-up` falls back to building
`Dockerfile.python-base` locally when GHCR has no manifest for the Mac's
architecture (see [Bring-up](mac-mini-server.md#bring-up)), and the server compose profile builds
its app images locally with a `:local` tag rather than pulling. Nothing is
broken today; a first build just takes several minutes. The amd64 half of the
multi-arch manifest existed to serve CI, which no longer builds images — so if
the weekly refresh comes back at all, an arm64-only local build on the mini is
enough.

**Validation is not optional, and is currently missing.** With no image build
anywhere, nothing checks that `Dockerfile`, `Dockerfile.python-base`,
`Dockerfile.full`, or the compose files still work. A broken Dockerfile is now
discovered at deploy time on the mini, which is the worst place to find it.
`tests/` cannot cover this: the ETL image is what the tests would run *inside*.

**Implemented in this PR:** a **path-filtered `docker` job in `ci.yml`**, gated on
`Dockerfile*`, `docker-compose*.yml`, `.dockerignore`, `uv.lock` and
`pyproject.toml`. It costs nothing on a typical PR — it does not run at all —
and fires exactly when a change could break the build. Scope it to build and
smoke-test, not publish:

- `docker build` the ETL image (amd64, the runner's native arch — the point is
  catching a broken Dockerfile, and arm64 emulation triples the time for no
  extra signal)
- run `dagster --version` in it, the smoke test the old job used
- `docker compose --profile ci config -q` to validate the compose files

That is roughly a 5–10 minute job that runs on a handful of PRs a month. It
keeps the "GitHub Actions is tests only" line honest — it is a test, of the
build — without restoring a 20-minute job on every merge.

The alternative, building on the mini via cron, catches the same breakage but
only after it lands on `main`, and only on arm64. Worth doing *as well* if you
want the arm64 path covered, but it is not a substitute for a pre-merge gate.

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
3. ~~**Weekly awards report**~~ — done; only the operator enable step remains.
4. **Monthly benchmark** — diagnose the 60-second success first.
5. **Monthly procurement transition** — diagnose the download failure first;
   largest scope.
6. ~~**Docker image generation**~~ — build validation restored as a
   path-filtered CI job. Publishing stays optional and unscheduled.

Steps 2 and 3 are independent and can proceed in parallel. Steps 4 and 5 both
start with a diagnosis that can happen before any code is written.

## Definition of done

- Each migrated workload has run successfully by hand on the host.
- Each has a `_HOST_SCHEDULES` entry and a runbook table row.
- Each writes durable dated output under `<data_root>`, not somewhere that
  expires.
- A failed run reaches a human without anyone opening the Dagster UI.
- Unused GitHub repository secrets are deleted.

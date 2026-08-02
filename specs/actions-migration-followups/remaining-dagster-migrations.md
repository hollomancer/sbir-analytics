# Remaining Dagster migrations

Tracking stub. Finishes the Dagster half of
[the Actions migration plan](../deployment/actions-migration-plan.md); nothing
here is implemented yet.

## 1. Weekly awards report — enable it

The job and schedule already exist (`weekly_awards_report_job` /
`weekly_awards_report`, Monday 12:00 UTC, default STOPPED). What remains is
operational, not code:

- [ ] Run it by hand on the mini and confirm it produces a report
- [ ] **Enable `weekly_sbir_awards_download` first.** Executing the job proved
      it resolves the SBIR awards CSV from disk and raises `FileNotFoundError`
      when no vintage exists. The crons order this correctly (download 09:00,
      report 12:00) but both default to STOPPED, so enabling the report alone
      fails every Monday.
- [ ] Compare output against a recent Actions artifact for the same window
- [ ] Set `SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_AWARDS_REPORT_ENABLED=true`

Consider whether a run-status sensor (as `sbir_pipeline_after_download` does)
is better than relying on cron spacing.

## 2. Monthly benchmark evaluation — diagnose first

Was `monthly-analysis.yml` · `benchmark`, cron `0 6 1 * *`, running
`scripts/data/run_benchmark_analysis.py` then `scripts/ci/benchmark_summary.py`.

**Do not port as-is.** Every month since May the workflow showed a ~30s
`failure` around 06:50 UTC followed by a ~60s `success` — against a step that
budgets 90 minutes. A benchmark finishing in 60s is not doing the work the
timeout implies.

- [ ] Pull a recent `run_manifest.json` / `benchmark_evaluation.json` artifact
      **before the 30-day retention expires** and establish what the successful
      runs actually produced
- [ ] Decide what the job should compute, then wrap it
- [ ] `_HOST_SCHEDULES` entry, default STOPPED, keeping `0 6 1 * *`
- [ ] Dated durable output under `<data_root>` (artifacts expired; this becomes
      the only copy)
- [ ] The `usaspending_api_cache.json` `actions/cache` becomes a plain SSD file

## 3. Monthly procurement transition report — diagnose first

Was `monthly-procurement-transition.yml`, cron `0 13 2 * *`, chaining five
scripts. Needs `SAM_GOV_API_KEY` and `OPENAI_API_KEY`.

**It has never succeeded.** Its only run (`30750087110`) died 5s into "Download
current public data" — too fast for a network timeout, pointing at a non-200
from the SBIR bulk CSV endpoint or an expired SAM key.

- [ ] Reproduce the download failure on the host
- [ ] **Drop the redundant `curl`** — `sbir_awards_download_job` already fetches
      that CSV weekly; consume the vintage instead and the failing step
      disappears
- [ ] Replace the `actions/cache` month-over-month diff with two SSD paths
- [ ] Wrap, schedule (default STOPPED), dated durable output
- [ ] Treat as new work with a reference implementation, not a port

## Cross-cutting, blocks all three

- [ ] **Failure notification.** A stopped-by-default schedule on a tailnet-only
      host tells nobody when it breaks. This is the failure mode that kept
      `weekly.yml` dead and unnoticed. Decide the path (run-failure sensor →
      email/Slack/ntfy) before enabling anything.

# Jev CI Enforcement Design

**Status:** active exploratory CI application

## Decision

Add a deterministic contract-drift job as a stacked application of Jev Preflight.
The job compares current annual-report decisions with a reviewed policy. It does
not call Jev.

```text
relevant pull-request paths
            |
            v
  annual-report adapter + deterministic rules
            |
            v
     committed CI policy
            |
            v
 stable report + pass/fail exit code
```

## Policy boundary

Store the policy at `specs/jev-ci-enforcement/policy.yaml`. The policy pins the
ruleset, case IDs, readiness status, and first blocker. Require complete coverage
of the annual-report claim registry. A new claim therefore fails until a reviewer
classifies its expected deterministic outcome.

An expected `NARROW` or `STOP` is not a waiver. It freezes a known refusal. A
change to `GO` also fails until the policy changes, because removing a blocker is
an evidence decision that requires review.

## CI boundary

Use the existing `detect-changes` job to select the check. Run a separate job so
the repository can require or inspect it independently. Do not add credentials.
Do not make a live request. Upload the JSON report with `if: always()`.

The job covers:

- `studies/sba-annual-report-tables/**`
- `scripts/jev_preflight/**`
- `scripts/data/sba_annual_report_tables.py`
- `scripts/ci/validate_study_manifests.py`
- `sbir_etl/config/yaml_io.py`
- `sbir_etl/quality/study_manifest.py`
- `specs/jev-preflight/**`
- `specs/jev-ci-enforcement/**`
- the focused preflight and enforcement tests
- the Make target, CI workflow, and dependency metadata

## Failure behavior

Validation errors, adapter errors, policy drift, status drift, blocker drift, and
claim-coverage drift return a non-zero status. The command writes a report for
policy comparisons. Errors that prevent any valid comparison remain visible in
the job log and fail closed.

## Citability

The report is exploratory and non-citable. A pass means only that the configured
deterministic decisions match the reviewed policy under the pinned ruleset.

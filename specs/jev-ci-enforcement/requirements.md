# Jev CI Enforcement Requirements

**Research question anchor:** A1 / D1 — annual-report portfolio composition and award totals
**Target epistemic tier:** `exploratory`
**Operational duty:** Detect unreviewed drift in configured study-readiness decisions.
**Status:** active
**Out of scope:** Live Jev calls; prose scanning; evidence promotion; merge approval; repository-wide study coverage.

## Done when

A pull request that changes the annual-report study or its preflight implementation
runs the deterministic readiness contracts. CI fails when a configured claim changes
status or first blocker without an explicit policy update. CI publishes an inspectable,
non-citable report for every executed check.

## Requirements

### Requirement 1 — Versioned enforcement policy

1. THE policy SHALL name the deterministic ruleset it expects.
2. THE policy SHALL list every configured claim exactly once.
3. EACH claim SHALL declare its expected readiness status and first blocker.
4. THE policy SHALL reject unknown fields, duplicate claims, and unknown claims.
5. THE check SHALL fail when a configured claim is missing from the study adapter.

### Requirement 2 — Deterministic failure behavior

1. THE check SHALL run without a TypeSafe API key or network access.
2. THE check SHALL fail when the active ruleset differs from the policy.
3. THE check SHALL fail when a claim status differs from policy.
4. THE check SHALL fail when a claim first blocker differs from policy.
5. THE check SHALL fail when the adapter cannot validate its frozen inputs.
6. THE check SHALL not treat Jev output as authoritative evidence.

### Requirement 3 — Changed-file scope

1. THE pull-request job SHALL run only for changes to the annual-report study,
   preflight implementation, enforcement policy, relevant tests, or workflow.
2. THE local command SHALL run the same check without changed-file detection.
3. Changes outside the declared path set SHALL not invoke the pull-request job.

### Requirement 4 — Inspectable output

1. THE check SHALL write a stable JSON report before returning failure.
2. THE report SHALL identify every observed and expected decision.
3. THE report SHALL list policy violations by case ID.
4. THE report SHALL label itself exploratory and non-citable.
5. CI SHALL upload the report when the job runs, including on failure.

## Explicit exclusions

- No `TYPESAFE_API_KEY` secret in GitHub Actions.
- No request to the TypeSafe API from CI.
- No generated reasoning or repository summary.
- No automatic policy rewrite when a decision changes.
- No claim that a passing check approves a study or publication.
- No enforcement for studies without a named adapter and policy.

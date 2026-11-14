# Jev Preflight Design

**Status:** active exploratory vertical slice

## Decision

Build the first product as deterministic study governance with an optional Jev
shadow. Put the implementation under `scripts/jev_preflight/`. Do not add it to
`sbir_etl`, because the result is exploratory and probabilistic model output is
not pipeline evidence.

```text
claim contract + validated study manifest + sources manifest
                            |
                            v
               deterministic evidence facts
                            |
                            v
              deterministic readiness engine
                    |               |
                    v               v
          authoritative result   optional Jev request
                                         |
                                         v
                               private shadow comparison
```

## First study application

The adapter reads `studies/sba-annual-report-tables/study.yaml` and
`sources.yaml`. It exposes two claims:

1. `published-sample-reproduction`: The current export reproduces the
   publication-era tables. This requires a surviving report-era vintage.
2. `current-snapshot-structural-check`: The pinned current export can rerun the
   declared structural comparison. This requires valid frozen artifacts and a
   reproducible study contract. It does not require a report-era vintage.

The first claim returns `NARROW`, not `STOP`, because the study manifest already
permits the second claim. The adapter cites the exact contract fields supporting
that decision. It does not infer a new permitted claim.

## Validation and rule precedence

Validate every required claim dimension before policy runs. Treat a missing or
blank dimension as invalid input, not as a readiness result.

For a valid contract, evaluate blockers in this order:

1. Unavailable required source outcome. Evaluate permanent impossibility before
   a remediable source gap.
2. Unpinned required input.
3. Missing required definition.
4. Incomplete required validation.
5. Target evidence status above the study's current status.

This order is versioned as `preflight-rules-v1`. The engine returns one first
blocker and retains all matched constraints for inspection.

## Evidence labels

- `OBSERVED`: read directly from a validated repository artifact.
- `INFERRED`: depends on a declared interpretation or model.
- `UNSUPPORTED`: a required fact is absent.
- `BLOCKED`: an explicit repository gate prevents the claim.

## Jev shadow

Send one Choice question for readiness, one Choice question for the first
blocker, and atomic Noul questions for individual facts. Code compares the typed
response with the deterministic result. It does not ask Jev to generate an
explanation. The request uses the documented `/v1/systemone` endpoint and
`jev-latest` model alias.

The live output goes to an operator-selected path outside the repository by
default. Tests use a fake transport. CI makes no TypeSafe request.

## Citability

The implementation and all evaluation outputs are exploratory and non-citable.
The preflight result reports existing study status; it cannot promote that
status. A `GO` result means only that no configured blocker was found under the
named ruleset.

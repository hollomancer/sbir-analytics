# SBIR ROI Comparative Tests Design

## Boundary

Keep the work in `exploratory` status.
Do not add Dagster assets, scheduled jobs, external uploads, or live-source reads.

## Components

`contracts.yaml` owns comparator, outcome, attribution, and welfare-ledger definitions.
`sbir_roi_contracts.py` validates the shared bundle.
Each study directory owns one estimand, design, identity policy, and materialization gate.

## Evidence flow

The identification bridge can supply causal weights for supported populations.
Test Two compares SBIR with mechanism-matched federal research programs.
Test Three converts identified and linked benefits into a break-even attribution threshold.

Context-only analogues can explain design choices.
They cannot establish a relative return ranking.

## Failure behavior

Reject unknown contract fields.
Reject duplicate identifiers.
Reject missing evidence classes.
Reject invalid attribution weights.
Reject patents as standalone success.
Keep every study closed until its listed blockers are removed through a later amendment.

## Promotion

This PR does not promote evidence.
A later PR must pin inputs, implementation, parameters, and validation design.
That PR must update each manifest and record the change in an amendment log.

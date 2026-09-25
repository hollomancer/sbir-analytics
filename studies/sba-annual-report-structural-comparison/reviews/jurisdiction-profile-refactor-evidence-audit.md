# Jurisdiction-profile refactor evidence audit

**Date:** 2026-09-21
**Reviewer:** `sba_profile_refactor_audit`, project evidence-auditor role
**Verdict:** `GO WITH REQUIRED CHANGES`

The auditor authorized the existing `validated` result to remain in force after
the producer moved its exact jurisdiction map to the versioned
`SBA_ANNUAL_REPORT_TABLE_V1` shared profile. A new prospective validation run
is not required.

The auditor verified:

- exact equivalence for all 53 prior name/code pairs;
- no expanded input domain;
- current producer SHA-256
  `bff52a594e4d77a2094c584e59365d4fd8be7dc381f2029246927fdebec5445a`;
- current geography primitive SHA-256
  `b2961c8f77086d3fb33e5f3e8fdce22a56da60004883d274c8431c1fcae00280`;
- byte-identical regeneration of all 632 cells at SHA-256
  `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`;
- exact reconciliation of all 1,264 confirmatory operands; and
- passing focused tests and identity, tier, and manifest guards.

The estimand, population, threshold, claims, non-claims, and numerical result
do not change. Producer provenance in the public JSON and Markdown does change.
The auditor therefore required regeneration, frozen new public hashes, a clean
reproduction replay, and a fresh cold named-reader review of that exact
snapshot.

This audit did not authorize citable status, materialization, merge,
publication, release, tagging, or a broader claim.

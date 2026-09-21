# SBA Structural Comparison — Freeze and Amendment Record

## Revision 0 — 2026-09-21 — candidate design created

**Status:** Candidate only. This revision does not authorize an evaluated run.

The blank population and prospective fidelity design were committed together at
Git commit `72695b18853b82a5efe66350ad9f416a9eea18f1`. No filled independent
extraction or validation result existed at that commit.

The candidate population contains 1,264 unique operands. It contains 632
`published_count` operands and 632 `recomputed_count` operands. The base keys
contain 53 jurisdictions for FY2020, 53 for FY2021, and 52 for FY2022. Each
jurisdiction has four program-phase cells.

The following results were visible before this candidate existed. They are
post-hoc context. They do not set a validation threshold:

- The historical exploratory comparison reported FY2020 `+179` counts
  (`+2.51%`).
- It reported FY2021 `+98` counts (`+1.44%`).
- It reported FY2022 `+56` counts (`+0.85%`).
- It reported 632 cell comparisons and a post-hoc tolerance-band verdict.
- It assigned 534 cells to `revised_upstream` without cell-specific evidence.
- It used dollar differences in some count-cell classifications.
- An eight-year extension showed that the three-year band was not a safe
  general rule and excluded FY2014 for an unresolved basis.

None of those verdicts or classifications is permitted in the citable product.

## Pre-run evidence audit — 2026-09-21

**Auditor:** Dalton, evidence-auditor role

**Verdict:** Go with required changes.

The auditor accepted the complete-population fidelity target and rejected an
evaluated run from the candidate unchanged. The required changes were:

1. Add durable exact-byte acquisition and a frozen source manifest.
2. Separate this product from the blocked historical reproduction study.
3. Freeze the final count-only producer and sidecar before extraction.
4. Remove post-hoc bands and unsupported causal classifications.
5. Name all 632 printed count cells as the estimand.
6. Make blinding operational with named, separate roles.
7. Define the submission schema, abort rules, and point interval.
8. Add fail-closed evidence gates and arithmetic checks.
9. Record formal approval and final hashes before extraction.

`validation-design-v1.md` was revised to include these requirements. The
`source-manifest.json` now names clean, exact-byte acquisition routes for all
four source files. The evaluated run remains prohibited until Revision 1 is
complete.

## Revision 1 — pending formal freeze

Do not complete this section until every preflight gate passes.

- Approver: pending
- Approval time: pending
- Git anchor: pending
- Coordinator: pending
- Independent extractor: pending
- Design SHA-256: pending
- Population SHA-256: pending
- Source manifest SHA-256: pending
- Production implementation SHA-256: pending
- Production sidecar SHA-256: pending
- Environment lock SHA-256: pending
- Blind packet SHA-256: pending
- Prior results visible at approval: Revision 0 list above
- Permitted claim after a confirmatory pass: pending exact text
- Required adjacent non-claims: pending exact text

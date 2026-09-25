---
Type: Study protocol (frozen before capture)
Study-ID: sba-annual-report-tables
Roadmap-Order: 1
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-17
Status: gate not yet satisfied — source capture outstanding
---

# Study 1 protocol — SBA SBIR/STTR annual-report tables

Order 1 of the [literature replication roadmap](../../docs/research/literature-replication-roadmap.md).
Replicates the published tables of the SBA SBIR/STTR Annual Reports **[L18]**, serving inventory
questions **A1** and **D1**.

This protocol is written **before** capture, as the completion standard requires. It is the frozen
contract; deviations are recorded in `amendments.md`, not by editing this file.

## Why this study is first

It is a direct grouping of public award records. It needs no entity resolution, no SBIR/STTR
classifier, no patent linkage, and no causal identification. Every input is either a published
table or the award record set the pipeline already holds.

## Estimand

Reproduce, cell for cell, the published counts and award dollars cross-tabulated by **agency**,
**state**, **phase**, **fiscal year**, and **first-time-winner status**, as printed in the selected
SBA annual report.

This is a reproduction of published administrative tables. It is **not** an estimate of program
effect, not a measure of commercialization, and not a corrected or improved version of the SBA
figures. Where this pipeline and the report disagree, the deliverable is the explained difference,
not a preferred number.

## Two separate products

Per the roadmap, these are reported separately and never merged:

1. **Published-sample replication** — the report's own period, cohort, definitions, and *source
   vintage*. Reproduces the printed tables.
2. **Current-data extension** — the identical, unchanged code applied to a newer pinned award cut.
   Runs only after (1) reconciles. Not a replication and never labelled as one.

## Report selection rule

Select the most recent annual report **whose underlying source export can be recovered** —
recoverability governs, not recency. [L18] names FY20, FY21, and FY22. Record the selection and the
reason in `sources.yaml`.

## Definitions to recover verbatim before any computation

Capture each of these from the report text itself, quoted verbatim into
`sources.yaml:definition_verbatim`. Every one is a known divergence source:

- **Fiscal-year assignment** — award date, obligation date, or report year.
- **STTR treatment** — combined with SBIR, reported separately, or both.
- **Amendments and modifications** — counted as distinct awards or folded into the parent.
- **Zero-dollar and negative records** — included, excluded, or netted.
- **Phase labels** — Phase I / II / III, and the handling of Phase IIB and similar sub-phases.
- **Agency attribution** — funding agency versus component, and where components roll up.
- **State attribution** — firm address of record, performance site, or HQ, and the vintage of that
  address.
- **First-time-winner definition** — and, critically, the **history window** used to establish that
  a firm is new.
- **Dollar basis** — obligated versus awarded amount; nominal or adjusted.

## First-time-winner left-censoring

The first-time-winner share is the most fragile cell in the report. A firm can only be called new
relative to a lookback window. If the recoverable award history is shorter than the report's own
window, the statistic is **left-censored** and must be reported as a bound, with the available
history length stated, not as a point estimate.

## Blocking checks

These run before any cell comparison and fail the study rather than producing numbers:

- identifier integrity (no null or duplicate award identifiers at the declared grain);
- declared grain matches the table's row grain;
- row counts reconcile to the source ledger;
- no duplicate-join fan-out on any enrichment;
- denominator integrity — every total equals the sum of its published parts.

## Cell comparison and difference classification

Compare **every** published cell against the recomputed value. Classify each non-match as exactly
one of:

| Class | Meaning | Resolution |
| --- | --- | --- |
| `rounding` | Within the report's declared rounding tolerance | Accept, record tolerance |
| `revised_upstream` | Source record changed after the report was printed | Accept, record vintage delta |
| `definition_mismatch` | Our rule differs from the recovered definition | Fix our rule, re-run |
| `pipeline_defect` | Our implementation is wrong | Fix, re-run, note in amendments |

Unexplained differences are not a category. An unclassified cell keeps the study out of
`reproduced`.

## Outcome vocabulary

Exactly one of: **`reproduced`**, **`diverged with explanation`**, or **`blocked`**. Divergence is a
legitimate result. Tuning definitions to reach agreement with the published number is not — the
prohibition in the roadmap's Study 3 (do not tune to reach 4:1) applies here equally.

## Done when

- every published cell matches within its declared rounding tolerance, or carries a row-level
  explanation classified above;
- the cohort-flow table, source-coverage report, and benchmark reconciliation rebuild from the
  declared inputs;
- the manifest's pinned inputs and outputs reproduce the deliverable;
- the current-data extension, if run, is reported in a separate directory with separate claims.

## Known risk: source-vintage recoverability

**This is the study's principal threat, and it is not yet resolved.**

A published-sample replication requires the award records *as they stood when the report was
printed*. SBIR.gov's award data is refreshed in place, so an FY22-vintage export may no longer be
retrievable. The award snapshot currently in this repository
(`data/raw/sbir/award_data.csv`, retrieved 2026-05-11) is a **later** vintage than any report named
in [L18].

Consequences, stated in advance so the outcome is not rationalised after the fact:

- If no report-era vintage is recoverable, the honest outcome for the published-sample replication
  is **`blocked`**, and only the current-data extension can proceed.
- Substituting the May-2026 snapshot for the report vintage and calling the result a replication is
  precisely the proxy substitution the roadmap prohibits. Differences would be
  uninterpretable — indistinguishable between `revised_upstream` and `pipeline_defect`.
- A mixed path is acceptable **if labelled**: reproduce table *structure* and definitions against
  the current snapshot, report it as a structural check, and keep the `blocked` verdict on the
  published-sample cells.

## Deferred: `study.yaml` manifest

No manifest is committed yet, deliberately. `StudyManifest` requires at least one
`implementation` entry whose symbol CI resolves, plus `frozen_artifacts` with verified SHA-256
hashes. Both presuppose code and captured sources that do not yet exist. The manifest lands with
the implementation, registering this protocol as a frozen artifact at that point.

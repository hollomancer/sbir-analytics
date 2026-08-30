# SBIR M&A Dated Signal Study — Design

## Decision

This is a prospective, **exploratory** pre-run protocol for a new study. Its
planned as-of cutoff is **2026-08-29 UTC**. It neither restores nor compares
against the unrecoverable April 2026 snapshot: historic award counts, event
totals, match percentages, and their source files are excluded from every
future input and verification step.

The currently authorized flow permits one private, raw SBIR.gov firm-frame
retrieval under [Amendment 1](amendments.md#amendment-1--private-first-source-acquisition-authorization).
It remains intentionally closed to analysis and materialization:

```text
pre-run protocol + Amendment 1 + empty exploratory notebook + closed study gate
    -> private retrieval of official SBIR.gov award CSV only
    -> record private provenance and explicit cutoff check
    -> await separate authorization for every later source and all materialization
```

## Prospective run contract

Before any source retrieval, an amendment must be committed and reviewed. It
must identify:

1. the SBIR firm-frame source, its coverage, extraction method, and inclusion
   and exclusion rules;
2. every candidate M&A-signal source, its permitted use/license and collection
   timestamps, and its known coverage limitations through the planned cutoff;
3. source byte hashes, byte sizes, record counts, schema versions, and an
   immutable local manifest;
4. a candidate-level audit table with source IDs/URLs, observed dates, identity
   rationale, alias handling, duplicate/deal rules, exclusion reasons, and
   source-specific uncertainty; and
5. a declared descriptive estimand before aggregation.

An unavailable, incomplete, or post-cutoff-only source is a failed precondition,
not permission to substitute a nearby vintage or to infer missing observations.
Amendment 1 authorizes only the stated SBIR.gov retrieval; no other network
acquisition is authorized by this document.

## Identity and observation boundary

The future unit may only be declared after the firm frame and source schemas
are reviewed. Candidate matches retain raw names and stable source identifiers;
normalization can generate candidates but cannot independently establish a
firm, a transaction, or a completed acquisition. Candidate events must retain
the source-observed date and distinguish that date from announcement, signing,
and closing dates when known.

The prospective utility `scripts/data/sbir_ma_signal_counts_by_fy.py` may be
considered only after the source contract is approved. Its historic JSONL
contract is a signal-observation diagnostic, not a source-acquisition path and
not an exit-rate implementation.

## Validation and promotion runway

The notebook and manifest remain exploratory/non-citable. Before a result
leaves the repository as a numerical claim, a distinct evidence-tier promotion
must complete all of the following:

| Gate | Required proof |
|---|---|
| Frozen protocol | Pre-run design and amendments fixed at recorded content hashes. |
| Input integrity | SHA-256, sizes, record counts, schemas, and output hash enforced at materialization. |
| Blocking checks | Source cutoff, schema, uniqueness, provenance, and reconciliation failures stop publication. |
| Estimand | A written quantity, denominator, observation window, and explicit failure modes. |
| Human validation | Blinded independent adjudication, sample design, error estimates where applicable, and documented disagreement resolution. |
| Claim review | Privacy/license clearance and independent human methods review approve exact permitted language. |

Only a later manifest promoted through `reproducible`, `validated`, and
`citable` as its verified evidence warrants may authorize external numerical
claims. A signal count does not become an acquisition, exit, incidence,
agency-effect, comparator, vintage-adjusted, or survival result by promotion
alone; each needs its own declared estimand and validation.

## Explicit exclusions

This protocol excludes discovery/search services, LLM extraction, source
reconstruction, vintage adjustment, survival analysis, external comparators,
agency-specific comparisons or causal attribution, public datasets, and live
Dagster operations. It does not modify the historical M&A specifications.

## Verification

This documentation slice is complete when the requirements, design, task list,
study manifest, and cleared notebook agree on the cutoff, closed gate,
exploratory tier, non-citability, conditional acquisition, and exclusions.
`make docs-check` and `scripts/ci/validate_study_manifests.py` must pass.

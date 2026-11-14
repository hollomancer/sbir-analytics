# SBA Annual-Report Structural Comparison Release — Design

## Decision

Treat the first public product as a descriptive structural comparison. Validate
the fidelity of source capture, transcription, and transformation. Do not
validate the observed source agreement with bands chosen after those results
were known.

## Candidate public claim

> For FY2020-FY2022, this study compares selected SBA Annual Report award-count
> cells with counts computed from the exact September 17, 2026 SBIR.gov export
> under declared row, year, and jurisdiction rules. The released tables report
> the observed differences. They do not reproduce the publication-era source,
> establish official-report equivalence, or compare award dollars.

This wording is a draft. It is not approved until the evidence-approval gates close.

## Validation design decision

Before any new validation extraction, choose and freeze one of these designs:

1. An independent second extraction of the report count cells and study rules,
   performed by a reviewer who does not use the implementation output.
2. A frozen untouched subset of eligible report cells, transcribed and checked
   only after the design is committed.

The design must define the addressable population, expected error rate,
decision threshold, threshold derivation, reconciliation method, and treatment
of missing cells. It must have power to detect a meaningful transcription or
transformation defect. Existing comparison outputs cannot select the threshold.

## Comparison behavior

The study-owned comparison code emits mechanical facts:

- report count;
- export-derived count;
- signed and absolute count difference;
- declared rule and source references;
- direct mismatch evidence, when available; and
- `unresolved` otherwise.

`revised_upstream` requires row-level or source-version evidence. Being inside a
band is not that evidence. Dollar values can be displayed with an incomparable
basis label, but they cannot classify a count cell.

## Artifact flow

```text
verified source inputs + frozen study contract
                    |
                    v
study-owned comparison producer
                    |
                    v
machine-readable result + deterministic sidecar
                    |
                    v
public renderer
                    |
                    v
round-trip, mutation, audit, and reader-review checks
```

The renderer reads only generated results and frozen explanatory text. It does
not recalculate data or contain hand-entered findings.

The source acquisition record covers the 2026-09-17 export and the FY2020,
FY2021, and FY2022 report PDFs. A release asset or upstream object version is
acceptable only when a clean replay verifies its frozen SHA-256 and byte count.
An ordinary mutable URL is not sufficient.

## Gate reconciliation

The current study correctly blocks a published-sample reproduction claim. A
future amendment may authorize a separate descriptive structural-comparison
product while leaving that blocker permanent. It may not relabel the existing
blocked outcome as achieved.

## Release and approval boundaries

An immutable release packet is the object a reader cites. The study manifest's
`approved` rank independently records whether the repository authorizes its
bounded substantive claims. Operational materialization and repository-owner
merge authority are separate controls. The moving repository remains a
research instrument with mixed-status work. Graph data, exploratory notebooks,
and unrelated studies are outside the packet.

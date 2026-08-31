# Form D Amendment-Chain Deduplication — Design

## Data flow

```text
Form D filings → accession-grain normalized rows → versioned chain resolver
                                               ↘ resolution audit
                    resolved series → one as-of representative → monetary aggregate
                    unresolved rows ───────────────────────────→ excluded/audited
```

The accession-grain table remains canonical. Chain and firm aggregates are derived outputs with
their own grain and policy version.

## Chain identity

Implementation begins with an audit of SEC XML fields and known original/amendment sequences. Use
an explicit predecessor or offering identifier if the source exposes one. Any fallback key must be
documented, deterministic, and tested against collisions; plausible-but-ambiguous candidates stay
unresolved. Issuer name alone is never a chain key.

Candidate fallback components may include issuer CIK, date of first sale, exemption, security
types, and stable offering attributes, but the implementation may only adopt them after the audit
shows the collision and missingness behavior. The named chain-policy version makes later rule
changes explicit.

## Representative selection

Within a resolved series and declared as-of cut:

1. order filings by valid filing date and accession tie-break;
2. select the latest valid filing representing cumulative progress;
3. retain its reported `total_amount_sold` as the series amount;
4. retain earlier accessions as lineage, not additive dollars.

Conflicting same-day records, decreasing/restated values, and orphan amendments are surfaced in
checks. A decrease is not silently rewritten; the latest disclosed amount and audit flag are both
preserved when the chain itself is unambiguous.

## Consumer migration

`agency_private_capital` inputs, capital-event summaries, and bootstrap leverage code must consume
resolved series amounts rather than summing offering rows. Participation outputs may continue to
use accession-grain filings if their names state that grain. Legacy dollar artifacts are not
relabelled as chain-resolved.

## Testing strategy

- Original plus two cumulative amendments (5, 8, 10) produces 10, not 23.
- Two independent resolved offerings produce the sum of two representatives.
- Orphan and ambiguous amendments are excluded with reasons.
- Duplicate-accession conflict fails closed.
- As-of cut selects the latest filing available by that date.

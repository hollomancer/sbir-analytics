# Phase III negative-control identity eligibility audit — August 3, 2026

## Interpretation boundary

This is a source-completeness gate run before construction of the SAM control frame. It
contains no control candidates, matching result, census outcome, balance statistic,
criteria distribution, overlap coefficient, or placebo result. Passing this gate means
only that every still-unresolved SBIR/STTR source row can conservatively quarantine an
exactly colliding control candidate under frozen Revision 11.

## Frozen gate

Revision 11 was committed as `ace76058` before quarantine-key availability was computed
from the real source. Every final non-`resolved_authoritative` award must have a complete
normalized company-name-plus-state key, a complete normalized address-plus-five-digit-ZIP
key, or both. One row with neither key stops the study; there is no allowable missing
share or percentage threshold.

## Source continuity and provenance

The original 207,826,925-byte February processed SBIR.gov parquet was no longer present
locally. Its materialization record pins the artifact at SHA-256
`b46c552f26a9de9ff70bb63f08880a38d9e4d4413c33d23c3e539f4316e1421f` and the raw
42-field CSV at SHA-256
`1c4c8b7d7b0928021699722c43bae97d8e2d79d2723857179e7a160255e573db`.

The official SBIR.gov bulk file retrieved on August 3 was materialized with the identical
42-field source-row algorithm. The later raw file has SHA-256
`efdf7ca5a398703002ebb33345275b0f68e50af3c5db361d48a2456266a23628`; its processed
parquet has SHA-256
`5a1bc980bcbf0bbdf49b0f397589ab13647618b0b58da46d12146205761c0f09`. Because these
digests differ from the February inputs, the later file was not treated as the February
artifact. Instead, it supplied source fields only for rows whose complete 42-field
`source_row_sha256` exactly matched the retained February recovery audit.

All 37,477 identifier-poor recovery-audit fingerprints matched exactly and uniquely; zero
were absent. Thus the company, state, address, and ZIP values used below are the same
source-row values hashed in February, not values joined by award number or company name.
The final recovery audit used below has SHA-256
`c4c0efa9941205207da78e7bee9fe54a2582e4124dcdfb8b77cd4d1eeb7a8ac7`.

## Complete unresolved-row key coverage

| Key availability | Unresolved source rows |
|---|---:|
| Both name+state and address+ZIP | 32,952 |
| Name+state only | 110 |
| Address+ZIP only | 0 |
| Neither | 0 |
| **Total unresolved** | **33,062** |

The persisted row audit has SHA-256
`29e24a7e9119a5162cd4e4db647c66bf91e1b918806712b7b019c7094fd6fb11`; the four-row
coverage table has SHA-256
`7fd4b8cb2cb4c5952bfed465e7d73ab2d9f9c46393b28ed8bf48ca9386f90d52`.

## Gate disposition

The Revision 11 gate passes. Under the frozen eligibility protocol, **zero additional
award-identifier resolutions are required for unresolved-award quarantine completeness**.
This does not reclassify any of the 33,062 unresolved rows as identified, and it does not
make a name or address an identity link. Those rows remain unresolved and can only exclude
an exactly colliding candidate from the screened-negative pool.

The next authorized step is to construct the SAM candidate identity envelopes, exclude
exact UEI/DUNS intersections and exact unresolved-row quarantine collisions, and report all
three eligibility statuses before any matching or arm outcome is computed.

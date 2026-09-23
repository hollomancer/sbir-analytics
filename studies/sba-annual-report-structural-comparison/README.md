# SBA annual-report award-count structural comparison

**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB,
JCT, and state economic-development offices

## Public claim

For all 632 award-count cells printed in FY2020 Table 18, FY2021 Table 18, and
FY2022 Table 20, this study reports the differences between those published
counts and counts computed from the pinned September 17, 2026 SBIR.gov export
under declared row, year, program, phase, and jurisdiction rules. A separate
blinded-role implementation reproduced all 1,264 count operands used to
calculate those differences.

[Read the generated public result](../../docs/public/sba-structural-comparison.md).

## Status

**Validated, not approved evidence.** The fidelity test matched 1,264/1,264 operands with
the exact complete-population point interval `[1.0, 1.0]`. The public renderer
and its sidecar reproduce byte-for-byte. Every claim-facing revision requires
supporting evidence audits and reader reviews. One final pinned review of the
exact manifest claim boundary governs evidence approval. Operational
materialization, owner merge approval, and citation metadata are separate controls.

## Comparison summary

The 632 cells contain 276 exact and 356 unresolved comparisons. Signed
recomputed-minus-published differences sum to `+333`; absolute cell
differences sum to `869`. Fifty-seven exact cells are zero versus zero. Among
the 575 cells where either source is nonzero, 219 are exact. The 356 unresolved
cells comprise 208 positive and 148 negative differences.

Of 20,836 export rows retained for FY2020-FY2022 before jurisdiction handling,
one had blank `State` and was excluded under the frozen rule. The remaining
20,835 rows were counted. Sixty eligible groups had no retained row and
received a recomputed count of zero.

The study profile accepts only its 53 exact, case-sensitive, untrimmed full
jurisdiction names. Every unmapped nonblank value blocks the run. Its
`Marshall Islands` to `MH` mapping is study-specific, not an extension of the
general canonical jurisdiction set.

## What this study does not show

- It does not reproduce the unavailable publication-era SBIR.gov export.
- It does not certify either source as complete or correct.
- It does not establish official-report equivalence.
- It does not compare or validate award-dollar totals.
- It does not measure commercialization, program effects, or economic return.
- It does not validate M&A, private-capital, or other repository outputs.
- The blinded roles are separate implementations in this repository, not an
  unaffiliated third-party replication.

The validation also cannot detect a rule error shared by both separate
implementations.

## Inputs

The [source manifest](source-manifest.json) declares the exact URLs, versions,
retrieval times, byte counts, SHA-256 values, row counts, page counts, and schema
fingerprints for the September 17, 2026 SBIR.gov award export and the FY2020,
FY2021, and FY2022 SBA Annual Reports. The [study contract](study.yaml) freezes
that manifest, the count rules, producer, 632-cell result, 1,264-unit validation
population, separate blinded-role submission, and audit record.

## Reproduce

From a release checkout, run:

```bash
make install-core
make reproduce-sba-structural
```

The command retrieves and verifies about 402 MB of public source files. It then
rebuilds the count comparison and requires byte identity with
`results/count-comparison.csv` at SHA-256
`e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`.
It also reconciles the 1,264-value confirmatory submission at SHA-256
`66827a11e860da48a9da215ab982722fa182ceb2726a9ef05a182922c61bae2a`.
It verifies the public sidecar at SHA-256
`b87c38ebcc43621d5bb83aaa1102006bc5ab61a8da33e8ed6645eb0b76f87dd2`
and the generated Markdown at SHA-256
`8ab91c64cf60eed4876bf4b7dd3db6c4023c4d50de5c49f30c533b34c741ae02`.

## Review history

- Candidate design and population frozen: commit `72695b18`.
- Final design clarification frozen: commit `b5ae2ddc`.
- Valid Packet v5 frozen before extraction: commit `c4874c00`.
- Sealed confirmatory artifacts recorded: commit `56acfb0f`.
- Post-result evidence audit: go with required changes for `validated`; not
  authorized for `approved`.
- Release-readiness evidence audit: `GO` for the core-only reproduction path
  and final cold-reader review; no merge or citation authority.
- Claim-facing evidence and cold-reader records: see `reviews/`. A review
  satisfies the gate only when it names the exact current public hashes.
- Release tag: pending.

Read [the amendment record](amendments.md) for every invalid or
nonconfirmatory run and the final freeze chronology.

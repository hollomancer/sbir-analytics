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

**Validated, not citable.** The fidelity test matched 1,264/1,264 operands with
the exact complete-population point interval `[1.0, 1.0]`. The public renderer
and its sidecar now reproduce byte-for-byte. The final cold reader review
returned `BRIEF`. Materialization, owner approval, and tagged-release
requirements still govern citable promotion.

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
`a0b81cc9d700de5fae4cfa1857a13fc593ba47223362968d55a0b071f1516e85`
and the generated Markdown at SHA-256
`9f643c041a3a8747927c5565a7be5a0a3621d3d63ff30858f2ba614b6726c742`.

## Review history

- Candidate design and population frozen: commit `72695b18`.
- Final design clarification frozen: commit `b5ae2ddc`.
- Valid Packet v5 frozen before extraction: commit `c4874c00`.
- Sealed confirmatory artifacts recorded: commit `56acfb0f`.
- Post-result evidence audit: go with required changes for `validated`; not
  authorized for `citable`.
- Release-readiness evidence audit: `GO` for the core-only reproduction path
  and final cold-reader review; no merge or citation authority.
- Final named-reader review: `BRIEF` on the exact Revision 10 public hashes;
  no remediation and no merge or citation authority.
- Release tag: pending.

Read [the amendment record](amendments.md) for every invalid or
nonconfirmatory run and the final freeze chronology.

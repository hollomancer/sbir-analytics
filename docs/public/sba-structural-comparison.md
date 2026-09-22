# SBA Annual-Report Award-Count Structural Comparison

**Prepared for:** SBIR program managers and policy analysts in Treasury, OMB, JCT, and state economic-development offices

> **Status: Validated, not citable.**

This page reports a validated current-vintage structural comparison. The release
gates are still closed. Do not quote this result as a released finding.

## Bounded claim

For all 632 award-count cells printed in FY2020 Table 18, FY2021 Table 18, and FY2022 Table 20, this study reports the differences between those published counts and counts computed from the pinned September 17, 2026 SBIR.gov export under EXPORT_ROW_V1, AWARD_YEAR_FIELD_V1, and the frozen program, phase, and jurisdiction rules. A separate blinded-role implementation reproduced 1,264 of 1,264 count operands. The recorded interval is [1.0, 1.0] using the method: exact complete-population point interval; no sampling.

In plain language: Count each parsed export row once, use Award Year as the year, and do not deduplicate.

The validation supports source-capture and transformation fidelity. It does not
establish agreement between the SBA annual reports and SBIR.gov.

## Comparison result

The comparison contains 632 count cells: 276 are exact and 356 are unresolved. Across the same cells, recomputed minus published counts sum to +333. This +333 total is not an omitted-award estimate, a source-correctness verdict, or a causal explanation.

The signed difference is the recomputed count minus the published count.

| Fiscal year | SBA table | Cells | Published total | Recomputed total | Signed difference | Exact | Unresolved |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FY2020 | 18 | 212 | 7,136 | 7,315 | +179 | 91 | 121 |
| FY2021 | 18 | 212 | 6,783 | 6,881 | +98 | 88 | 124 |
| FY2022 | 20 | 208 | 6,583 | 6,639 | +56 | 97 | 111 |
| **Total** | — | **632** | **20,502** | **20,835** | **+333** | **276** | **356** |

Every nonzero difference remains `unresolved`. The study applies no tolerance
verdict, dollar comparison, or causal mismatch label.

The complete cell-level result is in `studies/sba-annual-report-structural-comparison/results/count-comparison.csv` (SHA-256 `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381`).

## Validation result

The separate blinded role reproduced **1,264 of 1,264** extracted operands.

- Interval: `[1.0, 1.0]`
- Method: `exact complete-population point interval; no sampling`
- Evaluated: `2026-09-21`
- Frozen design: `studies/sba-annual-report-structural-comparison/validation-design-v1.md`
- Design SHA-256: `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3`

This was a complete-population fidelity check. It was not a sample estimate.
It cannot detect a rule error shared by both separate implementations.

## Sources and vintage

| Source | Vintage or as-of | Captured | Clean verification | Bytes | SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| SBIR.gov award export | September 17, 2026 export object version | 2026-09-17 | 2026-09-21T22:09:28Z | 394,636,989 | `aed146eab56f370c9f3fe7f562475e3eedfc61cca2eba112c830fac6f73bf38a` |
| FY2020 SBA annual report | FY2020 report, Table 18 | 2026-09-17 | 2026-09-21T22:09:28Z | 2,505,195 | `f1f51abb29c71d631451868f31babf2f6f1fe3845df91e534052f1d40dece3d3` |
| FY2021 SBA annual report | FY2021 report, Table 18 | 2026-09-17 | 2026-09-21T22:09:29Z | 2,444,751 | `30b4dfa9b4c2c2220fc15938d5bd1a44bee92d5aa746b8756dc7d66217c6df55` |
| FY2022 SBA annual report | FY2022 report, Table 20 | 2026-09-17 | 2026-09-21T22:09:29Z | 2,038,536 | `5ba60852f1cc44b23afdbf810ecf0cff77d714d10ffc786a9b73416d7c000fd1` |

## Adjacent non-claims

- The study does not reproduce the unavailable publication-era SBIR.gov export.
- The study does not certify SBIR.gov or the SBA annual reports as complete or correct.
- The study does not establish official-report equivalence.
- The study does not compare or validate award-dollar totals.
- The study does not measure commercialization, program effects, or economic return.
- The study does not validate M&A, private-capital, or other repository outputs.
- The validation does not detect a rule error shared by both separate implementations.
- Independence is between named blinded roles and separate implementations in this repository; it is not an unaffiliated third-party replication.

## Reproduce

From the repository root in a tagged release checkout, run:

```bash
make install-core
make reproduce-sba-structural
```

To regenerate this JSON sidecar and Markdown page together from the committed
comparison and manifests, run:

```bash
uv run python scripts/data/render_sba_structural_comparison.py
```

## Run and artifact hashes

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| Source manifest | `studies/sba-annual-report-structural-comparison/source-manifest.json` | `be8adfce554b2811cb612428bebab314f061b2a808b9cc957ad0311797388db3` |
| Validation design | `studies/sba-annual-report-structural-comparison/validation-design-v1.md` | `7373d7e189bf8dce3ec4611064f698571053b3fb397e213e1bf8873424839fa3` |
| Frozen validation population | `studies/sba-annual-report-structural-comparison/validation-population-v1.csv` | `48dfdf1ea70e9a74378c21a3a661795540ebd6450c77365ebdad76c6569b68c1` |
| Count producer | `packages/sbir-analytics/sbir_analytics/assets/sba_annual_report_structural_comparison/producer.py` | `bff52a594e4d77a2094c584e59365d4fd8be7dc381f2029246927fdebec5445a` |
| Count reproduction command | `scripts/data/run_sba_structural_comparison.py` | `a8d2aa68e40e5748c241795599bf7c432abb013cfe7c26a020c5fbc29c6be538` |
| Public reproduction command | `scripts/data/reproduce_sba_structural_comparison.py` | `741187a34827ea0df008ca627aedd239a008d7e5f9937d70eb43a607baeab436` |
| Public result renderer | `scripts/data/render_sba_structural_comparison.py` | `d666b51fe4e18256c0359fccd88d1fcad9a610699861ab5a4d970b2ad2de7572` |
| Environment lock | `uv.lock` | `b9f214496158828da145a19db9c7d5cb4fc52765eeacb9a394312a2b6cf34893` |
| 632-cell count comparison | `studies/sba-annual-report-structural-comparison/results/count-comparison.csv` | `e86ab66905f65adaa7fdb721ced6bcbc7b3991a288ba37156f1efe9b4bed7381` |
| Confirmatory packet manifest | `studies/sba-annual-report-structural-comparison/validation/blind-packet-manifest-v5.json` | `51033aca620e71f71fc18d6ae398d27fe238fbf7c7d6cda4e748ba7db3299314` |
| Independent validation values | `studies/sba-annual-report-structural-comparison/validation/confirmatory/validation-values.csv` | `66827a11e860da48a9da215ab982722fa182ceb2726a9ef05a182922c61bae2a` |
| Confirmatory run diagnostics | `studies/sba-annual-report-structural-comparison/validation/confirmatory/run-diagnostics.json` | `bf8c932dd8725f2f3e66309c0318987d4a1eed485e6651d064f2037e9f68dbb8` |
| Confirmatory reconciliation | `studies/sba-annual-report-structural-comparison/validation/confirmatory/reconciliation.json` | `bca6828884c45fe550a5738f95d59803e0ccbfb6891e7b468ce1f2113a4d92e7` |
| Confirmatory attestation | `studies/sba-annual-report-structural-comparison/validation/confirmatory/attestation.json` | `015febb06cb68884d5c703531f6c99feeb56e0a500c1e73f383457406ab300cb` |
| Sealed-component hashes | `studies/sba-annual-report-structural-comparison/validation/confirmatory/sealed-components.sha256` | `c452750aa2b717c4c5781cc758b19ef6566cb98421aa64e39d11554844c302b0` |
| Post-result evidence audit | `studies/sba-annual-report-structural-comparison/reviews/post-result-evidence-audit.md` | `ac05b2e6d888b0b60e1ea57e0b5a32b9a4f70b6bc4d7dcb118af399975411b4a` |

Public sidecar content SHA-256: `9a1e9d6081fa0aaae554727cde589cdc47a86a09f0988fa8b2bc887aea01ed49`.
This content digest is SHA-256 over the sidecar's `content` object encoded as
canonical JSON with sorted keys and compact separators. It differs from the
whole-file SHA-256 because the file also stores this digest and schema version.

## Release gates still open

- Release governance requires explicit owner approval before merge, an immutable annotated version 0.18.0 tag, tag-bound citation metadata, and a citable-promotion evidence audit. The named-reader gate is complete.

# Phase III Census Materialization — February 6, 2026 Data Cut

## Interpretation boundary

This is the complete Phase 1 deterministic census audit, not a validated count of
statutory Phase III awards. Every row and sensitivity cell is reported; no cell is a
headline result. As of this February run, the matched negative-control study, placebo
test, and labeled validation were not part of the materialization, so this record does
not establish that the frozen proxy discriminates Phase III work from ordinary follow-on
federal contracting.

Later record (do not back-date this run): the 2026-08-03 identity, matching, outcomes,
and placebo memos, and the [study file](study.yaml), supersede the "remain unresolved"
clause for those three audits. Labeled validation is still unresolved. The study file is
the clock.

## Run and freeze record

| Item | Recorded value |
|---|---|
| Dagster run | `aa0ec6d3-2b8e-4ad5-8de7-18a22495c107` (`SUCCESS`) |
| Data cut | `2026-02-06` |
| Census code commit used by the run | `dc524ad995c1574965aa9dd94ae1078c8ddf8934` |
| Contract-extraction code commit | `48493d59aa2ae61ba6d26da9ba1527dd317e330d` |
| Frozen revision | `phase-0-r8` |
| Frozen design SHA-256 | `91b84c67e51a36a56b9d11d1afe997bc9b7de7cef090de12c24619116b6351ff` |
| Amendment-log SHA-256 | `6168c6e2a685a3b89fa93eae86976d14798d5e6c67f7a8721b764384081ce74c` |
| Stochastic execution | `false` (seed `null`) |
| Blocking sensitivity check | Passed: all seven one-factor contrasts reported; no review condition triggered |

The run metadata recorded the same commit tags, data cut, frozen revision and hashes,
ordered clauses, source paths, and non-stochastic execution record shown above.

## Verified inputs

| Artifact | Rows | Bytes | SHA-256 | Verification |
|---|---:|---:|---|---|
| `data/transition/contracts_ingestion.parquet` | 1,879,459 | 416,094,799 | `c1518188ef674f3b301ef61be19f6db796a9389e4d03f1196280080f71803a98` | Canonical `rpt.transaction_search`, physical `rpt.transaction_search_fpds`, February mirror member `5924.dat.gz`; manifest and output checksum passed |
| `data/processed/phase_iii_census_sbir_awards.parquet` | 219,500 | 207,826,925 | `b46c552f26a9de9ff70bb63f08880a38d9e4d4413c33d23c3e539f4316e1421f` | SBIR.gov v2 manifest passed; 219,503 raw rows with three exact duplicates collapsed |
| `data/processed/phase_ii_awards.parquet` | 95,313 | 7,793,225 | `4ebace02624b0c3591b01dd8ea1bbe1d9cd2a3828c648c5c7831776810f58b4a` | `phase-ii-awards-v2`, `ok: true`; exact persisted frame matched the in-memory Dagster input |

The contracts manifest pins the 167,887,503,123-byte Internet Archive mirror, archive
ETag, table-of-contents hash, 374-column schema hash, vendor-filter hash, member CRC32 and
SHA-256, and output hash. The Phase II manifest proves that its federal rows were built
from that same contract parquet and that its SBIR.gov rows came from the verified v2
artifact. The processed SBIR.gov artifact in turn pins the 394,394,570-byte bulk source
(`award_data.csv`, SHA-256
`1c4c8b7d7b0928021699722c43bae97d8e2d79d2723857179e7a160255e573db`) and its ordered
42-column source schema.

## Complete cumulative drop-off ladder

Dollar totals are signed federal action obligations deduplicated at target-transaction
grain within each row. Pair counts remain prior-award × target-transaction rows, so the
four measures intentionally diverge.

| Order | Clause | Surviving pairs | Distinct firms | Distinct contracts | Total obligated dollars |
|---:|---|---:|---:|---:|---:|
| 0 | All inherited normalized exact-UEI pairs | 53,890,816 | 8,938 | 531,972 | $417,549,185,734.16 |
| 1 | Prior Phase II end date is observable at the data cut | 35,561,357 | 7,683 | 474,757 | $385,209,098,109.01 |
| 2 | Target action is strictly after the Phase II end and at the data cut | 16,625,809 | 6,207 | 319,539 | $317,069,714,364.31 |
| 3 | Target is not affirmatively coded SBIR/STTR Phase I or II | 9,421,711 | 4,756 | 260,158 | $288,631,407,578.18 |
| 4 | Target is not already coded SBIR/STTR Phase III | 7,821,369 | 4,555 | 249,994 | $260,345,240,108.68 |
| 5 | Prior and target share an exact full NAICS or PSC code | 727,292 | 2,369 | 28,665 | $55,080,851,466.46 |

## Complete sensitivity grid

| Time window | Agency rule | Surviving pairs | Distinct firms | Distinct contracts | Total obligated dollars |
|---|---|---:|---:|---:|---:|
| None | Same agency | 247,548 | 1,693 | 15,297 | $29,905,425,795.33 |
| None | Same department | 595,689 | 2,129 | 24,585 | $49,300,151,046.27 |
| 5 years | Same agency | 160,301 | 1,643 | 13,502 | $21,298,051,673.61 |
| 5 years | Same department | 397,872 | 2,078 | 20,392 | $34,679,849,644.75 |
| 10 years | Same agency | 221,790 | 1,688 | 14,739 | $25,960,766,045.91 |
| 10 years | Same department | 543,607 | 2,122 | 23,334 | $43,145,149,401.74 |

## One-factor sensitivity diagnostics

Each comparison varies one dimension while holding the other fixed. Window contrasts are
adjacent in the nested `none → 10 years → 5 years` order. The blocking check can stop only
for a window fold in distinct firms or distinct contracts that exceeds both 3× and the
largest adjacent core-clause fold for the same metric. Pair and agency folds are reported
for diagnosis but do not decide the check.

| Contrast | Held constant | Pair fold | Firm fold | Contract fold | Review triggered |
|---|---|---:|---:|---:|---|
| None → 10 years | Same agency | 1.1161× | 1.0030× | 1.0379× | No |
| 10 years → 5 years | Same agency | 1.3836× | 1.0274× | 1.0916× | No |
| None → 10 years | Same department | 1.0958× | 1.0033× | 1.0536× | No |
| 10 years → 5 years | Same department | 1.3663× | 1.0212× | 1.1443× | No |
| Same department → same agency | No window | 2.4064× | 1.2575× | 1.6072× | No |
| Same department → same agency | 10 years | 2.4510× | 1.2571× | 1.5831× | No |
| Same department → same agency | 5 years | 2.4820× | 1.2648× | 1.5103× | No |

## Persisted outputs

| Artifact | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| `data/processed/phase_iii_census_dropoff.parquet` | 6 | 6,264 | `2e11e0c7dd0feeedc47eeee50e65d3b94eada90ef34ac7dcbbd70f210b8fb3e5` |
| `data/processed/phase_iii_census_sensitivity.parquet` | 6 | 5,698 | `32b70cc3400bf9d8ab9a6a20b664950a976fb39610f50bc8f5fcb35b98b3aa84` |

Both parquets were reread after materialization. Their schemas and row order matched the
frozen artifact contract, and the seven diagnostics above were reconstructed from those
persisted tables rather than from an in-memory pre-write frame.

## Questions explicitly left for later phases

1. Can SAM.gov controls be proven SBIR/STTR-negative over the complete available award
   history, and how many candidates must be excluded for positive or unreliable status?
2. Can each SBIR firm obtain one to three controls balanced within 0.1 standardized mean
   difference on primary NAICS, employee-count band, state, first-contract year, and PSC
   family without introducing an unapproved numeric cutoff?
3. When the identical arm-blind filter is run, how much do the per-firm criteria-count
   distributions overlap, and what is the ratio of firms clearing the full criteria set?
4. Does a seed-fixed across-firm permutation of Phase II completion dates materially
   change the complete census tables?
5. Do labeled or independently documented Phase III awards show that the uncoded proxy is
   valid enough to support an undercount claim?

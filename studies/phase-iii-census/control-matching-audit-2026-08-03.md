# Phase III negative-control matching audit — August 3, 2026

## Interpretation boundary

This is the required pre-outcome matching and balance gate. It contains no census filter
result for either arm, criteria-met distribution, overlap coefficient, full-criteria ratio,
or placebo result. Exact balance among retained pairs does not establish that the frozen
criteria discriminate Phase III work from ordinary federal contracting.

## Frozen design and run

| Item | Recorded value |
|---|---|
| February contract mirror | `usaspending-db_20260206.zip`, member `5924.dat.gz` |
| Frozen revision | `phase-0-r12` |
| Frozen design SHA-256 | `c61d690b0e6e20caf6651b7233d9074b99641de5cc1d4b1e3679ab5b8a58c49f` |
| Amendment-log SHA-256 | `8f364cb9c832d01e032d253050a00d4b2aaffbaa97b17f46877fe2e917191514` |
| Matching code commit | `027409e4` |
| Stochastic execution | `false` |
| Census filter invoked | `false` |

The initial production query was stopped before publishing artifacts when DuckDB began
spilling an unbounded projection of the contract metadata struct. Commit `027409e4`
preserves the frozen first-contract definition while projecting only recipient UEI,
action date, PSC, and `metadata.business_categories`. The successful run produced no
DuckDB spill and left the 34-GiB disk headroom unchanged.

## Verified inputs

| Input | Rows | SHA-256 |
|---|---:|---|
| February control contract transactions | 82,513,002 | `587fd2e36802a43069cf358c0034a5dc4fd4905a0f6e7f3d66d762edc794dc15` |
| SAM entity rows | 895,429 | `5870e278599dbba58d8e55053a01813e827ea39a17d9f6cb0ac71ef1200fa5a9` |
| Initial SAM eligibility rows | 887,308 | `313056d78c4cba56e3472f7b7fc0ecb887e0b03da6c37f64c8ee66ad90f3f228` |
| Validated Phase II awards | 95,313 | `4ebace02624b0c3591b01dd8ea1bbe1d9cd2a3828c648c5c7831776810f58b4a` |
| Exact-UEI vendor filter | 857,122 UEIs | `7cad006416e7e633ffad134b8b18c829516ee85060edc21ee14aaf996f634560` |

The contract manifest passed and pins the archive ETag, byte size, TOC and schema hashes,
member CRC32 and SHA-256, exact vendor-filter hash, output hash, and 82,513,002-row Parquet
footer. The Phase II manifest passed independently.

## Conservative eligibility table

| Final status | Candidate identity envelopes |
|---|---:|
| Confirmed SBIR | 13,613 |
| Indeterminate possible SBIR | 29,918 |
| Eligible screened negative | 843,777 |
| **All candidate envelopes** | **887,308** |

Across all candidate envelopes, 7,922 have an exact UEI intersection with the validated
Phase II frame and 6,321 have an FPDS `SR1`–`SR3` or `ST1`–`ST3` code. These counts can
overlap each other and the earlier conservative exclusion classes; they are evidence flags,
not additive exclusion totals.

## Covariate coverage before matching

| Arm | Covariate | Observed | Missing | Conflict | Total | Observed share |
|---|---|---:|---:|---:|---:|---:|
| SBIR | Primary NAICS | 6,948 | 5,094 | 0 | 12,042 | 57.70% |
| SBIR | First-contract business size | 8,952 | 3,086 | 4 | 12,042 | 74.34% |
| SBIR | State | 7,922 | 4,120 | 0 | 12,042 | 65.79% |
| SBIR | First-contract year | 8,956 | 3,086 | 0 | 12,042 | 74.37% |
| SBIR | PSC family | 8,882 | 3,126 | 34 | 12,042 | 73.76% |
| Control | Primary NAICS | 609,319 | 234,458 | 0 | 843,777 | 72.21% |
| Control | First-contract business size | 183,774 | 659,655 | 348 | 843,777 | 21.78% |
| Control | State | 839,877 | 3,900 | 0 | 843,777 | 99.54% |
| Control | First-contract year | 184,122 | 659,655 | 0 | 843,777 | 21.82% |
| Control | PSC family | 179,878 | 662,738 | 1,161 | 843,777 | 21.32% |

All five covariates are usable for 5,539 of 12,042 treated firms and 167,616 of 843,777
screened-negative controls. No missing value is imputed and no conflict is broken by row
order.

## Exact matching result

| Matched controls retained | Treated firms | Share of 5,539 match-eligible treated firms |
|---:|---:|---:|
| 0 | 4,827 | 87.15% |
| 1 | 508 | 9.17% |
| 2 | 91 | 1.64% |
| 3 | 113 | 2.04% |
| **At least one** | **712** | **12.85%** |

The retained frame contains 1,029 treated-control pairs. Relative to all 12,042 exact-UEI
treated firms, 712 firms (5.91%) retain at least one control. These are coverage statistics,
not outcome results.

## Balance gate

| Covariate | Maximum absolute SMD | Levels above 0.1 |
|---|---:|---:|
| Primary NAICS | 0.000 | 0 |
| First-contract business size | 0.000 | 0 |
| State | 0.000 | 0 |
| First-contract year | 0.000 | 0 |
| PSC family | 0.000 | 0 |

The balance gate passed. Zero SMD is expected because every retained pair matches exactly
on all five covariates; it does not offset the limited treated-firm coverage.

## Persisted pre-outcome artifacts

| Artifact | Rows | SHA-256 |
|---|---:|---|
| Final eligibility | 887,308 | `c5c0947dd7fbf52b28484c142515d3deae3c838e64b9e2a49cd67bd4c88695a9` |
| Treated covariates | 12,042 | `b1bd00b36313b16cb49f51821553f74df22a5477736549d2d495e6919bd1a13e` |
| Control covariates | 843,777 | `faca0d583d0cdf3c5a1677fe58ed77f4d6050e854a8f6f8ca8238cc577949785` |
| Coverage table | 10 | `e33a8d4aaa39b79074be2c4decf29260f34670e6ead32e0362d0b48918ee7fd8` |
| Exact matched pairs | 1,029 | `4c0aa165a16bd58471797192284f7c691a675d27df75d1886a6bf96835fdd789` |
| Matching summary | 4 | `709d0b77d5e755aa04f8249766c75a4a3b789fef877ea2f78d002167b9406047` |
| Balance table | 116 | `ceb33d314f74dc67d49882e99d855a4c67632726e407df7677b846b122219bde` |

## Required review before outcomes

The frozen design specifies no minimum matched share, so the run does not manufacture one.
Before Phase 2 outcome construction, the repository owner must decide whether the exact
matched frame's coverage is adequate for the intended negative-control inference. Any
revision to matching covariates or exactness would require a prospective amendment with a
reason that does not inspect arm outcomes.

### Review disposition

On 2026-08-03, before any arm outcome existed, the repository owner approved proceeding
with the clean restricted test and limiting the negative-control inference to the matched
common-support subset. Revision 13 records that decision. Exact matching remains unchanged;
the approval does not extrapolate the result to unmatched Phase II firms.

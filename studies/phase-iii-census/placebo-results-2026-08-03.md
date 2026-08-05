# Phase III full-census placebo — August 3, 2026

## Finding and interpretation boundary

The fixed-seed cross-firm date permutation did not reproduce the complete-filter result.
At the final cumulative clause, the actual frame exceeded the placebo frame on pair rows,
distinct firms, distinct contracts, and obligated dollars. The actual frame also exceeded
the placebo frame on all four measures in each of the six sensitivity cells. The temporal
link therefore changes the frozen proxy under this placebo rather than contributing
nothing.

This is one preregistered falsification run, not labeled validation or a probability
calculation. The randomized cyclic construction is reproducible but is not a uniform draw
over all possible cross-firm derangements. No similarity threshold, pass/fail rule,
preferred cell, or headline count was used. The matched-control distributions still
overlap substantially, and neither result establishes that any contract is statutory
Phase III or supports an undercount claim.

## Frozen run

| Item | Recorded value |
|---|---|
| February data cut | `2026-02-06` |
| Run checkout commit | `d88e2819b2773eedc7f0952d826e84cdd20d5a94` |
| Frozen revision | `phase-0-r15` |
| Frozen design SHA-256 | `05d1850df6c33ead6d15a34137a4aa202273820a3191b83da0fca007324fe752` |
| Amendment-log SHA-256 | `6ea0768468de67703a4ada3aebd428d44e04e0d0cf9057d8698f9bbb0ee1b313` |
| Seed | `20260801` |
| Assignment method | Randomized cyclic group derangement; not uniform over all derangements |
| Assignment mapping SHA-256 | `c1c97a9c7f1c81105a17dc21888afb7493311605405272672608d950c9250119` |
| Owner approval asserted at invocation | `true` |
| Scoring path invoked | `false` |
| Similarity threshold applied | `false` |
| Headline cell selected | `false` |

The materializer verified the frozen spec, the 1,879,459-row projected February contract
artifact, the 95,313-row Phase II artifact, and the SBIR.gov source artifact before
constructing pairs. It then required the recomputed actual drop-off and sensitivity tables
to equal the already-persisted Phase 1 tables exactly. Their SHA-256 values matched.

## Assignment audit

| Measure | Value |
|---|---:|
| Unique recipient awards | 72,996 |
| Recipient firms | 8,938 |
| Donor firms | 8,938 |
| Same-firm donors | 0 |
| Date value changed | 69,026 |
| Date value unchanged despite a different-firm donor | 3,970 |
| Original null completion dates | 16,798 |
| Permuted null completion dates | 16,798 |

Every recipient award has one recorded donor award and donor firm. The audit preserves the
award-level date multiset, including nulls, while the fanned pair frame preserves row order,
pair count, award-to-pair fanout, and every non-date field.

## Complete cumulative comparison

Each metric cell reports `actual / placebo / actual-minus-placebo / actual-to-placebo`.

| Cumulative stage | Pair rows | Distinct firms | Distinct contracts |
|---|---:|---:|---:|
| All inherited normalized exact-UEI pairs | 53,890,816 / 53,890,816 / +0 / 1.000000× | 8,938 / 8,938 / +0 / 1.000000× | 531,972 / 531,972 / +0 / 1.000000× |
| Prior Phase II end date is observable at the data cut | 35,561,357 / 36,676,827 / -1,115,470 / 0.969587× | 7,683 / 7,862 / -179 / 0.977232× | 474,757 / 494,627 / -19,870 / 0.959828× |
| Target action is strictly after the Phase II end and at the data cut | 16,625,809 / 15,022,059 / +1,603,750 / 1.106760× | 6,207 / 6,412 / -205 / 0.968029× | 319,539 / 356,437 / -36,898 / 0.896481× |
| Target is not affirmatively coded SBIR/STTR Phase I or II | 9,421,711 / 8,220,136 / +1,201,575 / 1.146175× | 4,756 / 4,681 / +75 / 1.016022× | 260,158 / 293,667 / -33,509 / 0.885895× |
| Target is not already coded SBIR/STTR Phase III | 7,821,369 / 6,852,971 / +968,398 / 1.141311× | 4,555 / 4,514 / +41 / 1.009083× | 249,994 / 284,430 / -34,436 / 0.878930× |
| Prior and target share an exact full NAICS or PSC code | 727,292 / 546,242 / +181,050 / 1.331447× | 2,369 / 1,985 / +384 / 1.193451× | 28,665 / 21,357 / +7,308 / 1.342183× |

| Cumulative stage | Obligated dollars |
|---|---:|
| All inherited normalized exact-UEI pairs | $417,549,185,734.16 / $417,549,185,734.16 / $0.00 / 1.000000× |
| Prior Phase II end date is observable at the data cut | $385,209,098,109.01 / $400,633,459,011.50 / -$15,424,360,902.49 / 0.961500× |
| Target action is strictly after the Phase II end and at the data cut | $317,069,714,364.31 / $305,349,347,267.96 / +$11,720,367,096.35 / 1.038383× |
| Target is not affirmatively coded SBIR/STTR Phase I or II | $288,631,407,578.18 / $273,417,531,651.72 / +$15,213,875,926.46 / 1.055643× |
| Target is not already coded SBIR/STTR Phase III | $260,345,240,108.68 / $245,936,632,974.27 / +$14,408,607,134.41 / 1.058587× |
| Prior and target share an exact full NAICS or PSC code | $55,080,851,466.46 / $46,386,904,542.06 / +$8,693,946,924.40 / 1.187422× |

The observable-date clause has more placebo than actual contracts because the frozen
permutation preserves completion dates at unique-award grain, not pair-weighted grain;
awards have different target-pair fanout. This is an expected consequence of the approved
award-level estimand, not a date-multiset failure.

## Complete sensitivity comparison

Each metric cell reports `actual / placebo / actual-minus-placebo / actual-to-placebo`.

| Time window and agency rule | Pair rows | Distinct firms | Distinct contracts |
|---|---:|---:|---:|
| 10 years, same agency | 221,790 / 119,703 / +102,087 / 1.852836× | 1,688 / 1,290 / +398 / 1.308527× | 14,739 / 10,132 / +4,607 / 1.454698× |
| 10 years, same department | 543,607 / 314,269 / +229,338 / 1.729751× | 2,122 / 1,670 / +452 / 1.270659× | 23,334 / 16,846 / +6,488 / 1.385136× |
| 5 years, same agency | 160,301 / 69,750 / +90,551 / 2.298222× | 1,643 / 1,117 / +526 / 1.470904× | 13,502 / 8,363 / +5,139 / 1.614492× |
| 5 years, same department | 397,872 / 185,434 / +212,438 / 2.145626× | 2,078 / 1,472 / +606 / 1.411685× | 20,392 / 14,271 / +6,121 / 1.428912× |
| No window, same agency | 247,548 / 166,628 / +80,920 / 1.485633× | 1,693 / 1,438 / +255 / 1.177330× | 15,297 / 11,017 / +4,280 / 1.388491× |
| No window, same department | 595,689 / 432,879 / +162,810 / 1.376110× | 2,129 / 1,799 / +330 / 1.183435× | 24,585 / 18,226 / +6,359 / 1.348897× |

| Time window and agency rule | Obligated dollars |
|---|---:|
| 10 years, same agency | $25,960,766,045.91 / $20,601,899,147.01 / +$5,358,866,898.90 / 1.260115× |
| 10 years, same department | $43,145,149,401.74 / $37,944,681,164.77 / +$5,200,468,236.97 / 1.137054× |
| 5 years, same agency | $21,298,051,673.61 / $14,173,906,040.57 / +$7,124,145,633.04 / 1.502624× |
| 5 years, same department | $34,679,849,644.75 / $29,330,607,106.26 / +$5,349,242,538.49 / 1.182377× |
| No window, same agency | $29,905,425,795.33 / $23,619,285,731.97 / +$6,286,140,063.36 / 1.266144× |
| No window, same department | $49,300,151,046.27 / $41,471,949,997.95 / +$7,828,201,048.32 / 1.188759× |

## Persisted artifacts

| Artifact | Rows | Bytes | SHA-256 |
|---|---:|---:|---|
| Assignment audit | 72,996 | 2,351,043 | `0e8b73c800ed766a7a15a79b7b3474e3778612187ca46cde6cfd622af14e5ed3` |
| Actual drop-off | 6 | 6,264 | `2e11e0c7dd0feeedc47eeee50e65d3b94eada90ef34ac7dcbbd70f210b8fb3e5` |
| Placebo drop-off | 6 | 6,264 | `e898380785c21231eea117536be8cfaa70b92819cbce4985cda15ea3efa482f5` |
| Drop-off comparison | 6 | 21,497 | `cb04c529ae0632ac9979237bfba2a9534f0d004ca5deca19ba0f8f18ff78ab7b` |
| Actual sensitivity | 6 | 5,698 | `32b70cc3400bf9d8ab9a6a20b664950a976fb39610f50bc8f5fcb35b98b3aa84` |
| Placebo sensitivity | 6 | 5,700 | `20daeec66bbe995e8425f562b95adcc3422d6e6e3d6ad859566e35c826389273` |
| Sensitivity comparison | 6 | 20,931 | `a51464e7eb1f63b05b416d6b3720e10aa79b364121e46a38d5d5032b57d85aba` |
| JSON manifest | — | 4,904 | `1d819a84dc3a6588b39673cd2583ea5f8d20d969487b8f448b27ff96a1f3c4d1` |

The parquet artifacts remain uncommitted data products. The JSON manifest records exact
input and output hashes, the frozen contract, seed, mapping digest, comparison semantics,
and the explicit owner-approval assertion.

# Phase III matched negative-control outcomes — August 3, 2026

## Finding and interpretation boundary

Within the frozen exact-match common-support subset, the criteria show some separation on
the binary full-set outcome, but the firm-level contract-count distributions still overlap
substantially. The SBIR clearing proportion is about 2.10 times the control proportion,
while the overlap coefficient is 0.853. That is descriptive separation within the retained
matched subset, not validation; the high overlap means the criteria do not cleanly
distinguish SBIR firms from otherwise similar federal contractors.

This is an unweighted empirical comparison of 712 retained SBIR firms and 1,029 retained
screened-negative controls. It is not a matched-set causal estimate, does not generalize to
the unmatched Phase II population, and does not validate any contract as statutory Phase
III. This outcomes run did not invoke the placebo (see Frozen run). The preregistered
placebo was run separately and is recorded in
[placebo-results-2026-08-03.md](placebo-results-2026-08-03.md). Hand-labelled validation
remains unresolved. The [study file](study.yaml) is the clock: the placebo is descriptive
falsification evidence, not labeled validation.

## Frozen run

| Item | Recorded value |
|---|---|
| February data cut | `2026-02-06` |
| Frozen revision | `phase-0-r14` |
| Frozen design SHA-256 | `ef5da718f76a8904f5c61da3494af46a7e05428618bcdf96bb1201c489384841` |
| Amendment-log SHA-256 | `02fb5593c4621af227b8ae62ff23cbcaf61d009f4822a6af7bcacd8d540664e6` |
| Outcome code commit | `f3224f90d62a5386c0d0fbd145eb4b17008c7366` |
| Stochastic execution | `false` |
| Scoring path invoked | `false` |
| Placebo invoked | `false` |

The materializer verified the 82,513,002-row February contract parquet, the 95,313-row
Phase II parquet, all matching artifacts, and the current frozen spec before reading arm
outcomes. It projected only matched exact UEIs, created control pseudo-index rows outside
the filter, called the shared `build_uei_pairs` boundary, and passed each arm to the same
pure evaluator without an arm argument.

## Pre-outcome coverage and balance shown beside the result

| Arm | All firms | Complete five-covariate firms | Retained matched firms | Retained share of all firms |
|---|---:|---:|---:|---:|
| SBIR | 12,042 | 5,539 | 712 | 5.91% |
| Screened-negative control | 843,777 | 167,616 | 1,029 | 0.12% |

| Matched controls retained | Treated firms |
|---:|---:|
| 0 | 4,827 |
| 1 | 508 |
| 2 | 91 |
| 3 | 113 |

Every retained pair matched exactly on primary NAICS, first-contract business-size class,
state, first federal contract year, and PSC family. All 116 reported balance rows had
absolute standardized mean difference 0; none exceeded 0.1. These balance results do not
remedy the limited common-support coverage.

## Cumulative outcome audit

Counts are pair rows, distinct target transactions summed within firm, and distinct target
contract instances summed within firm. The firm denominator remains fixed at every stage.

| Arm | Step | Cumulative stage | Pair rows | Distinct transactions | Firm-contract instances | Firms |
|---|---:|---|---:|---:|---:|---:|
| Control | 0 | All exact-UEI pairs | 4,612,301 | 263,820 | 101,767 | 1,029 |
| Control | 1 | Prior end observable | 3,142,858 | 193,299 | 50,722 | 1,029 |
| Control | 2 | Target post-completion | 1,414,314 | 118,557 | 28,794 | 1,029 |
| Control | 3 | Not Phase I/II coded | 1,414,314 | 118,557 | 28,794 | 1,029 |
| Control | 4 | Not Phase III coded | 1,414,314 | 118,557 | 28,794 | 1,029 |
| Control | 5 | Exact NAICS-or-PSC lineage | 107,410 | 20,307 | 2,221 | 1,029 |
| SBIR | 0 | All exact-UEI pairs | 4,723,661 | 178,645 | 65,184 | 712 |
| SBIR | 1 | Prior end observable | 3,611,959 | 151,717 | 56,232 | 712 |
| SBIR | 2 | Target post-completion | 1,714,508 | 108,510 | 42,597 | 712 |
| SBIR | 3 | Not Phase I/II coded | 1,031,962 | 97,192 | 38,454 | 712 |
| SBIR | 4 | Not Phase III coded | 782,846 | 90,562 | 37,022 | 712 |
| SBIR | 5 | Exact NAICS-or-PSC lineage | 88,266 | 16,891 | 2,476 | 712 |

## Full-set clearing comparison

Clearing means at least one distinct target contract survives every frozen clause. It is
the logical nonzero outcome defined in Revision 14, not a tuned cutoff.

| Arm | Firms clearing | Firm denominator | Clearing proportion |
|---|---:|---:|---:|
| SBIR | 176 | 712 | 0.247191 |
| Control | 121 | 1,029 | 0.117590 |

| Comparison | Value |
|---|---:|
| SBIR/control clearing-proportion ratio | 2.102145 |
| Final distinct-contract distribution overlap coefficient | 0.852906 |

## Complete final-stage firm distribution

Zero-outcome firms are retained. The complete six-stage empirical distributions are in the
persisted distribution parquet; this table shows the complete final-stage distribution
used for the overlap coefficient and clearing comparison.

| Contracts surviving | SBIR firms | SBIR share | Control firms | Control share |
|---:|---:|---:|---:|---:|
| 0 | 536 | 0.752809 | 908 | 0.882410 |
| 1 | 64 | 0.089888 | 50 | 0.048591 |
| 2 | 25 | 0.035112 | 17 | 0.016521 |
| 3 | 22 | 0.030899 | 10 | 0.009718 |
| 4 | 12 | 0.016854 | 6 | 0.005831 |
| 5 | 4 | 0.005618 | 2 | 0.001944 |
| 6 | 4 | 0.005618 | 3 | 0.002915 |
| 7 | 6 | 0.008427 | 2 | 0.001944 |
| 8 | 4 | 0.005618 | 1 | 0.000972 |
| 9 | 3 | 0.004213 | 2 | 0.001944 |
| 10 | 1 | 0.001404 | 1 | 0.000972 |
| 11 | 2 | 0.002809 | 2 | 0.001944 |
| 12 | 0 | 0.000000 | 1 | 0.000972 |
| 13 | 0 | 0.000000 | 2 | 0.001944 |
| 14 | 2 | 0.002809 | 0 | 0.000000 |
| 15 | 1 | 0.001404 | 1 | 0.000972 |
| 16 | 1 | 0.001404 | 0 | 0.000000 |
| 17 | 4 | 0.005618 | 2 | 0.001944 |
| 18 | 1 | 0.001404 | 1 | 0.000972 |
| 19 | 1 | 0.001404 | 0 | 0.000000 |
| 20 | 0 | 0.000000 | 1 | 0.000972 |
| 21 | 2 | 0.002809 | 0 | 0.000000 |
| 25 | 2 | 0.002809 | 1 | 0.000972 |
| 26 | 0 | 0.000000 | 1 | 0.000972 |
| 27 | 0 | 0.000000 | 1 | 0.000972 |
| 28 | 1 | 0.001404 | 0 | 0.000000 |
| 34 | 1 | 0.001404 | 0 | 0.000000 |
| 37 | 2 | 0.002809 | 1 | 0.000972 |
| 38 | 0 | 0.000000 | 1 | 0.000972 |
| 41 | 1 | 0.001404 | 0 | 0.000000 |
| 42 | 0 | 0.000000 | 1 | 0.000972 |
| 46 | 0 | 0.000000 | 1 | 0.000972 |
| 48 | 1 | 0.001404 | 0 | 0.000000 |
| 49 | 1 | 0.001404 | 0 | 0.000000 |
| 55 | 0 | 0.000000 | 1 | 0.000972 |
| 57 | 0 | 0.000000 | 1 | 0.000972 |
| 62 | 1 | 0.001404 | 1 | 0.000972 |
| 69 | 0 | 0.000000 | 1 | 0.000972 |
| 74 | 1 | 0.001404 | 0 | 0.000000 |
| 84 | 1 | 0.001404 | 0 | 0.000000 |
| 122 | 0 | 0.000000 | 1 | 0.000972 |
| 142 | 0 | 0.000000 | 1 | 0.000972 |
| 163 | 0 | 0.000000 | 1 | 0.000972 |
| 165 | 0 | 0.000000 | 1 | 0.000972 |
| 180 | 1 | 0.001404 | 0 | 0.000000 |
| 193 | 1 | 0.001404 | 0 | 0.000000 |
| 213 | 1 | 0.001404 | 0 | 0.000000 |
| 276 | 0 | 0.000000 | 1 | 0.000972 |
| 305 | 1 | 0.001404 | 0 | 0.000000 |
| 430 | 1 | 0.001404 | 0 | 0.000000 |
| 506 | 0 | 0.000000 | 1 | 0.000972 |

## Validation checks

- All 712 SBIR firms and 1,029 control firms appear once at each of six stages.
- Each stage's empirical distribution sums to its arm denominator and probability 1.
- No firm-level distinct-contract count increases down the cumulative ladder.
- Contract counts deduplicate Phase II/pseudo-index and transaction fan-out by
  `firm_id + target_contract_key`.
- The pseudo-index copies every matched treated firm's complete Phase II row set to every
  exact UEI in its matched control envelope, replacing only `recipient_uei`.
- An independent second materialization to a separate directory produced the same SHA-256
  for all four Parquet artifacts.

## Persisted outcome artifacts

| Artifact | Rows | SHA-256 |
|---|---:|---|
| Firm × cumulative-stage counts | 10,446 | `8dc2da72bd14ab80f0749163cca1fbfbd7fc9d9d603b1f2da78f2a2464bfb0fb` |
| Complete arm × cumulative-stage distributions | 1,501 | `8e3d02e370760af5684b16b585a7bac2bd4c2bdff367915881284a8f0e76e3c8` |
| Cumulative audit totals | 12 | `635be8a5f4add41976bd84c69e9948eaae590f506fc9f22bc89c55bde9772ee7` |
| Final comparison | 1 | `19583514d54482f4bfbf9ec1f56d370b8f86a2be1afb796729f0f102097ddbcd` |

The sidecar `phase_iii_negative_control_outcomes.json` records input and output hashes,
source provenance, the shared pair builder, the shared evaluator, and the interpretation
boundary. The Parquet artifacts remain data products and are not committed to Git.

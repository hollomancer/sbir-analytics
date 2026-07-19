# Phase III undercount: award-grain protocol

Status: **corrected implementation; empirical rerun blocked by missing inputs.**

`scripts/phase3_benchmark/undercount_award_grain.py` now treats the source-native
`contract_award_unique_key` as authoritative. Reconstructed keys are validation
fields only: any disagreement fails the run instead of silently creating a
second unit. The primary estimate includes contracts, excludes IDVs, and reports
SBIR/SR3 and STTR/ST3 separately.

The output distinguishes two quantities that were previously conflated:

- `description_only_flags`: an unadjudicated direct review queue;
- `description_only_rate_among_text_captured`: a conditional rate within the
  text list, not the fraction of all Phase III awards missed by the code.

The historical DoD 141/962 and NASA 16/202 values remain in
`provisional-results.json` for traceability. They are not reproduced by this PR,
because the gitignored source frames are unavailable in the worktree. Neither
value is called a lower bound until list precision and frame completeness are
measured.

## Dark-cell scenario

`capture_sensitivity.py` labels Chapman as the list-independence (`OR = 1`)
scenario. It reports sensitivity to list dependence and to false positives in
the description-only cell. Positive dependence does not make the Chapman dark
cell an identified lower bound without additional assumptions about
heterogeneous capture, list precision, population closure, and linkage error.

## Release gates

1. Regenerate every contract and IDV query through the manifested puller and
   verify each query exhausted pagination.
2. Confirm native-key validation, contract/IDV separation, and SBIR/STTR strata
   on the frozen input packet.
3. Hand-adjudicate both list-only cells, including random unflagged records, and
   propagate measured error rates through the sensitivity table.
4. Report direct counts and modeled scenarios separately; do not turn either an
   AUC or a selected-list percentage into a universe count.

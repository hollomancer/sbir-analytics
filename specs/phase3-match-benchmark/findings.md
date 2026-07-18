# Phase III benchmark: provisional findings and decision record

Status: **methodology hardened; empirical rerun blocked by missing gitignored inputs.**

The benchmark answers two bounded research questions: whether known Phase III
records can be linked to earlier Phase II work, and how much Phase III coding
undercount is directly observable. It does not identify the complete dark
population and does not convert retrieval scores into counts.

## Evidence that may be retained

- The historical DoD result is **141 unadjudicated description-only flags among
  962 description-captured records**. The percentage is conditional on being
  caught by the text list, not a population code-miss rate.
- The historical NASA analogue is 16 of 202 under the same provisional
  semantics.
- The historical dark-cell value near 949 is the Chapman/independence scenario
  for the stated two-list cells. It is not an identified lower bound. Results
  must be shown with list-odds-ratio and false-positive sensitivity.
- Retrieval AUCs measure portfolio or award-to-notice linkage in selected proxy
  cohorts. They do not measure dark-contract precision, recall, prevalence, or
  universe-wide coverage.
- Survival output is time from first observed DoD Phase II to the first later
  observed **coded** Phase III action. It does not establish true Phase III
  latency or a never-transition fraction.

All retained historical values and their exact status live in
`provisional-results.json`. None is treated as reproduced by this PR.

## Product decisions

- Keep description-only and code-only records as bounded review queues after
  identity and source manifests pass.
- Keep similarity as a triage feature only. Human-adjudicated precision@K is
  required before deployment.
- Recommend a structured parent-award linkage field only with referential
  validation, completeness audits, and many-to-many lineage support. It is less
  exposed to prose-padding incentives, not immune to missingness or gaming.

## Gates before policy use

1. Regenerate both lists with native award keys, contract/IDV separation,
   SBIR/STTR strata, and complete manifests.
2. Rerun every estimator with the corrected code and retain input hashes.
3. Adjudicate list precision and a population-aligned retrieval sample.
4. Use threshold-specific TPR/FPR and prevalence for PPV; AUC alone cannot
   supply precision or a count.

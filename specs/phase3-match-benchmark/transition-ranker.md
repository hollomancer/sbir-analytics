# Transition ranker: bounded research protocol

Status: **provisional portfolio-linkage benchmark; deployment metrics pending adjudication.**

Given an as-of Phase II award, the benchmark ranks selected candidate target
texts. Same-firm or known-Phase-III pairs are proxy labels unless technical
lineage is independently verified. Other firms' targets test identity and
portfolio topicality; they are not operational same-firm non-transition
controls.

## Required estimator behavior

- Pair at award grain and select only Phase II evidence dated on or before the
  target action.
- Score ties as one half in the Mann-Whitney retrieval AUC.
- Keep target text, action date, PSC, FY, and award key on the same source row.
- Record exact-hard, relaxed-hard, random, and excluded negative-pool counts.
- Use a fixed candidate set across model or field comparisons.
- Report label semantics, candidate denominator, tie rate, and cohort flow next
  to every metric.

The historical 0.844, 0.714, 0.879, and 0.828 values used earlier cohort and
metric implementations. They remain visible only as provisional history in
`provisional-results.json` and must be replaced rather than defended after a
data-packet rerun.

## Deployment boundary

No AUC is a contract count or a precision estimate. Deployment requires a
population-aligned candidate pool and blind precision@K adjudication. At base
rate `p`, PPV must be computed from the chosen operating point:

`PPV = TPR × p / (TPR × p + FPR × (1 - p))`.

---
Type: Subsystem Overview
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Transition Detection Overview

Transition detection asks whether an SBIR-funded firm appears to receive related follow-on federal
procurement. It is a proxy built from public records, not proof of statutory Phase III,
commercialization, causation, or private-market success.

## Do not confuse these analyses

| Analysis | Question | Current method |
| --- | --- | --- |
| Transition asset pipeline | Which award/contract pairs are plausible follow-on candidates? | Vendor resolution plus bounded rule-based scoring |
| `sbir_ml.transition` library | How could multiple evidence signals score a candidate? | Configurable scorer, feature extractors, detector, evidence generator |
| [Phase III census](../../studies/phase-iii-census/study.yaml) | How many uncoded follow-on candidates pass frozen criteria? | Reproducible, non-citable study contract |
| [Phase-transition latency](../phase-transition-latency.md) | How long to an explicitly coded Phase III contract? | Survival analysis on coded records |

## Materialized Dagster path

`transition_mvp_job` and `transition_full_job` are defined in
`packages/sbir-analytics/sbir_analytics/assets/jobs/transition_job.py`:

```text
validated contract sample
        │
        ▼
vendor resolution ──▶ rule-based candidate scores ──▶ evidence and detections
                                                        │
                                                        ├──▶ analytics
                                                        └──▶ Neo4j loading
```

The current `transformed_transition_scores` asset starts from the vendor match method and applies
bounded temporal, agency, amount, and identifier-link boosts where fields are available. Its
settings are read by the asset implementation and environment overrides. It does not currently
invoke the full `TransitionDetector` or all six feature extractors described by the library guides.

Run locally after preparing the declared inputs:

```bash
uv run dagster job execute -m sbir_analytics.definitions -j transition_mvp_job
```

Use `transition_full_job` only when Neo4j and the downstream assets are configured. These heavy
jobs are not scheduled on the live Mac mini by default.

## Library path

`packages/sbir-ml/sbir_ml/transition/` contains reusable entity-resolution, feature, scoring,
detection, evaluation, and evidence components. They are tested components, but their presence
does not establish that the current Dagster path uses every signal or meets the performance and
precision figures in historical design material.

The detailed [scoring](scoring-guide.md), [detection](detection-algorithm.md), and
[evidence](evidence-bundles.md) guides document this library path. Verify defaults against code and
`config/transition/detection.yaml` before changing weights or thresholds.

## Identity and interpretation

Company identity uses the canonical profiles in `sbir_etl/identity/`. A successful name or
identifier match establishes a candidate relationship, not topical equivalence. Evidence bundles
must retain the match method, score inputs, source identifiers, and limitations.

Transition-scoring changes must maintain the repository's ≥85% precision benchmark. A benchmark
result is citable only when a study manifest names the data cut, validation design, and permitted
claim.

## Canonical references

- Configuration: `config/transition/detection.yaml` and the implementing asset/module
- Fields: [transition dictionary](../data/dictionaries/transition-fields-dictionary.md)
- Queries: [transition queries](../queries/transition-queries.md)
- Graph: [Neo4j schema](../schemas/neo4j.md)
- Evidence maturity: [epistemic tiers](../steering/epistemic-tiers.md)

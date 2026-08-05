---
Type: Integration Note
Owner: ml@project
Last-Reviewed: 2026-08-03
Status: limited
---

# CET Alignment in Transition Scoring

The canonical CET classification system is documented in
[ML/CET classification](../ml/cet-integration.md). Transition code should consume those versioned
labels rather than maintain another taxonomy.

## Current implementation

`sbir_ml.transition.features.cet_analyzer.CETSignalExtractor` can:

- read a CET-like field from award data;
- infer one contract area from description keywords;
- compare the two labels; and
- emit a `CETSignal` for the multi-signal transition library.

The extractor currently embeds a separate ten-name keyword mapping. It is not aligned to the
canonical 21-area `NSTC-2025Q1` taxonomy, and repository search shows it is exercised by unit tests
but not called by the current Dagster transition scoring asset. Therefore:

- do not describe CET alignment as a current production scoring input;
- do not compare its labels directly with canonical CET aggregates;
- do not tune or expand the embedded list as a substitute for integration work.

## Integration requirement

A future integration should remove the embedded taxonomy, consume versioned award and contract
classifications, define behavior for missing or multi-label cases, and re-run the transition
precision benchmark. Until then CET alignment is a tested library capability, not an operational
or evidence-tier signal.

See the [transition overview](overview.md) for the distinction between the current Dagster path and
the richer `sbir_ml.transition` library.

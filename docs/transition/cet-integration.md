---
Type: Integration Note
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-11-26
Status: limited
---

# CET Alignment in Transition Scoring

The canonical CET classification system is documented in
[ML/CET classification](../ml/cet-integration.md). Transition code should consume those versioned
labels rather than maintain another taxonomy.

## Current implementation

The transition library has no CET extractor. `TransitionScorer.score_cet_alignment` in
`sbir_ml.transition.detection.scoring` compares an award CET label and a contract CET label only
when a caller supplies both. The current Dagster transition scoring asset does not supply them.

The former `sbir_ml.transition.features.cet_analyzer.CETSignalExtractor` was removed because only
its own unit tests called it. It embedded a separate ten-name keyword mapping that did not match the
canonical 21-area `NSTC-2025Q1` taxonomy. Therefore:

- do not describe CET alignment as a current production scoring input;
- do not rebuild a separate keyword taxonomy for transition scoring.

## Integration requirement

A future integration should consume versioned award and contract classifications, define
behavior for missing or multi-label cases, and re-run the transition precision benchmark. Until
then CET alignment is an unused scorer input, not an operational or evidence-tier signal.

See the [transition overview](overview.md) for the distinction between the current Dagster path and
the richer `sbir_ml.transition` library.

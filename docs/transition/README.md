# Transition Detection

Start with the [current overview](overview.md). It distinguishes the Dagster asset pipeline that is
materialized today from the richer `sbir_ml.transition` scoring/evidence library.

Narrow references:

- [Detection algorithm](detection-algorithm.md) - library-level candidate and signal model
- [Scoring guide](scoring-guide.md) - configurable multi-signal scorer
- [Vendor matching](vendor-matching.md) - identity resolution
- [Evidence bundles](evidence-bundles.md) - evidence model and persistence
- [CET alignment](cet-integration.md) - optional, currently disconnected CET signal
- [Transition field dictionary](../data/dictionaries/transition-fields-dictionary.md)
- [Neo4j schema](../schemas/neo4j.md)

For explicitly coded Phase III timing, use the separate
[phase-transition latency](../phase-transition-latency.md) methodology.

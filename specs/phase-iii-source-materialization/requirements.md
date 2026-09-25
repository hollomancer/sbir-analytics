# Phase III Source Materialization — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: this layer supplies the
  schema-verified USAspending and SBIR.gov inputs that the Phase III census and the other
  transition consumers read. It materializes inputs; it does not apply census criteria or
  produce findings, so the questions it serves are anchored by those consumers rather than
  here. See [docs/research-questions.md](../../docs/research-questions.md).

The deterministic source, schema, grain, fingerprint, and atomic-publication
contracts are defined in [design.md](design.md). This layer materializes inputs;
it does not apply Phase III census criteria or produce findings.

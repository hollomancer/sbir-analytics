# Glossary

Short definitions for recurring pipeline and enrichment terms. Method-specific
thresholds and tier contracts live in their owner docs — do not treat this file
as a universal scoring standard.

## Confidence (method-scoped)

There is **no repository-wide High / Medium / Low band**. A confidence value is
meaningful only with its method and calibration population; see
[enrichment-patterns.md](enrichment-patterns.md#confidence).

Owners (read the config or doc; do not copy numbers here):

| Method | Owner |
|--------|--------|
| Enrichment doctrine | [enrichment-patterns.md](enrichment-patterns.md) |
| Fuzzy-match thresholds | `config/base.yaml` (`high_confidence_threshold` / `low_confidence_threshold`) |
| Transition HIGH / LIKELY / POSSIBLE | `config/transition/detection.yaml`, [detection-algorithm.md](../transition/detection-algorithm.md) |
| CET High / Medium / Low | `config/cet/classification.yaml` |
| Form D confidence tiers | [form-d-data-dictionary.md](../research/form-d-data-dictionary.md) |
| Company-categorization bands | `config/base.yaml` (award-count knobs) |

## Key Terms

- Asset check: A Dagster validation attached to an asset that enforces quality gates.
- Quality gates: Configurable pass/fail thresholds that block or allow downstream assets.
- Incremental mode: Process only new/changed data while preserving previous outputs.
- Chunked processing: Split large datasets into bounded-size chunks to manage memory.
- Fallback chain: Ordered sequence of enrichment sources, moving to the next on failure.
- Enrichment evidence: Metadata supporting an enrichment decision (e.g., similarity
  scores, API info). Not the epistemic tier named `evidence` — see
  [epistemic-tiers.md](epistemic-tiers.md).
- Confidence: Numeric score produced by a named method (often 0.0–1.0). Gate on that
  method's contract, not a context-free band from this glossary.
- Epistemic tier: Admission control for how much weight an artifact can carry
  (`primitives` / `pipelines` / `evidence` / `exploratory`). Defined in
  [epistemic-tiers.md](epistemic-tiers.md) and summarized in [CLAUDE.md](../../CLAUDE.md).
- RQ complexity tier: Descriptive / Relational / Inferential / Predictive labels in
  [research-questions.md](../research-questions.md). Not an epistemic tier.
- Batch size: Number of records processed per operation (API call, DB write, etc.).
- Env var override: `SBIR_ETL__...` environment variable that overrides YAML config at runtime.

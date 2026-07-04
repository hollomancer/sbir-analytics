# Data Reliability Manifest — Original Draft, Archived

**Archived:** 2026-07-02
**Status:** Superseded before any code was implemented. Never landed in `sbir_etl/`; no assets were instrumented; the JSON schema was never produced.

## Why archived

The original draft attempted to implement GAO-20-283G (an external audit *assessment* framework) as an 8-requirement, per-asset Reliability Manifest with a tiered fitness verdict, four-dimension sub-objects, provenance and transformation ledgers with reversibility flags, GAO-vocabulary alignment in the JSON schema, a controlled-vocabulary intended-use taxonomy, and a two-asset pilot rollout.

A scope-guard pass identified that this was framework-conformance theater layered on top of a much smaller core:

- **No downstream consumer** for the tiered verdict, four-dimension taxonomy, GAO vocabulary alignment, or worked example. No external auditor is waiting; no downstream code can branch on `fitness_verdict`; no research question in `docs/research-questions.md` gates on manifest-shaped output.
- **Existing machinery already emits most of the signals.** `AlertCollector` (`sbir_etl/utils/monitoring/alerts.py`) already produces JSON/Markdown-serializable alerts with severity levels; `fiscal_audit_trail.py` already does row-count reconciliation; `quality/baseline.py` already handles verdict-over-time. Wrapping these in GAO vocabulary produced zero new signal.
- **The user's stated intent — "gaps as artifact, not test failure" — is a persistence + surfacing problem, not a framework-adoption problem.** It reduces to ~100 lines: add `emit_caveat(...)` to `AlertCollector`, persist to a new report path, attach to Dagster `MaterializationMetadata`.

Cutting the framework-conformance layer removes work with no consumer and leaves the load-bearing disclosure mechanism intact.

## Superseded by

The replacement lives at `specs/data-reliability-manifest/requirements.md` (same directory, rewritten from scratch). It has three requirements:

1. **Reliability caveat stream** — `AlertCollector.emit_caveat(...)` for subthreshold observations currently logged and discarded. Persisted per-run as JSON. This is the load-bearing requirement.
2. **Provenance ledger** — Per-input source metadata (location, retrieved_at, sha256, row_count) attached to the same artifact. Cheap and independently useful for reproducibility.
3. **Pilot on `validated_sbir_awards`** — One asset instrumented end-to-end, with `caveat_count` + manifest path surfaced as Dagster `MaterializationMetadata`.

The replacement retains GAO-20-283G as *context* (the "why" behind investing in caveat disclosure at all) but does not attempt vocabulary alignment, verdict tiers, or dimension taxonomies in the schema. Those can be layered on if and when an actual external reviewer materializes.

## What was dropped, not moved

The following original requirements were considered and cut because their value did not clear the "does a consumer exist today" bar:

- **Original Req 2 (intended-use declaration + 4-tier fitness verdict)** — No downstream code can branch on the verdict; the fourth tier (`sufficient_with_caveats`) was scope-creep on scope-creep. Dropped entirely.
- **Original Req 3 (four-dimension sub-objects with `dimension_status`)** — A naming layer, not evidence. Kept only as a single `dimension` string field on each caveat (~zero cost).
- **Original Req 4's transformation ledger with reversibility flags** — Row-count reconciliation across every transformation with `lossless|lossy_reversible|lossy_irreversible` classification. `fiscal_audit_trail.py` covers the reconciliation surface where it matters; the reversibility classification had no consumer.
- **Original Req 6.4 (dashboard tab extension)** — Already scoped "in a follow-up PR" in the original draft; if it's not blocking, it's not a requirement.
- **Original Req 7 (two-asset pilot + contributor guide + one-file-PR extension pattern)** — Two-asset scope only existed because the framework was heavy enough to need a "pilot." The replacement's one-asset pilot is the whole rollout.
- **Original Req 8 (GAO vocabulary in schema + worked example doc)** — Vocabulary alignment with a framework no one has asked to see is padding. The replacement references GAO-20-283G in the intro for context but does not embed the vocabulary in the schema.

If a specific external audit or publication surfaces demand for the fuller framework alignment, revisit — the caveat stream and provenance ledger are the natural substrate to build the tiered verdict on top of.

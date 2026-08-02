# Research→Production Doorway — Requirements

> **Status:** Spec / design. No implementation.
> Supports inventory question **E3** (data quality & completeness) and the reproducibility
> obligations running through **E1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E3 (can a published figure be traced to the inputs that produced it)
**Answers for:** anyone consuming a production artifact derived from research code
**Complexity tier:** Infrastructure (not a research tier)

---

## Done when

> Every artifact produced by `scripts/` and read at runtime by `sbir_etl/` or `packages/`
> is registered in a single manifest with its producing script, input witness, and content
> hash; the consuming code verifies that hash on load; and CI fails when a production module
> reads a derived artifact that is not registered. The registry has exactly one entry on the
> day it lands (`fusion_coefficients.json`) and adding the second costs nothing.

---

## Background

The repo is a two-world system, and the split is healthy: `scripts/` is a lab where a
question can be answered without the code first earning production citizenship. That is why
`scripts/phase3_benchmark/` could reproduce a published AUC (0.847 against the study's 0.844)
in days rather than sprints.

The problem is not the lab. It is that the lab has **exactly one export channel and it was
unlabelled**. `packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json` is the
only research-produced artifact committed into a package and read at runtime. Until PR #482 it
crossed with an integrity control that existed and was never invoked: `load_fusion_coefficients`
accepted `expected_corpus_hash` and refused a mismatch, but no production caller supplied it and
no test pinned the coefficients to their provenance record. The hashes agreed by hand.

PR #482 armed that one crossing by hand. This spec generalises it **while the registry still has
one row**, because the cost of the convention is lowest now and the cost of retrofitting it grows
with each artifact.

A second, deeper problem is visible at the same joint and is in scope here: the coefficients are
**not reproducible from a clean checkout**. The corpus they were fit on
(`data/derived/phase3_notice_corpus.parquet`) is gitignored under `*.parquet`, so
`corpus.manifest.json` is the only in-repo witness to what was fit. #482 made drift *detectable*;
it did not make the fit *repeatable*. A doorway that does not require a durable witness would
institutionalise that gap.

---

## Requirements

1. **SHALL** define a single registry — `contracts/registry.yaml` — listing every derived
   artifact that crosses from research into production. One entry per artifact, with:
   `path` (the artifact as committed), `producer` (the script that emits it), `inputs`
   (a witness per input: URI plus content hash, or a named external snapshot with its pull
   date), `content_sha256`, `frozen_at`, and `owner_spec`.

2. **SHALL** verify the artifact's own hash at load time in the consuming module, not only in
   tests. The `fusion_model.FROZEN_CORPUS_FRAME_HASH` pattern from #482 is the reference
   implementation: a constant in the installed package, so verification needs nothing outside it.

3. **SHALL** fail CI when a module under `sbir_etl/` or `packages/` reads a file under a
   derived-artifact extension (`.json`, `.parquet`, `.csv`) that is neither a registry entry
   nor an explicitly listed static-config exemption. This is the requirement that makes the
   doorway a doorway rather than a convention; without it the registry is documentation.

4. **SHALL** require every registry entry to carry a **durable input witness** — either the
   input committed in-tree, or a manifest recording a content hash plus a retrievable source
   URI. An entry whose inputs cannot be re-obtained is registered as
   `reproducible: false` with a stated reason, so the gap is visible rather than implicit.
   `fusion_coefficients.json` lands as `reproducible: false` on day one; that is the honest
   status and this spec does not pretend otherwise.

5. **SHALL NOT** require research scripts to change shape, move, import the library, or become
   Dagster assets. The doorway constrains what *crosses*, not how the lab works. A script that
   never exports anything is unaffected by this spec.

6. **SHALL NOT** introduce a second copy of any artifact. The registry references the committed
   path; it does not vendor, mirror, or re-emit.

---

## Non-goals

- Promoting `scripts/` into the orchestrated pipeline. The two-world split is deliberate.
- Reorganising `sbir_etl/` or the package layering, which is sound (one back-edge, deliberate).
- Reconciling the three transition-scoring paths. Separate concern, separate spec.
- Making `fusion_coefficients.json` reproducible. This spec makes the gap *declared*; closing
  it means freezing the corpus somewhere durable, which is a storage decision, not a schema one.

---

## Risks

- **Registry rots into documentation.** Mitigated by requirement 3: an unregistered read fails
  CI, so the registry cannot silently fall behind the code.
- **The exemption list becomes the escape hatch.** Static config (`config/*.yaml`,
  `data/reference/*.csv`) is genuinely not research output and must be exempt. Keep exemptions
  path-explicit, never pattern-wide, and review additions like any other gate change.
- **Over-engineering for one artifact.** Real risk, and the reason requirements 5 and 6 exist.
  If the implementation is larger than roughly the size of the thing it guards, it is wrong.

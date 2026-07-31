# Phase III Notice Corpus & Fusion Ranker — Tasks

> Sequenced for one focused implementation effort. T1–T3 are the data freeze
> (needs AWS/FPDS access); T4–T6 are offline; T7–T8 integrate into the packet
> (rebase onto the merged PR #466 branch, which carries the ported harness).

## T1 — Commit the recovery scripts
Re-derive the GSA `falextracts` pull + FPDS `VENDOR_UEI`/Sol#+PIID join scripts
under `scripts/phase3_benchmark/` from the July 2026 session recipe.
→ verify: end-to-end run on a single office (e.g. FA8650) produces linked notices.

## T2 — Full recovery run
10-year window, all offices from the study frame. Freeze raw pulls under
`data/raw/gsa_falextracts/` (or documented cache location).
→ verify: yield vs the July baseline (33/849 sols, ~273 notices) recorded in the manifest.

## T3 — Freeze the corpus
Emit `data/derived/phase3_notice_corpus.parquet` + `phase3_notice_corpus.manifest.json`
(source URIs, pull dates, join rules, counts, frame hash; both label channels).
→ verify: manifest hash stable across two runs from the frozen raw pulls.

## T4 — Refit the fusion ladder
`transition_ranker.evaluate` (GroupKFold-by-firm) over the frozen corpus:
text-only → +char → +temporal → +id_xref → +NAICS/notice-type (curated).
Include the char-channel re-test (SHOULD, requirements §8).
→ verify: final AUC within [0.800, 0.886]; ladder table committed to the spec dir.

## T5 — Freeze coefficients
Versioned artifact in `sbir-ml` (weights, scaler params, feature order,
corpus manifest hash). Loader validates the hash and never fits.
→ verify: round-trip test; mismatched-hash load refuses.

## T6 — Precision@K audit sample
Top-K per firm from the refit ranker → `reports/phase_iii/audit/`.
→ verify: file emitted with K rows per firm; format matches the audit-CSV convention.

## T7 — Packet integration (rebase on #466)
Fused score for DIRECTED/FOLLOWON selection behind existing weight validation;
scale-shift measurement before any threshold change.
→ verify: RETROSPECTIVE composite bit-identical (test); shift documented.

## T8 — Docs
Update the why-it-connects design addendum (Phase 3 deferred items resolved or
re-deferred with numbers); note #442 relationship (this freeze does not replace
the adapter-framework home for scheduled re-recovery).
→ verify: spec review checklist passes.

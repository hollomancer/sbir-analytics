# Tasks — ModernBERT analysis layer

## Status

The core exploratory C2 path is implemented and in maintenance. This list
records what exists and the two bounded reliability gaps that remain. It is
not a roadmap for a larger ML platform.

## Implemented

- [x] Add `ModernBertClient` with Hugging Face API and optional local inference.
- [x] Use `nomic-ai/modernbert-embed-base` and return model, inference-mode,
  dimension, input-count, and timing metadata.
- [x] Add patent and award text preparation helpers.
- [x] Add in-process embedding caching and normalized-vector generation.
- [x] Add `modernbert_embeddings_awards` for validated SBIR awards.
- [x] Add `modernbert_embeddings_patents` for transformed patent data or a
  governed local PatentsView archive.
- [x] Add `modernbert_award_patent_similarity` with brute-force cosine
  similarity, threshold filtering, and a bounded per-award result set.
- [x] Add award and patent embedding coverage checks at 95% and 98%.
- [x] Add shared performance-monitor instrumentation to all three computations.
- [x] Add client unit and integration coverage for text preparation, caching,
  normalization, failures, and similarity math.
- [x] Document configuration and operation in `docs/ml/modernbert.md`.
- [x] Reconcile this spec with the maintained implementation and archive the
  unimplemented Bayesian/LoRA proposal.

## Remaining maintenance work

### 1. Multi-asset Dagster integration test

- [ ] Materialize award embeddings, patent embeddings, and similarity in one
  deterministic test with a stubbed `ModernBertClient`.
- [ ] Assert asset dependency ordering and output schemas.
- [ ] Exercise both coverage checks, including a threshold failure.
- [ ] Avoid network, model downloads, local archives, and wall-clock-dependent
  assertions.

This closes the gap between client integration tests and Dagster asset
behavior.

### 2. Similarity-output validation

- [ ] Read `top_k` from the maintained configuration rather than duplicating a
  literal in the asset.
- [ ] Validate that scores are finite and within `[-1, 1]`.
- [ ] Validate that each pair is unique and every emitted score meets the
  configured threshold.
- [ ] Validate that no award exceeds the configured top-k row count.
- [ ] Cover empty and below-threshold results without inventing placeholder
  matches.

## Removed from active scope

The following items are not deferred tasks. They were removed because no
current research contract or measured operating need justifies them:

- Bayesian mixture-of-experts routing and variational inference;
- LoRA expert pools and uncertainty/ECE heads;
- domain-specific embedding experts;
- FAISS or another approximate search backend;
- CET cohesion metrics;
- ModernBERT-specific dashboards and alerting.

Any proposal to restore these items must start with a new scope review,
research-question anchor, target epistemic tier, validation plan, and operating
owner.

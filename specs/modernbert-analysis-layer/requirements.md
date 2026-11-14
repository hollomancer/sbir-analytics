# Requirements — ModernBERT analysis layer

## Context

**Target epistemic tier:** `exploratory`

- **Research question:** C2 — patent–award semantic similarity
- **Lifecycle:** Maintenance
- **Primary users:** Pipeline engineers and analysts exploring possible semantic
  relationships between SBIR awards and patents

ModernBERT similarity is a discovery aid. A high score is not evidence that an
award produced, funded, licensed, or otherwise caused a patent. Similarity rows
must not be promoted into citable patent–award links without a separate study
contract and validation.

## Current scope

The maintained layer embeds award and patent text with
`nomic-ai/modernbert-embed-base`, computes cosine similarity, and emits a
bounded set of candidate pairs above a configurable threshold. It is additive
to the existing pipeline and does not change CET classification.

The following are explicitly out of scope:

- evidence-tier or confirmatory patent–award linkage claims;
- Bayesian mixture-of-experts routing, LoRA adapters, uncertainty heads, or
  dynamic expert pools;
- FAISS or another approximate-nearest-neighbor backend;
- ModernBERT-specific dashboards and alerting infrastructure;
- changes to CET classification or its schemas.

Those features require a new scope review tied to a current research question,
validation plan, and operating owner.

## Requirements

### R1. Embedding client

The client must:

1. generate normalized, 768-dimensional embeddings with
   `nomic-ai/modernbert-embed-base`;
2. support Hugging Face API inference and optional local
   `sentence-transformers` inference;
3. prepare award text from the available solicitation title, award title, and
   abstract fields;
4. prepare patent text from the available title and abstract fields;
5. return the model identifier, inference mode, dimension, input count, and
   elapsed generation time with each result; and
6. raise a clear error when configuration, model loading, or inference fails.

### R2. Dagster assets and outputs

The layer must provide:

1. `modernbert_embeddings_awards`, containing `award_id`, `embedding`,
   `model_version`, `inference_mode`, and `dimension`;
2. `modernbert_embeddings_patents`, containing `patent_id`, `embedding`,
   `model_version`, `inference_mode`, and `dimension`; and
3. `modernbert_award_patent_similarity`, containing `award_id`, `patent_id`,
   and `similarity_score`.

The similarity asset must compute cosine similarity by brute force, apply the
configured minimum score, and emit no more than the configured top-k candidates
per award. The maintained default is 10 candidates.

### R3. Quality boundaries

The award and patent embedding assets must expose blocking coverage checks.
The maintained thresholds are 95% valid award embeddings and 98% valid patent
embeddings. An embedding is valid only when it is present and has the expected
dimension. The current checks report error severity but are not yet blocking;
closing that gap is active maintenance work.

Similarity output must be structurally valid:

- scores are finite and within the cosine range `[-1, 1]`;
- an award–patent pair appears at most once;
- each award has no more than the configured top-k rows; and
- every emitted score meets the configured threshold.

### R4. Isolation and epistemic status

ModernBERT assets must remain in the exploratory ML surface. They must not
modify existing input assets, CET outputs, or evidence-tier tables. Downstream
work must preserve the distinction between a semantic candidate and a
validated relationship.

## Maintenance completion criteria

The current maintenance backlog is complete when:

1. a deterministic multi-asset test exercises award embeddings, patent
   embeddings, similarity, dependency ordering, and coverage-check failure
   behavior with a stubbed client; and
2. configured client, batch-size, threshold, top-k, and coverage settings are
   either wired to execution or removed from the public schema;
3. coverage failures block downstream similarity execution; and
4. automated validation enforces the similarity-output invariants in R3.

These criteria improve reliability of the implemented exploratory path. They
do not promote its evidence status.

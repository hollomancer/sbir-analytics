# Design — ModernBERT analysis layer

## Purpose and boundary

This layer produces exploratory semantic candidates for research question C2.
It embeds SBIR award and USPTO patent text in the same vector space, calculates
cosine similarity, and retains a bounded set of high-scoring pairs.

The output supports discovery and prioritization. It does not establish a
patent–award relationship and is not a citable evidence source.

## Data flow

```text
validated_sbir_awards
        |
        v
modernbert_embeddings_awards ----+
                                   |
                                   v
                             brute-force cosine
                                   |
                                   v
                         threshold + top-k filter
                                   |
                                   v
                    modernbert_award_patent_similarity
                                   ^
                                   |
modernbert_embeddings_patents ----+
        ^
        |
transformed_patents (or governed local PatentsView archive)
```

## Maintained components

### Client

`packages/sbir-ml/sbir_ml/ml/modernbert_client.py` provides
`ModernBertClient`.

- The default model is `nomic-ai/modernbert-embed-base`.
- API mode uses the Hugging Face inference client.
- Local mode uses `sentence-transformers`.
- Embeddings are normalized by default.
- The client can cache vectors in memory for the life of the process.
- Model loading and inference failures are raised to the caller.

`EmbeddingResult` records the vectors, model identifier, elapsed generation
time, input count, dimension, and inference mode.

### Award embedding asset

`modernbert_embeddings_awards` consumes `validated_sbir_awards`. It locates an
award identifier and available solicitation-title, award-title, and abstract
columns, prepares one text per row, and requests embeddings in batches.

Output columns are:

| Column | Meaning |
|---|---|
| `award_id` | Source award identifier, or a logged index fallback |
| `embedding` | Dense vector serialized as a list |
| `model_version` | Hugging Face model identifier |
| `inference_mode` | `api` or `local` |
| `dimension` | Vector dimension |

### Patent embedding asset

`modernbert_embeddings_patents` consumes metadata from `transformed_patents`.
It first reads the governed JSONL output when available. If that output is
absent, it can read one of the known local PatentsView archives. It prepares
title-and-abstract text and emits the same metadata as the award asset, keyed
by `patent_id`.

Absence of both transformed data and a recognized local archive is an error.

### Similarity asset

`modernbert_award_patent_similarity` converts the stored vectors to NumPy
arrays and delegates cosine calculation to `ModernBertClient`. It sorts each
award's scores, keeps the top candidates, and then applies the configured
minimum threshold.

Output columns are `award_id`, `patent_id`, and `similarity_score`. Metadata
records the number of comparisons and matches, the threshold, and summary
score statistics.

The current implementation is deliberately brute force. An approximate index
is not justified by a measured scale or latency requirement in the active C2
scope.

## Configuration

The configuration schema under `ml.modernbert` in `config/base.yaml` is broader
than the current asset wiring. The assets consume `use_local`,
`similarity_threshold`, and both coverage thresholds. They construct
`ModernBertClientConfig` with only `use_local`, so the client uses its own
defaults for model name, token lookup, device, cache folder, and caching.

The assets currently request a flat `ml.modernbert.batch_size`, which is not
declared by the nested API/local schema and therefore falls back to 32. The
similarity asset hard-codes a top-k of 10. Provider, API throttle/retry, nested
batch-size, local-model/device, and text-limit settings are not forwarded by
these assets. They must not be presented as effective operator overrides until
they are wired and tested.

The client model default is declared by `ModernBertClientConfig` in
`packages/sbir-ml/sbir_ml/ml/config/__init__.py`.

Configuration and implementation must use the same model identifier. A model
change requires test updates and an explicit review of comparability with
previous similarity output.

## Validation and failure behavior

Two Dagster checks report embedding coverage:

- `modernbert_awards_coverage_check`: at least 95% valid vectors;
- `modernbert_patents_coverage_check`: at least 98% valid vectors.

Both checks treat a vector as valid only when it is present and has 768
dimensions. Failures use error severity, but the decorators do not currently
set `blocking=True`; a failed check therefore does not stop downstream
similarity execution.

The remaining maintenance work is intentionally small:

1. exercise all three assets and the coverage checks together with a
   deterministic stubbed client;
2. reconcile the public configuration schema with settings actually passed to
   the client and assets;
3. make coverage checks blocking and verify that failure prevents downstream
   similarity execution; and
4. enforce score bounds, uniqueness, threshold, and per-award top-k limits on
   similarity output.

Client unit tests cover configuration, text preparation, caching, error
handling, normalization, and similarity math. Existing integration tests cover
client-level award/patent flows; they do not replace the missing multi-asset
Dagster test.

## Operational characteristics

Embedding generation and similarity calculation are wrapped by the shared
performance monitor. The assets log input counts, model metadata, and summary
statistics. This is sufficient for the current maintenance scope; dedicated
dashboards and alerts are not active requirements.

## Non-goals and superseded design

The previous spec proposed a three-stage Bayesian mixture-of-experts system,
LoRA expert pools, uncertainty calibration, FAISS, cohesion metrics, and new
monitoring infrastructure. None of those components were implemented or tied
to an approved validation study. That proposal is superseded; its disposition
is recorded in `specs/archive/superseded/modernbert-bayesian-moe/README.md`.

Reintroducing any of it requires a new spec rather than expanding this
maintenance contract.

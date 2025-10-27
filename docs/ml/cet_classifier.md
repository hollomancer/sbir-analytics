# CET Patent Classifier — Training and Feature Flow

This document describes the lightweight CET patent classifier components, feature extraction, training flow, evaluation, and Dagster assets.

The goals for this stack:
- Keep imports safe in lean environments (no heavy NLP libs at import time).
- Provide small, deterministic feature helpers suitable for unit tests and CI.
- Offer an opinionated training/evaluation flow that produces a pickle artifact and metadata.

---

## Components

- Feature extraction (pure-Python, import-safe)
  - `src/ml/features/patent_features.py`
    - `normalize_title`, `tokenize`, `remove_stopwords`
    - `extract_ipc_cpc`, `guess_assignee_type`, `bag_of_keywords_features`
    - `extract_features(record) -> PatentFeatureVector` with `as_dict()`
    - Small default keyword map and stopword set for deterministic testing.

- Vectorizers (convert features → numeric matrices)
  - `src/ml/features/vectorizers.py`
    - `KeywordVectorizer`: count and presence features by keyword group
    - `TokenCounterVectorizer`: token counts with/without stopwords
    - `AssigneeTypeVectorizer`: one-hot encoding of assignee type
    - `IPCPresenceVectorizer`: IPC/CPC section presence flags (A–H)
    - `FeatureMatrixBuilder`: combine vectorizers to produce a single 2D matrix

- Classifier wrapper and extractor
  - `src/ml/models/patent_classifier.py`
    - `PatentCETClassifier`: save/load, classify, batch classify, train
    - `PatentFeatureExtractor`: produce normalized training texts + feature vectors from DataFrame rows

- Training helpers
  - `src/ml/train/patent_training.py`
    - `train_patent_classifier(df, output_model_path, pipelines_factory, ...)`
    - `evaluate_patent_classifier(classifier, df_eval, ...)`
    - `precision_recall_at_k(y_true, y_pred_ranked, k=...)`
    - `train_and_evaluate(...)`: convenience wrapper

- Dagster assets
  - `src/assets/cet_assets.py`
    - `train_cet_patent_classifier`: trains and persists model artifact
    - `cet_patent_classifications`: batch-infers classifications for patents

---

## Feature Extraction

`PatentFeatureVector` encapsulates a compact set of deterministic features:

- `normalized_title`: lowercased, punctuation-stripped title text
- `tokens`, `tokens_no_stopwords`, counts (`n_tokens`, `n_tokens_no_stopwords`)
- `assignee_type`: heuristic classification (`company`, `academic`, `government`, `individual`, `unknown`)
- `ipc_codes`, `cpc_codes`, presence flags
- `keyword_features`: simple counts/presence of configured keyword groups
- `application_year` (best-effort parse)

Key functions in `src/ml/features/patent_features.py`:
- `extract_features(record, keywords_map=None) -> PatentFeatureVector`
- `bag_of_keywords_features(title, keywords) -> dict`
- `guess_assignee_type(assignee_str) -> str`

This module avoids heavy NLP dependencies and only uses Python and `re`.

---

## Vectorizers

When training real sklearn-like pipelines, you will typically need numeric feature matrices. `src/ml/features/vectorizers.py` provides a minimal set:

- `KeywordVectorizer(keywords_map)`:
  - For each group in `keywords_map`, creates `<group>__count` and `<group>__presence`.
- `TokenCounterVectorizer()`:
  - Two columns: `n_tokens`, `n_tokens_no_stopwords`.
- `AssigneeTypeVectorizer()`:
  - One-hot across: `academic`, `company`, `government`, `individual`, `unknown`.
- `IPCPresenceVectorizer()`:
  - Binary presence for IPC and CPC across sections `A..H`.
- `FeatureMatrixBuilder([vec1, vec2, ...])`:
  - Horizontal concatenation of individual matrices
  - `get_feature_names()` returns concatenated feature names across all vectorizers

These are designed to be import-safe and deterministic.

---

## Classifier

`src/ml/models/patent_classifier.py`

- `PatentCETClassifier(pipelines: Dict[cet_id, pipeline])`
  - `classify(title, assignee=None, top_k=3) -> List[PatentClassification]`
  - `classify_batch(titles, assignees=None, batch_size=1000, top_k=3) -> List[List[PatentClassification]]`
  - `train_from_dataframe(df, ... use_feature_extraction=True, feature_matrix_builder=None, ...)`
  - `save(path)`, `load(path)`, `get_metadata()`
- `PatentFeatureExtractor(keywords_map=None, stopwords=None)`
  - `features_for_dataframe(df, title_col="title", assignee_col=None) -> (texts, feature_vectors)`

Notes:
- Training can proceed using normalized title-only text, or using extracted features transformed into numeric matrices via `FeatureMatrixBuilder`.
- For lightweight pipelines (like `DummyPipeline` used in tests), text inputs are sufficient.
- For production pipelines (sklearn), pass a matrix via `feature_matrix_builder` in `train_from_dataframe`.

---

## Training Flow

Two options:

1) Programmatically (recommended for scripts and notebooks)

- Prepare a labeled DataFrame with at least:
  - `title`: patent title string
  - `cet_labels`: iterable of CET IDs or a comma-delimited string
  - Optionally: `assignee`, `ipc`, `cpc`, `abstract`

- Build a pipeline factory that returns a binary classifier for each CET ID. In tests, we use `DummyPipeline`, but for production you may use sklearn pipelines.

- Train and persist:
  - Use `src/ml/train/patent_training.py::train_patent_classifier`
  - Optionally evaluate with `evaluate_patent_classifier` (precision/recall@k)

2) Dagster asset

- `train_cet_patent_classifier` expects:
  - `data/processed/cet_patent_training.parquet` with columns:
    - `title`
    - `cet_labels`
    - optional `assignee`
- Writes:
  - Model artifact at `artifacts/models/patent_classifier_v1.pkl`
  - Companion checks JSON with training metadata

---

## Inference Flow

- `cet_patent_classifications` Dagster asset:
  - Inputs:
    - Model artifact: `artifacts/models/patent_classifier_v1.pkl`
    - Patents data:
      - `data/processed/transformed_patents.parquet` or
      - `data/processed/transformed_patents.ndjson`
  - Outputs:
    - `data/processed/cet_patent_classifications.parquet` with columns:
      - `patent_id`
      - `primary_cet`, `primary_score`
      - `supporting_cets`: top-k support list
      - `classified_at`, `taxonomy_version`
    - Companion checks JSON with coverage

Fallback behavior:
- If the artifact or dependencies are missing, the asset produces an empty schema-compatible output and a checks JSON indicating the reason.

---

## Evaluation

`src/ml/train/patent_training.py` provides:

- `precision_recall_at_k(y_true, y_pred_ranked, k)`
  - Simple micro-precision/recall@k for multi-label classification.
- `evaluate_patent_classifier(classifier, df_eval, k_values=(1,3), ...)`
  - Derives metrics for provided k values.

Store evaluation metrics in your artifact metadata by merging them into `config` or a checks JSON.

---

## Paths & Conventions

- Artifacts
  - `artifacts/models/patent_classifier_v1.pkl` (pickle)
  - `artifacts/models/patent_classifier_v1.checks.json` (training metadata)
- Inputs
  - Training: `data/processed/cet_patent_training.parquet`
  - Inference: `data/processed/transformed_patents.parquet` (preferred) or `.ndjson`
- Outputs
  - Inference: `data/processed/cet_patent_classifications.parquet` (preferred) or `.json`
  - Checks: `.checks.json` alongside outputs

---

## CI & Import Safety

- Feature extraction and vectorizers avoid heavy dependencies.
- Many components perform defensive imports and fallback to minimal behavior to keep tests green in lean environments.
- ML unit tests live under `tests/unit/ml/` and are included in the fast `ml-unit-tests` CI job.

---

## Configuration

- Keyword maps
  - A small default keyword map exists in `patent_features.py` for testing.
  - For production, add a YAML-based keyword config under `config/cet/` (e.g., `config/cet/patent_keywords.yaml`) and wire a loader so `extract_features` can use curated per-CET vocabularies.
- Taxonomy
  - `TaxonomyLoader` handles CET taxonomy under `config/cet/`. Ensure `taxonomy_version` is included in the classifier metadata where possible.

---

## Practical Tips

- Start simple: use `use_feature_extraction=True` to feed normalized text to text-based pipelines (or `DummyPipeline` for CI).
- Move to numeric features for sklearn: construct a `FeatureMatrixBuilder` and pass it to `train_from_dataframe` as `feature_matrix_builder`.
- Persist feature names:
  - `PatentCETClassifier` stores `feature_names` in `config` when a matrix builder is used; include this in your artifact metadata for interpretability.
- For portability across environments:
  - Keep sklearn version pinned for artifacts with sklearn objects (training and inference should match versions).

---

## Minimal Example (Script)

Outline of a training script using `DummyPipeline` for illustration:
- Load training data into a DataFrame with `title` and `cet_labels`.
- Create a factory that returns a binary pipeline for each CET ID.
- Call `train_patent_classifier(...)` to persist the model.
- Optionally evaluate with a held-out DataFrame using `evaluate_patent_classifier(...)`.

Replace `DummyPipeline` with your real sklearn pipelines when ready.

---

## Future Enhancements

- Load keyword maps from `config/cet/patent_keywords.yaml`
- Add richer vectorizers and calibration
- Cross-validation and train-test split utilities
- Neo4j loaders for patent → CET relationships (MERGE-based, idempotent)
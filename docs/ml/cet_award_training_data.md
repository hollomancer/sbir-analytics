# CET Award Training Data — Loader Expectations and Paths

This document describes the expected format, paths, and workflows for the CET award training dataset used to train the CET Applicability model. It covers:

- Supported input formats (CSV, NDJSON)
- Canonical schema and flexible column mapping
- Label and keyword parsing rules
- Output artifacts and companion checks
- Programmatic usage and Dagster asset behavior
- Paths and conventions for CI/dev

---

## Components

- Loader:
  - `src/ml/data/award_training_loader.py`
    - `AwardTrainingLoader`: CSV/NDJSON → `TrainingDataset` + `TrainingExample`
    - `load_training_dataset(path, taxonomy_version, ...)`
    - `save_dataset_ndjson(dataset, out_path)`
    - `save_dataset_metadata_json(dataset, out_path)`

- Dagster asset:
  - `src/assets/cet_assets.py`
    - `cet_award_training_dataset`: loads, validates, persists training data to processed storage and emits a checks JSON

- Pydantic models:
  - `src/models/cet_models.py`
    - `TrainingExample`, `TrainingDataset` (the canonical in-memory representation)

---

## Paths & Conventions

- Inputs (preferred → fallback):
  - `data/processed/cet_award_training.ndjson`
  - `data/processed/cet_award_training.jsonl`
  - `data/processed/cet_award_training.csv`
  - `data/raw/cet_award_training.ndjson`
  - `data/raw/cet_award_training.jsonl`
  - `data/raw/cet_award_training.csv`

- Outputs (by `cet_award_training_dataset` asset):
  - `data/processed/cet_award_training.parquet` (preferred)
  - Companion checks:
    - `data/processed/cet_award_training.checks.json`
  - NDJSON fallback (when parquet engine unavailable):
    - `data/processed/cet_award_training.ndjson`
    - A zero-byte parquet placeholder file is also created to keep downstream checks stable

- Parquet engines:
  - Requires `pyarrow` or `fastparquet`. Without a parquet engine, a NDJSON fallback is written and a placeholder parquet file is touched.

---

## Canonical Schema

The loader accepts flexible inputs but maps them to the following canonical fields for `TrainingExample`:

- `example_id` (string; or inferred from row index if missing)
- `text` (string; built deterministically from `title + abstract + keywords + solicitation`)
- `title` (optional string)
- `keywords` (optional string; comma-joined)
- `solicitation` (optional string)
- `labels` (list[str]; CET IDs)
- `source` (string; default `"bootstrap"`)
- `annotated_by` (optional string)
- `annotated_at` (optional ISO 8601 datetime)
- `notes` (optional string)

And wraps them in a `TrainingDataset`:
- `dataset_id` (default is derived from filename + UTC date)
- `taxonomy_version` (required: e.g., `NSTC-2025Q1`)
- `created_at` (auto-set)
- `description` (optional)
- `split` (optional, e.g., `train`, `val`, `test`)

---

## Column Mapping & Auto-Detection

By default, the loader tries to resolve columns using the following candidates:

- `example_id`: `example_id`, `award_id`, `id`
- `title`: `title`, `project_title`
- `abstract`: `abstract`, `project_abstract`, `summary`
- `keywords`: `keywords`, `keyword`, `key_words`
- `solicitation`: `solicitation`, `topic`, `topic_title`
- `labels`: `cet_labels`, `labels`, `label`, `cet_ids`
- `source`: `source`, `label_source`
- `annotated_by`: `annotated_by`, `labeler`, `annotator`
- `annotated_at`: `annotated_at`, `labeled_at`, `timestamp`
- `notes`: `notes`, `comments`

You can override detection with an explicit mapping:
- `{"example_id": "award_id", "title": "project_title", "labels": "cet_labels", ...}`

---

## Label Parsing

- Accepts:
  - list/tuple/set of strings
  - delimited strings (`,`, `;`, `|`)
- Normalization:
  - Lower-cased, spaces and hyphens converted to underscores
  - Deduplicated while preserving order
- Rows with no labels are skipped (tracked in loader stats)
- Example normalized labels: `["artificial_intelligence", "quantum_information_science"]`

---

## Keyword Parsing

- Accepts:
  - list/tuple/set of strings
  - delimited strings (`,`, `;`, `|`)
- Stored as a comma-joined string in output tables for portability

---

## Combined Training Text

For each row, `text` is deterministically composed by concatenating:

1) `title`
2) `abstract`
3) `keywords` (space-joined)
4) `solicitation`

Empty values are skipped. This provides consistent training inputs for the text-based pipeline.

---

## NDJSON Example

Each line represents one labeled example. Minimal fields shown here:

```json
{"example_id":"award-000001","title":"AI for medical imaging","abstract":"We apply deep learning to radiology images...","keywords":["deep learning","neural networks","radiology"],"labels":["artificial_intelligence"],"source":"manual","annotated_by":"annotator_1","annotated_at":"2025-01-15T12:34:56Z"}
{"example_id":"award-000002","title":"Quantum algorithms for optimization","abstract":"We explore qubit coherence and variational methods...","keywords":"quantum computing; qubits; optimization","labels":"quantum_information_science, artificial_intelligence"}
```

CSV is also supported with equivalent columns.

---

## Dagster Asset

Asset: `cet_award_training_dataset`

Behavior:
- Searches for training data under the input paths listed above (processed first, then raw)
- Loads via `AwardTrainingLoader`
- Persists to `data/processed/cet_award_training.parquet` (or NDJSON fallback)
- Writes companion checks to `data/processed/cet_award_training.checks.json` with:
  - `ok`: bool
  - `rows`: int
  - `input_path`: string or null
  - `taxonomy_version`: string
  - `stats`: loader counters (total, loaded, skipped, label histogram)
- If no input is found:
  - Writes empty output and a checks JSON with `ok=false` and `reason="training_data_missing"`

CI Tips:
- Use path filters to run this asset only when `data/**/cet_award_training.*` changes.
- Upload the checks JSON as a build artifact for PR feedback.

---

## Programmatic Usage

Python (CSV):

```python
from pathlib import Path
from src.ml.data.award_training_loader import AwardTrainingLoader

loader = AwardTrainingLoader(
    taxonomy_version="NSTC-2025Q1",
    dataset_id="bootstrap-annotated-awards",
    description="Bootstrap training set of 1,000+ annotated SBIR awards",
)

dataset = loader.load_csv(
    Path("data/processed/cet_award_training.csv"),
    mapping={
        "example_id": "award_id",
        "title": "project_title",
        "abstract": "project_abstract",
        "keywords": "keywords",
        "solicitation": "solicitation",
        "labels": "cet_labels",
    },
)
print(f"Loaded {len(dataset)} examples for taxonomy {dataset.taxonomy_version}")
```

Python (NDJSON):

```python
from pathlib import Path
from src.ml.data.award_training_loader import load_training_dataset

dataset = load_training_dataset(
    Path("data/processed/cet_award_training.ndjson"),
    taxonomy_version="NSTC-2025Q1",
)
```

Persisting to NDJSON for portability:

```python
from pathlib import Path
from src.ml.data.award_training_loader import save_dataset_ndjson, save_dataset_metadata_json

out_data = Path("data/processed/cet_award_training_clean.ndjson")
out_meta = Path("data/processed/cet_award_training_clean.metadata.json")

save_dataset_ndjson(dataset, out_data)
save_dataset_metadata_json(dataset, out_meta)
```

---

## Training Next Steps

To train the CET classifier using the `TrainingDataset`:

```python
from pathlib import Path
from src.ml.config.taxonomy_loader import TaxonomyLoader
from src.ml.models.trainer import CETModelTrainer

# 1) Load taxonomy and classification config
loader = TaxonomyLoader()
taxonomy = loader.load_taxonomy()
classification_cfg = loader.load_classification_config()
cet_areas = list(taxonomy.cet_areas)
taxonomy_version = taxonomy.version

# 2) Prepare trainer
trainer = CETModelTrainer(
    cet_areas=cet_areas,
    config=classification_cfg,
    taxonomy_version=taxonomy_version,
)

# 3) Prepare data
X_train, y_train, X_test, y_test = trainer.prepare_data(dataset)

# 4) Train (CV + calibration are configurable inside trainer)
model = trainer.train(dataset, perform_cv=True, perform_calibration=True)

# 5) Persist model and metrics
model_path = Path("artifacts/models/cet_classifier_v1.pkl")
trainer.save_model(model, model_path)
print(trainer.generate_report())
```

Outputs:
- `artifacts/models/cet_classifier_v1.pkl`
- `artifacts/models/cet_classifier_v1_metrics.json` (saved by `trainer.save_model` when enabled)

---

## Checks & Validation

- Rows without labels are skipped (reported in checks as `rows_skipped_no_labels`)
- Labels are normalized to lowercase with underscores
- Datetime fields are parsed best-effort (`ISO 8601`, `%Y-%m-%d`, `%m/%d/%Y`)
- The combined text always follows the same composition order for determinism
- The checks JSON includes a label histogram to spot distribution issues quickly

---

## Common Issues

- “Parquet engine unavailable”: Install `pyarrow` or rely on NDJSON fallback.
- “Empty dataset”: Ensure at least one labeled row is present; rows without labels are dropped.
- “Unexpected columns”: Provide an explicit `mapping` to align your schema with canonical fields.
- “Label drift”: Keep labels aligned with the taxonomy CET IDs and normalize to underscores.

---

## Summary

- Place your labeled training file at one of the recommended input paths
- Use `cet_award_training_dataset` to persist a clean, schema-stable output for the rest of the pipeline
- The loader provides flexible schema mapping, robust label/keyword parsing, and deterministic text construction
- Proceed to model training with `CETModelTrainer` and persist the artifact at `artifacts/models/cet_classifier_v1.pkl`

"""CET training assets.

This module contains:
- train_cet_patent_classifier: Train and persist patent CET classifier
- cet_award_training_dataset: Generate training dataset for award classifier
"""

from __future__ import annotations

import json
from pathlib import Path

from sbir_ml.ml.config.taxonomy_loader import TaxonomyLoader
from .utils import Output, asset, save_dataframe_parquet


@asset(
    name="train_cet_patent_classifier",
    key_prefix=["ml"],
    description=(
        "Train and persist a Patent CET classifier artifact at "
        "`artifacts/models/patent_classifier_v1.pkl`. Emits a companion checks JSON "
        "with training metadata. Missing prerequisites fail the materialization."
    ),
)
def train_cet_patent_classifier() -> Output:
    """Train the patent classifier, failing unless a real model artifact is created."""
    model_path = Path("artifacts/models/patent_classifier_v1.pkl")
    checks_path = model_path.with_suffix(".checks.json")
    train_data_parquet = Path("data/processed/cet_patent_training.parquet")
    train_data_ndjson = train_data_parquet.with_suffix(".ndjson")

    try:
        import pandas as pd
    except Exception as exc:
        raise RuntimeError("pandas is required to train the CET patent classifier") from exc

    try:
        from sbir_ml.ml.features.patent_features import get_keywords_map
        from sbir_ml.ml.models.dummy_pipeline import DummyPipeline
        from sbir_ml.ml.train.patent_training import train_patent_classifier
    except Exception as exc:
        raise RuntimeError("CET patent training dependencies are unavailable") from exc

    if not train_data_parquet.exists() and not train_data_ndjson.exists():
        raise FileNotFoundError(
            f"CET patent training data not found at {train_data_parquet} or {train_data_ndjson}"
        )

    if train_data_parquet.exists():
        try:
            df = pd.read_parquet(train_data_parquet)
        except Exception as exc:
            if not train_data_ndjson.exists():
                raise RuntimeError(f"Failed to read training data: {train_data_parquet}") from exc
            records = []
            with open(train_data_ndjson, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        records.append(json.loads(line))
            df = pd.DataFrame(records)
    else:
        records = []
        with open(train_data_ndjson, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records.append(json.loads(line))
        df = pd.DataFrame(records)

    if df is None or len(df) == 0:
        raise ValueError("CET patent training data is empty")

    # Provide a simple pipelines factory using DummyPipeline with CET id as keyword cue
    def _factory(cet_id: str):
        # Heuristic: derive a token from CET id for keyword; this keeps CI deterministic
        kw = cet_id.replace("_", " ")
        return DummyPipeline(cet_id=cet_id, keywords=[kw], keyword_boost=1.0)

    try:
        meta = train_patent_classifier(
            df=df,
            output_model_path=model_path,
            pipelines_factory=_factory,
            title_col="title",
            assignee_col="assignee" if "assignee" in df.columns else None,
            cet_label_col="cet_labels",
            use_feature_extraction=True,
            keywords_map={k: list(v) for k, v in get_keywords_map().items()}
            if get_keywords_map()
            else None,  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise RuntimeError("CET patent classifier training failed") from exc

    if not model_path.exists():
        raise RuntimeError(f"Training completed without creating model artifact: {model_path}")

    checks = {
        "ok": True,
        "model_path": str(model_path),
        "trained_on_rows": meta.get("trained_on_rows", 0),
    }

    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "model_path": str(model_path),
        "checks_path": str(checks_path),
        "trained": True,
    }
    return Output(value=str(model_path), metadata=metadata)  # type: ignore[arg-type]


# New asset: cet_award_training_dataset
@asset(
    name="cet_award_training_dataset",
    key_prefix=["ml"],
    description=(
        "Load labeled CET award training dataset with required `text` and `labels` columns "
        "from CSV or NDJSON, validate and persist to "
        "`data/processed/cet_award_training.parquet` and emit a companion checks JSON. "
        "The returned path always identifies the artifact that was actually written."
    ),
)
def cet_award_training_dataset() -> Output:
    """Validate labeled award examples and persist a real training artifact."""
    output_path = Path("data/processed/cet_award_training.parquet")
    checks_path = output_path.with_suffix(".checks.json")

    # Candidate input paths (prefer processed)
    candidate_inputs = [
        Path("data/processed/cet_award_training.ndjson"),
        Path("data/processed/cet_award_training.jsonl"),
        Path("data/processed/cet_award_training.csv"),
        Path("data/raw/cet_award_training.ndjson"),
        Path("data/raw/cet_award_training.jsonl"),
        Path("data/raw/cet_award_training.csv"),
    ]
    input_path = next((p for p in candidate_inputs if p.exists()), None)

    try:
        loader = TaxonomyLoader()
        taxonomy = loader.load_taxonomy()
        taxonomy_version = taxonomy.version
    except Exception as exc:
        raise RuntimeError("Failed to load the CET taxonomy for award training data") from exc

    if input_path is None:
        expected = ", ".join(str(path) for path in candidate_inputs)
        raise FileNotFoundError(f"CET award training data not found; checked: {expected}")

    try:
        import pandas as pd

        if input_path.suffix.lower() in (".ndjson", ".jsonl"):
            records = []
            with input_path.open(encoding="utf-8") as fh:
                for line_number, line in enumerate(fh, start=1):
                    if not line.strip():
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid JSON in {input_path} at line {line_number}"
                        ) from exc
            df = pd.DataFrame(records)
        elif input_path.suffix.lower() == ".csv":
            df = pd.read_csv(input_path)
        else:  # pragma: no cover - candidates above constrain extensions
            raise ValueError(f"Unsupported CET award training format: {input_path.suffix}")
    except Exception as exc:
        raise RuntimeError(f"Failed to load CET award training data: {input_path}") from exc

    if df.empty:
        raise ValueError(f"CET award training data is empty: {input_path}")

    required_columns = {"text", "labels"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"CET award training data is missing required columns: {missing}")

    if "taxonomy_version" not in df.columns:
        df["taxonomy_version"] = taxonomy_version

    artifact_path = save_dataframe_parquet(df, output_path)

    checks = {
        "ok": True,
        "rows": len(df),
        "input_path": str(input_path),
        "taxonomy_version": taxonomy_version,
        "columns": sorted(df.columns.tolist()),
    }
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "path": str(artifact_path),
        "rows": len(df),
        "checks_path": str(checks_path),
        "input_path": str(input_path),
        "taxonomy_version": taxonomy_version,
    }
    return Output(value=str(artifact_path), metadata=metadata)  # type: ignore[arg-type]

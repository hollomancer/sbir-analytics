"""CET training assets.

This module contains:
- train_cet_patent_classifier: Train and persist patent CET classifier
- cet_award_training_dataset: Generate training dataset for award classifier
"""

from __future__ import annotations

import json
from pathlib import Path

from ...ml.config.taxonomy_loader import TaxonomyLoader
from .utils import Output, asset, save_dataframe_parquet


@asset(
    name="train_cet_patent_classifier",
    key_prefix=["ml"],
    description=(
        "Train and persist a Patent CET classifier artifact at "
        "`artifacts/models/patent_classifier_v1.pkl`. Emits a companion checks JSON "
        "with training metadata. If training data or dependencies are missing, "
        "writes a minimal checks file and returns the intended model path."
    ),
)
def train_cet_patent_classifier() -> Output:
    """
    Dagster asset that trains the PatentCETClassifier from a labeled dataset.

    Behavior (import-safe):
    - Expects a labeled training dataset at `data/processed/cet_patent_training.parquet`
      with columns: `title`, `cet_labels` (iterable[str] or comma-delimited), and optional `assignee`.
    - When training data or pandas is missing, writes a checks JSON with ok=False and
      returns the model path without creating the artifact.
    """

    model_path = Path("artifacts/models/patent_classifier_v1.pkl")
    checks_path = model_path.with_suffix(".checks.json")
    train_data_parquet = Path("data/processed/cet_patent_training.parquet")

    try:
        import pandas as pd
    except Exception:
        # Missing pandas; write checks and exit
        checks = {"ok": False, "reason": "pandas_missing", "model_path": str(model_path)}
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return Output(
            value=str(model_path), metadata={"model_path": str(model_path), "trained": False}
        )

    # Attempt to import training helper and dummy pipeline for simple factory
    try:
        from src.ml.features.patent_features import get_keywords_map
        from src.ml.models.dummy_pipeline import DummyPipeline
        from src.ml.train.patent_training import train_patent_classifier
    except Exception:
        checks = {"ok": False, "reason": "training_helper_missing", "model_path": str(model_path)}
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return Output(
            value=str(model_path), metadata={"model_path": str(model_path), "trained": False}
        )

    if not train_data_parquet.exists():
        checks = {
            "ok": False,
            "reason": "training_data_missing",
            "expected_path": str(train_data_parquet),
            "model_path": str(model_path),
        }
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return Output(
            value=str(model_path), metadata={"model_path": str(model_path), "trained": False}
        )

    # Load training data
    try:
        df = pd.read_parquet(train_data_parquet)
    except Exception:
        # Try NDJSON fallback
        ndjson_path = train_data_parquet.with_suffix(".ndjson")
        records = []
        if ndjson_path.exists():
            with open(ndjson_path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        records.append(json.loads(line))
        df = pd.DataFrame(records)

    if df is None or len(df) == 0:
        checks = {
            "ok": False,
            "reason": "empty_training_data",
            "model_path": str(model_path),
            "rows": 0,
        }
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        return Output(
            value=str(model_path), metadata={"model_path": str(model_path), "trained": False}
        )

    # Provide a simple pipelines factory using DummyPipeline with CET id as keyword cue
    def _factory(cet_id: str):
        # Heuristic: derive a token from CET id for keyword; this keeps CI deterministic
        kw = cet_id.replace("_", " ")
        return DummyPipeline(cet_id=cet_id, keywords=[kw], keyword_boost=1.0)

    # Train and persist
    try:
        meta = train_patent_classifier(
            df=df,
            output_model_path=model_path,
            pipelines_factory=_factory,
            title_col="title",
            assignee_col="assignee" if "assignee" in df.columns else None,
            cet_label_col="cet_labels",
            use_feature_extraction=True,
            keywords_map=get_keywords_map(),
        )
        checks = {
            "ok": True,
            "model_path": str(model_path),
            "trained_on_rows": meta.get("trained_on_rows", 0),
        }
    except Exception as e:
        checks = {
            "ok": False,
            "reason": "training_failed",
            "error": str(e),
            "model_path": str(model_path),
        }

    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "model_path": str(model_path),
        "checks_path": str(checks_path),
        "trained": checks.get("ok", False),
    }
    return Output(value=str(model_path), metadata=metadata)  # type: ignore[arg-type]


# New asset: cet_award_training_dataset
@asset(
    name="cet_award_training_dataset",
    key_prefix=["ml"],
    description=(
        "Load labeled CET award training dataset from CSV or NDJSON, validate and persist to "
        "`data/processed/cet_award_training.parquet` and emit a companion checks JSON. "
        "Import-safe with NDJSON fallback when parquet engine or pandas is unavailable."
    ),
)
def cet_award_training_dataset() -> Output:
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

    # Load taxonomy for metadata
    loader = TaxonomyLoader()
    try:
        taxonomy = loader.load_taxonomy()
        taxonomy_version = taxonomy.version
    except Exception:
        taxonomy = None
        taxonomy_version = None

    # If no input, write empty output and checks
    if input_path is None:
        try:
            import pandas as pd

            df_empty = pd.DataFrame(
                columns=[
                    "example_id",
                    "text",
                    "title",
                    "keywords",
                    "keywords_joined",
                    "solicitation",
                    "labels",
                    "labels_joined",
                    "source",
                    "annotated_by",
                    "annotated_at",
                    "notes",
                    "taxonomy_version",
                ]
            )
            save_dataframe_parquet(df_empty, output_path)
        except Exception:
            # Ensure a placeholder parquet file exists and write empty NDJSON
            out_json = output_path.with_suffix(".ndjson")
            out_json.parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w", encoding="utf-8") as fh:
                fh.write("")
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()
            except Exception:
                pass

        checks = {
            "ok": False,
            "reason": "training_data_missing",
            "expected_paths": [str(p) for p in candidate_inputs],
            "rows": 0,
            "taxonomy_version": taxonomy_version,
        }
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        metadata = {
            "path": str(output_path),
            "rows": 0,
            "checks_path": str(checks_path),
            "input_path": None,
            "taxonomy_version": taxonomy_version,
        }
        return Output(value=str(output_path), metadata=metadata)  # type: ignore[arg-type]

    # Load dataset using the training loader
    try:
        from src.ml.data.award_training_loader import AwardTrainingLoader, save_dataset_ndjson

        atl = AwardTrainingLoader(taxonomy_version=taxonomy_version or "unknown")
        # Dispatch based on extension
        if input_path.suffix.lower() in (".ndjson", ".jsonl"):
            dataset = atl.load_ndjson(input_path)
        elif input_path.suffix.lower() == ".csv":
            dataset = atl.load_csv(input_path)
        else:
            # Try CSV then NDJSON as fallback
            try:
                dataset = atl.load_csv(input_path)
            except Exception:
                dataset = atl.load_ndjson(input_path)
        stats = atl.last_stats.as_dict() if getattr(atl, "last_stats", None) else {}
    except Exception as e:
        # Failed to load training dataset; write checks and empty output
        try:
            import pandas as pd

            df_empty = pd.DataFrame(
                columns=[
                    "example_id",
                    "text",
                    "title",
                    "keywords",
                    "keywords_joined",
                    "solicitation",
                    "labels",
                    "labels_joined",
                    "source",
                    "annotated_by",
                    "annotated_at",
                    "notes",
                    "taxonomy_version",
                ]
            )
            save_dataframe_parquet(df_empty, output_path)
        except Exception:
            out_json = output_path.with_suffix(".ndjson")
            out_json.parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w", encoding="utf-8") as fh:
                fh.write("")
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()
            except Exception:
                pass

        checks = {
            "ok": False,
            "reason": "load_failed",
            "error": str(e),
            "input_path": str(input_path),
            "taxonomy_version": taxonomy_version,
        }
        checks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(checks_path, "w", encoding="utf-8") as fh:
            json.dump(checks, fh, indent=2)
        metadata = {
            "path": str(output_path),
            "rows": 0,
            "checks_path": str(checks_path),
            "input_path": str(input_path),
            "taxonomy_version": taxonomy_version,
        }
        return Output(value=str(output_path), metadata=metadata)  # type: ignore[arg-type]

    # Persist dataset to parquet (preferred) with NDJSON fallback
    try:
        import pandas as pd

        rows = []
        for ex in dataset.examples:
            rows.append(
                {
                    "example_id": ex.example_id,
                    "text": ex.text,
                    "title": ex.title,
                    "keywords": ex.keywords,
                    "keywords_joined": (ex.keywords or ""),
                    "solicitation": ex.solicitation,
                    "labels": ex.labels,
                    "labels_joined": ", ".join(ex.labels or []),
                    "source": ex.source,
                    "annotated_by": ex.annotated_by,
                    "annotated_at": ex.annotated_at.isoformat() if ex.annotated_at else None,
                    "notes": ex.notes,
                    "taxonomy_version": dataset.taxonomy_version,
                }
            )
        df = pd.DataFrame(rows)
        save_dataframe_parquet(df, output_path)
    except Exception:
        # Fallback to NDJSON using helper
        try:
            out_json = output_path.with_suffix(".ndjson")
            save_dataset_ndjson(dataset, out_json)
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()
            except Exception:
                pass
        except Exception:
            # As a last resort, write minimal NDJSON manually
            out_json = output_path.with_suffix(".ndjson")
            out_json.parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w", encoding="utf-8") as fh:
                for ex in dataset.examples:
                    fh.write(
                        json.dumps(
                            {
                                "example_id": ex.example_id,
                                "text": ex.text,
                                "labels": ex.labels,
                            }
                        )
                        + "\n"
                    )
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.touch()
            except Exception:
                pass

    # Build checks JSON
    checks = {
        "ok": True,
        "rows": len(dataset.examples),
        "input_path": str(input_path),
        "taxonomy_version": dataset.taxonomy_version,
        "stats": stats if isinstance(stats, dict) else {},
    }
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checks_path, "w", encoding="utf-8") as fh:
        json.dump(checks, fh, indent=2)

    metadata = {
        "path": str(output_path),
        "rows": len(dataset.examples),
        "checks_path": str(checks_path),
        "input_path": str(input_path),
        "taxonomy_version": dataset.taxonomy_version,
    }
    return Output(value=str(output_path), metadata=metadata)  # type: ignore[arg-type]

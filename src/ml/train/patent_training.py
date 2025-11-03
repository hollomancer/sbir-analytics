"""
sbir-etl/src/ml/train/patent_training.py

Helper routines to train and persist a PatentCETClassifier from a labeled
DataFrame. Keeps Dagster assets thin and enables unit tests to call training
logic directly.

Capabilities:
- Train per-CET pipelines using a small, import-safe pathway
- Optional lightweight feature extraction for consistent training inputs
- Optional basic evaluation utilities (precision@k, recall@k) on validation data
- Persist model artifact and return training metadata
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

# pandas is optional at import-time; fail only when training is invoked
try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - optional import
    pd = None  # type: ignore

# Core classifier and optional feature extractor
try:
    from src.ml.models.patent_classifier import (
        PatentCETClassifier,
        PatentClassification,
        PatentFeatureExtractor,
    )
except Exception as e:  # pragma: no cover
    raise RuntimeError("Required module src.ml.models.patent_classifier is not available") from e

logger = logging.getLogger(__name__)


def _ensure_pandas() -> None:
    if pd is None:  # type: ignore
        raise RuntimeError("pandas is required for patent classifier training")


def _normalize_labels_column(df: pd.DataFrame, cet_label_col: str) -> list[set[str]]:
    """
    Coerce the labels column to a list of sets of strings.
    """
    labels: list[set[str]] = []
    for v in df[cet_label_col].tolist():
        if v is None:
            labels.append(set())
        elif isinstance(v, list | tuple | set):
            labels.append({str(x) for x in v})
        else:
            # Accept delimited strings like "a,b,c"
            s = str(v).strip()
            if not s:
                labels.append(set())
            else:
                labels.append({p.strip() for p in s.split(",")})
    return labels


def build_training_inputs(
    df: pd.DataFrame,
    *,
    title_col: str = "title",
    assignee_col: str | None = None,
    use_feature_extraction: bool = True,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Produce training inputs from a DataFrame:
    - texts: list[str] to pass to pipelines (normalized title + assignee hint)
    - features: list[feature-dicts] primarily for debugging or advanced pipelines

    If feature extraction is disabled or unavailable, falls back to normalized titles only.
    """
    _ensure_pandas()

    titles: list[str] = []
    features: list[dict[str, Any]] = []

    # Prefer the extractor for consistent normalization and small additional signal
    if use_feature_extraction:
        try:
            extractor = PatentFeatureExtractor()
            texts, feature_vectors = extractor.features_for_dataframe(
                df, title_col=title_col, assignee_col=assignee_col
            )
            # Convert feature vectors to plain dicts for portability/debugging
            for fv in feature_vectors:
                try:
                    features.append(fv.as_dict())  # type: ignore[attr-defined]
                except Exception:
                    # Minimal fallback dict if PatentFeatureVector.as_dict isn't available
                    d = {
                        "normalized_title": getattr(fv, "normalized_title", ""),
                        "assignee_type": getattr(fv, "assignee_type", "unknown"),
                    }
                    features.append(d)
            titles = texts
            return titles, features
        except Exception:
            logger.exception("Feature extraction failed; falling back to raw title text")

    # Fallback: normalized title strings only
    titles = df[title_col].fillna("").astype(str).str.lower().tolist()
    features = [{"normalized_title": t} for t in titles]
    return titles, features


def train_patent_classifier(
    df: pd.DataFrame,
    output_model_path: Path,
    pipelines_factory: Callable[[str], Any],
    *,
    title_col: str = "title",
    assignee_col: str | None = None,
    cet_label_col: str = "cet_labels",
    use_feature_extraction: bool = True,
    keywords_map: dict[str, list[str]] | None = None,
    taxonomy_version: str | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """
    Train a PatentCETClassifier and persist it to output_model_path.

    Parameters
    ----------
    df : pd.DataFrame
        Labeled training dataset. Must include `title_col` and `cet_label_col`.
    output_model_path : Path
        Where to save the trained model artifact (pickle).
    pipelines_factory : Callable[[str], Any]
        Factory returning a binary pipeline instance for a given CET id.
    title_col : str
        Column name for patent title text.
    assignee_col : Optional[str]
        Optional column for assignee/owner, used for small additional signal in text.
    cet_label_col : str
        Column name for label sets per row (iterable[str] or delimited string).
    use_feature_extraction : bool
        Whether to leverage the lightweight feature extractor to produce normalized
        texts for training.
    keywords_map : Optional[Dict[str, List[str]]]
        Optional keyword map passed through to feature extraction; used when your
        extractor relies on custom keywords (safe to leave None).
    taxonomy_version : Optional[str]
        CET taxonomy version string to embed as metadata.
    model_version : Optional[str]
        Model version string to embed as metadata.

    Returns
    -------
    Dict[str, Any]
        Training metadata, including artifact path, training date, and counts.
    """
    _ensure_pandas()

    if df is None or len(df) == 0:
        raise ValueError("Training DataFrame is empty or None")

    missing_cols = [c for c in [title_col, cet_label_col] if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Training DataFrame missing required columns: {missing_cols}")

    # Prepare labels
    _normalize_labels_column(df, cet_label_col)

    # Instantiate classifier
    classifier = PatentCETClassifier(
        pipelines={},
        taxonomy_version=taxonomy_version,
        config={"model_version": model_version} if model_version else {},
    )

    # Train
    classifier.train_from_dataframe(
        df=df,
        title_col=title_col,
        assignee_col=assignee_col,
        cet_label_col=cet_label_col,
        pipelines_factory=pipelines_factory,
        use_feature_extraction=use_feature_extraction,
        keywords_map=keywords_map,
    )

    # Persist
    output_model_path = Path(output_model_path)
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    classifier.save(output_model_path)

    meta = classifier.get_metadata()
    meta.update(
        {
            "path": str(output_model_path),
            "trained_on_rows": int(len(df)),
            "trained_at": datetime.utcnow().isoformat(),
        }
    )
    return meta


# ------------------------------
# Basic evaluation (optional)
# ------------------------------
def precision_recall_at_k(
    y_true: Sequence[set[str]],
    y_pred_ranked: Sequence[Sequence[PatentClassification]],
    *,
    k: int = 1,
) -> dict[str, float]:
    """
    Compute simple micro-averaged precision@k and recall@k for multi-label classification.

    - y_true: iterable of sets of true CET IDs per record
    - y_pred_ranked: iterable of ranked predictions (PatentClassification) per record
    """
    if k <= 0:
        raise ValueError("k must be >= 1")

    total_pred = 0
    total_true = 0
    total_correct = 0

    for true_set, preds in zip(y_true, y_pred_ranked, strict=False):
        topk = [p.cet_id for p in (preds[:k] if preds else [])]
        pred_set = set(topk)
        true_labels = set(true_set or [])
        total_pred += len(pred_set)
        total_true += len(true_labels)
        total_correct += len(pred_set.intersection(true_labels))

    precision = (total_correct / total_pred) if total_pred > 0 else 0.0
    recall = (total_correct / total_true) if total_true > 0 else 0.0
    return {"precision_at_k": precision, "recall_at_k": recall}


def evaluate_patent_classifier(
    classifier: PatentCETClassifier,
    df_eval: pd.DataFrame,
    *,
    title_col: str = "title",
    assignee_col: str | None = None,
    cet_label_col: str = "cet_labels",
    k_values: Sequence[int] = (1, 3),
    batch_size: int = 1000,
) -> dict[str, Any]:
    """
    Evaluate a trained classifier on a labeled evaluation DataFrame.

    Returns a dict of metrics for the provided k_values.
    """
    _ensure_pandas()

    if df_eval is None or len(df_eval) == 0:
        return {"ok": False, "reason": "empty_eval"}

    texts = df_eval[title_col].fillna("").astype(str).tolist()
    assignees = (
        df_eval[assignee_col].tolist() if assignee_col and assignee_col in df_eval.columns else None
    )
    y_true = _normalize_labels_column(df_eval, cet_label_col)

    y_pred = classifier.classify_batch(
        titles=texts, assignees=assignees, batch_size=batch_size, top_k=max(k_values or [1])
    )

    metrics: dict[str, Any] = {"ok": True, "n": int(len(df_eval))}
    for k in k_values:
        m = precision_recall_at_k(y_true, y_pred, k=k)
        metrics.update(
            {f"precision_at_{k}": m["precision_at_k"], f"recall_at_{k}": m["recall_at_k"]}
        )
    return metrics


def train_and_evaluate(
    df_train: pd.DataFrame,
    df_eval: pd.DataFrame | None,
    output_model_path: Path,
    pipelines_factory: Callable[[str], Any],
    *,
    title_col: str = "title",
    assignee_col: str | None = None,
    cet_label_col: str = "cet_labels",
    use_feature_extraction: bool = True,
    keywords_map: dict[str, list[str]] | None = None,
    taxonomy_version: str | None = None,
    model_version: str | None = None,
    k_values: Sequence[int] = (1, 3),
) -> dict[str, Any]:
    """
    Convenience wrapper: train and optionally evaluate, returning merged metadata.

    If df_eval is provided and non-empty, computes precision/recall@k and
    stores metrics in the returned metadata dict.
    """
    train_meta = train_patent_classifier(
        df=df_train,
        output_model_path=output_model_path,
        pipelines_factory=pipelines_factory,
        title_col=title_col,
        assignee_col=assignee_col,
        cet_label_col=cet_label_col,
        use_feature_extraction=use_feature_extraction,
        keywords_map=keywords_map,
        taxonomy_version=taxonomy_version,
        model_version=model_version,
    )

    if df_eval is not None and len(df_eval) > 0:
        # Load back the classifier to simulate production scoring path
        clf = PatentCETClassifier.load(Path(train_meta["path"]))
        eval_metrics = evaluate_patent_classifier(
            clf,
            df_eval,
            title_col=title_col,
            assignee_col=assignee_col,
            cet_label_col=cet_label_col,
            k_values=k_values,
        )
        train_meta["evaluation"] = eval_metrics
    else:
        train_meta["evaluation"] = {"ok": False, "reason": "no_eval_provided"}

    return train_meta

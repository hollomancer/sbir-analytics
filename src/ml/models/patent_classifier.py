# sbir-analytics/src/ml/models/patent_classifier.py
"""
PatentCETClassifier

Lightweight, import-safe classifier wrapper for assigning CET areas to patent
records (titles + assignee hints). This is a smaller, focused analogue of the
award ApplicabilityModel used for patents.

Design goals
- Keep implementation minimal and robust for CI/unit tests (no heavy optional deps at import time).
- Accept pre-built per-CET binary pipelines (e.g., `DummyPipeline`) that implement
  a `predict_proba(List[str]) -> np.ndarray` interface returning shape (n, 2)
  (columns: [neg_prob, pos_prob]).
- Provide train/save/load/classify utilities suitable for tests and small-scale runs.
- Persist artifacts as a pickleable dict containing pipelines and metadata.

Notes
- This module intentionally avoids importing large optional packages at module
  import time. Pandas is used defensively inside functions only when available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


# Defensive imports (may be None in minimal CI environments)
try:
    import numpy as np
except Exception:  # pragma: no cover - defensive import
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover - defensive import
    pd = None  # type: ignore

import pickle  # nosec B403 - Used for loading internally-generated ML model files

from src.exceptions import CETClassificationError, DependencyError, FileSystemError, ValidationError


# Define optional placeholders so static analysis doesn't flag undefined names before lazy import
extract_features = None
PatentFeatureVector = None

# Feature helpers are optional and may already have been imported above.
# Attempt a local import to ensure names exist when the features module is
# available, but do not raise if it's missing in minimal CI environments.
try:
    from src.ml.features.patent_features import PatentFeatureVector as _PatentFeatureVector
    from src.ml.features.patent_features import extract_features as _extract_features

    # Populate module-level names only if not already present or None
    if "extract_features" not in globals() or extract_features is None:
        extract_features = _extract_features
    if "PatentFeatureVector" not in globals() or PatentFeatureVector is None:
        PatentFeatureVector = _PatentFeatureVector
except Exception:
    # Optional feature module not available; keep extract_features / PatentFeatureVector as None
    pass

try:
    from src.ml.features.vectorizers import create_feature_matrix_builder  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional import
    create_feature_matrix_builder = None


class PatentFeatureExtractor:
    """
    Small helper to extract lightweight features/texts from patent DataFrame rows.

    Usage:
        extractor = PatentFeatureExtractor(keywords_map=..., stopwords=...)
        texts, feature_vectors = extractor.features_for_dataframe(df, title_col="title")
    """

    def __init__(self, keywords_map: Any = None, stopwords: Any = None) -> None:
        self.keywords_map = keywords_map
        self.stopwords = stopwords

    def features_for_dataframe(
        self, df: Any, title_col: str = "title", assignee_col: str | None = None
    ) -> tuple[list[str], list[Any]]:
        """
        Given a pandas DataFrame, return a tuple (texts, feature_vectors) where:
          - texts: List[str] suitable to pass to classifier pipelines (combined normalized title + assignee hint)
          - feature_vectors: List[PatentFeatureVector] with extracted structured features

        This method imports pandas locally and raises a RuntimeError if pandas is unavailable.
        """
        # Local import to remain import-safe at module import time
        try:
            pass
        except Exception:
            raise DependencyError(
                "pandas is required for PatentFeatureExtractor.features_for_dataframe",
                dependency_name="pandas",
                component="ml.patent_classifier",
                operation="features_for_dataframe",
                details={"install_command": "poetry install"},
            )

        texts: list[str] = []
        feature_vectors: list[PatentFeatureVector] = [] # type: ignore[valid-type]

        # iterate deterministic order
        for _, row in df.iterrows():
            # pandas.Series has .get; handle mapping-like fallback if needed
            try:
                title = row.get(title_col) if hasattr(row, "get") else row[title_col]
            except Exception:
                title = None

            assignee = None
            if assignee_col:
                try:
                    assignee = row.get(assignee_col) if hasattr(row, "get") else row[assignee_col]
                except Exception:
                    assignee = None

            # Build a minimal record dictionary for feature extraction
            rec = {}
            if title is not None:
                rec["title"] = title
            if assignee is not None:
                rec["assignee"] = assignee
            # Propagate other common metadata if present
            for meta_key in ("ipc", "cpc", "abstract", "application_year"):
                if meta_key in row and row.get(meta_key) is not None:
                    rec[meta_key] = row.get(meta_key)

            # Use the optional extract_features function when available. If the
            # features module is not present (e.g., in minimal CI), fall back to a
            # tiny in-memory feature-like object containing just the normalized title
            # and a basic assignee hint so downstream code can still build training
            # texts.
            if extract_features is None:
                normalized_title = str(rec.get("title", "")).lower()
                assignee_hint = rec.get("assignee") or ""

                class _SimpleFV:
                    def __init__(self, normalized_title: str, assignee_type: str):
                        self.normalized_title = normalized_title
                        self.assignee_type = assignee_type

                pfv = _SimpleFV(normalized_title, assignee_hint)
                feature_vectors.append(pfv)
            else:
                pfv = extract_features(  # type: ignore[assignment,no-redef,valid-type]
                    rec, keywords_map=self.keywords_map, stopwords=self.stopwords
                )
                feature_vectors.append(pfv)  # type: ignore[arg-type]

            # Build pipeline text: normalized title + assignee type (gives lightweight signal)
            parts = [pfv.normalized_title or ""]
            if pfv.assignee_type:
                parts.append(pfv.assignee_type)
            texts.append(" ".join([p for p in parts if p]))

        return texts, feature_vectors


@dataclass
class PatentClassification:
    cet_id: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"cet_id": self.cet_id, "score": float(self.score)}


class PatentCETClassifier:
    """
    Simple multi-CET classifier wrapper for patents.

    Parameters
    ----------
    pipelines: Optional[Dict[str, Any]]
        Mapping CET ID -> binary classifier pipeline object. Each pipeline must
        implement a `predict_proba(texts: List[str]) -> numpy.ndarray` method
        returning shape (n_samples, 2) with columns [neg, pos].
    taxonomy_version: Optional[str]
        Version string for the CET taxonomy these pipelines were trained against.
    config: Optional[dict]
        Optional config dict (e.g., thresholds, model_version) stored as metadata.
    """

    def __init__(
        self,
        pipelines: dict[str, Any] | None = None,
        taxonomy_version: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.pipelines: dict[str, Any] = pipelines.copy() if pipelines else {}
        self.taxonomy_version = taxonomy_version
        self.config = config or {}
        self.model_version = self.config.get("model_version")
        self.training_date = self.config.get("training_date")
        self.is_trained = bool(self.pipelines)
        # Default positive class index for predict_proba output
        self._pos_index = 1

    # -----------------------
    # Training helpers
    # -----------------------
    def train_from_dataframe(
        self,
        df: pd.DataFrame,
        title_col: str = "title",
        assignee_col: str | None = None,
        cet_label_col: str = "cet_labels",
        pipelines_factory: Any | None = None,
        use_feature_extraction: bool = False,
        keywords_map: dict[str, list[str]] | None = None,
        feature_matrix_builder: Any | None = None,
    ) -> None:
        """
        Train per-CET binary pipelines using a labeled DataFrame.

        df:
          - each row corresponds to a patent record with a text field (title) and a
            multi-label column `cet_label_col` containing an iterable of CET ids
            present on that record (can be empty).
        pipelines_factory:
          - Optional callable(cet_id) -> pipeline instance. If omitted and pipelines
            pre-exist for a CET ID, those pipelines will be reused. If neither is
            available, training will raise.

        This is a convenience wrapper that will call `.fit(X, y)` on each pipeline
        with X = list of combined text strings and y = binary labels per CET.
        """
        if pd is None:
            raise DependencyError(
                "pandas is required for train_from_dataframe",
                dependency_name="pandas",
                component="ml.patent_classifier",
                operation="train_from_dataframe",
                details={"install_command": "poetry install"},
            )

        if cet_label_col not in df.columns or title_col not in df.columns:
            raise ValidationError(
                "DataFrame must contain title and cet label columns",
                component="ml.patent_classifier",
                operation="train_from_dataframe",
                details={
                    "required_columns": [title_col, cet_label_col],
                    "available_columns": list(df.columns),
                },
            )

        # Use PatentFeatureExtractor to derive training texts and feature vectors.
        # The pipelines consume text; the extractor normalizes titles and adds simple
        # assignee/keyword signals to the text so pipelines receive consistent inputs.
        extractor = PatentFeatureExtractor(keywords_map=keywords_map)
        texts, feature_vectors = extractor.features_for_dataframe(
            df, title_col=title_col, assignee_col=assignee_col
        )
        # Optionally build a numeric feature matrix for sklearn-style pipelines
        X_matrix = None
        feature_names = None
        if feature_matrix_builder is not None:
            try:
                X_matrix = feature_matrix_builder.fit_transform(feature_vectors)
                if hasattr(feature_matrix_builder, "get_feature_names"):
                    feature_names = feature_matrix_builder.get_feature_names()
            except Exception:
                X_matrix = None
                feature_names = None

        # Convert labels column to list of sets
        labels_series = df[cet_label_col].apply(lambda v: set(v) if v else set())

        # Determine CET universe
        cet_universe = set()
        for s in labels_series:
            cet_universe.update(s)

        if not cet_universe:
            logger.warning("No CET labels found in training data; training aborted")
            return

        # Ensure pipelines exist for each CET
        for cet in cet_universe:
            if cet not in self.pipelines:
                if pipelines_factory is not None:
                    self.pipelines[cet] = pipelines_factory(cet)
                else:
                    raise CETClassificationError(
                        f"No pipeline for CET '{cet}' and no pipelines_factory provided",
                        component="ml.patent_classifier",
                        operation="train_from_dataframe",
                        details={"cet_id": cet, "available_pipelines": list(self.pipelines.keys())},
                    )

        # Train each pipeline with binary labels
        for cet, pipeline in list(self.pipelines.items()):
            # Build binary label vector
            y = [1 if cet in s else 0 for s in labels_series]
            # Prefer numeric matrix if available, else fall back to text
            train_X = X_matrix if "X_matrix" in locals() and X_matrix is not None else texts
            try:
                pipeline.fit(train_X, y)
            except Exception:
                # Fallback: try the alternate representation
                alt_X = (
                    texts
                    if train_X is not texts
                    else (X_matrix if "X_matrix" in locals() else None)
                )
                if alt_X is not None:
                    try:
                        pipeline.fit(alt_X, y)
                    except Exception:
                        logger.exception("Failed to fit pipeline for CET %s", cet)
                        raise
                else:
                    logger.exception("Failed to fit pipeline for CET %s", cet)
                    raise

        self.is_trained = True
        self.training_date = datetime.utcnow().isoformat()
        # Store feature metadata if available
        if feature_names:
            self.config = self.config or {}
            self.config["feature_names"] = list(feature_names)

    # -----------------------
    # Classification
    # -----------------------
    def _ensure_model_ready(self) -> None:
        if not self.pipelines:
            raise CETClassificationError(
                "No pipelines available for classification",
                component="ml.patent_classifier",
                operation="classify",
                details={"is_trained": self.is_trained, "num_pipelines": len(self.pipelines)},
            )

    def _text_from_record(self, title: str, assignee: str | None = None) -> str:
        # Combine title and assignee for extra signal
        parts = [str(title or "")]
        if assignee:
            parts.append(str(assignee or ""))
        return " ".join(p.strip() for p in parts if p)

    def _score_with_pipeline(self, pipeline: Any, texts: list[str]) -> list[float]:
        """
        Invoke `pipeline.predict_proba` if available and normalize to positive-class scores.
        Return list[float] with length == len(texts).
        """
        # Prefer predict_proba, but some test pipelines may offer a different API.
        if hasattr(pipeline, "predict_proba"):
            probs = pipeline.predict_proba(texts)
            # Expect an ndarray-like object; defensively extract pos column
            try:
                if np is not None and isinstance(probs, np.ndarray):
                    pos = probs[:, self._pos_index].astype(float).tolist()
                    return pos
                # Fallback: assume indexable sequences
                return [float(row[self._pos_index]) for row in probs]
            except Exception:
                # Try to be resilient to shape (n,) arrays representing pos scores
                try:
                    return [float(v) for v in probs]
                except Exception:
                    logger.exception("Unexpected predict_proba output format")
                    raise
        # Fallback: try `predict` returning 0/1 and convert to float
        if hasattr(pipeline, "predict"):
            preds = pipeline.predict(texts)
            return [float(bool(p)) for p in preds]
        raise DependencyError(
            "Pipeline does not implement predict_proba or predict",
            dependency_name="pipeline",
            component="ml.patent_classifier",
            operation="_score_with_pipeline",
            details={"pipeline_type": type(pipeline).__name__},
        )

    def classify(
        self, title: str, assignee: str | None = None, top_k: int = 3
    ) -> list[PatentClassification]:
        """
        Classify a single patent (title + optional assignee). Returns a sorted list
        of `PatentClassification` objects ordered by score descending (top_k).
        """
        self._ensure_model_ready()
        text = self._text_from_record(title, assignee)
        # For each pipeline, score the text
        scores: list[tuple[str, float]] = []
        for cet_id, pipe in self.pipelines.items():
            try:
                sc = self._score_with_pipeline(pipe, [text])[0]
            except Exception:
                logger.exception("Scoring failed for CET %s", cet_id)
                sc = 0.0
            scores.append((cet_id, float(sc)))
        # Sort and return top_k as PatentClassification
        scores.sort(key=lambda x: x[1], reverse=True)
        top = [PatentClassification(cet_id=s[0], score=s[1]) for s in scores[:top_k]]
        return top

    def classify_batch(
        self,
        titles: list[str],
        assignees: list[str | None] | None = None,
        batch_size: int = 1000,
        top_k: int = 3,
    ) -> list[list[PatentClassification]]:
        """
        Classify a batch of patent titles. Optionally provide a parallel `assignees`
        list. Returns a list (len==n_inputs) of lists of `PatentClassification` objects.
        """
        n = len(titles)
        if assignees is None:
            assignees = [None] * n
        if len(assignees) != n:
            raise ValidationError(
                "titles and assignees must have the same length",
                component="ml.patent_classifier",
                operation="classify_batch",
                details={"titles_length": n, "assignees_length": len(assignees)},
            )
        # If no pipelines configured, return empty lists per input
        if not self.pipelines:
            return [[] for _ in range(n)]

        # Build combined texts
        texts = [self._text_from_record(t, a) for t, a in zip(titles, assignees, strict=False)]

        # For memory reasons, iterate pipelines and get scores per pipeline
        # Build scores_map: cet_id -> list[float] of length n
        scores_map: dict[str, list[float]] = {}
        for cet_id, pipe in self.pipelines.items():
            try:
                # Score in batches if pipeline is expensive
                if batch_size and batch_size > 0:
                    scores: list[float] = []
                    for i in range(0, n, batch_size):
                        chunk = texts[i : i + batch_size]
                        chunk_scores = self._score_with_pipeline(pipe, chunk)
                        scores.extend([float(s) for s in chunk_scores])
                else:
                    scores = [float(s) for s in self._score_with_pipeline(pipe, texts)]
            except Exception:
                logger.exception("Batch scoring failed for CET %s", cet_id)
                scores = [0.0] * n
            # Ensure correct length
            if len(scores) != n:
                # pad or truncate defensively
                scores = (scores + [0.0] * n)[:n]
            scores_map[cet_id] = scores

        # Convert per-input: for each index, collect (cet_id, score) and pick top_k
        results: list[list[PatentClassification]] = []
        for i in range(n):
            row_scores = [(cet, scores_map[cet][i]) for cet in scores_map.keys()]
            row_scores.sort(key=lambda x: x[1], reverse=True)
            top = [PatentClassification(cet_id=c, score=float(s)) for c, s in row_scores[:top_k]]
            results.append(top)
        return results

    # -----------------------
    # Persistence
    # -----------------------
    def save(self, path: Path) -> None:
        """
        Serialize the classifier to `path` (pickle). The saved object is a dict:
        {
            'pipelines': self.pipelines,
            'taxonomy_version': self.taxonomy_version,
            'config': self.config,
            'model_version': self.model_version,
            'training_date': self.training_date,
            'is_trained': self.is_trained,
        }
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pipelines": self.pipelines,
            "taxonomy_version": self.taxonomy_version,
            "config": self.config,
            "model_version": self.model_version,
            "training_date": self.training_date or datetime.utcnow().isoformat(),
            "is_trained": self.is_trained,
        }
        with open(path, "wb") as fh:
            pickle.dump(payload, fh)

    @classmethod
    def load(cls, path: Path) -> PatentCETClassifier:
        """
        Load a previously saved classifier (pickle) and return an instance.
        """
        path = Path(path)
        if not path.exists():
            raise FileSystemError(
                f"Model file not found: {path}",
                file_path=str(path),
                operation="load_model",
                component="ml.patent_classifier",
            )
        with open(path, "rb") as fh:
            payload = pickle.load(fh)  # nosec B301 - Loading trusted internally-generated model files
        pipelines = payload.get("pipelines", {})
        taxonomy_version = payload.get("taxonomy_version")
        config = payload.get("config", {})
        inst = cls(pipelines=pipelines, taxonomy_version=taxonomy_version, config=config)
        inst.model_version = payload.get("model_version")
        inst.training_date = payload.get("training_date")
        inst.is_trained = bool(payload.get("is_trained", False))
        return inst

    # -----------------------
    # Utilities
    # -----------------------
    def get_metadata(self) -> dict[str, Any]:
        """
        Return metadata about the classifier (useful for checks and asset metadata).
        """
        return {
            "num_pipelines": len(self.pipelines),
            "taxonomy_version": self.taxonomy_version,
            "model_version": self.model_version,
            "training_date": self.training_date,
            "is_trained": self.is_trained,
        }

    def __repr__(self) -> str:
        return (
            f"PatentCETClassifier(num_pipelines={len(self.pipelines)}, "
            f"taxonomy_version={self.taxonomy_version!r}, model_version={self.model_version!r})"
        )

"""
CET (Critical and Emerging Technology) Classification Model.

This module implements a multi-label TF-IDF classification model for identifying
applicable CET technology areas in SBIR/STTR awards, patents, and other documents.

Key components:
- CETAwareTfidfVectorizer: Enhanced TF-IDF with keyword boosting
- ApplicabilityModel: Multi-label classifier with probability calibration
- Multi-threshold classification (High ≥70, Medium 40-69, Low <40)
- Batch processing for efficient classification

Based on the NSTC Critical and Emerging Technologies taxonomy (21 categories).
"""

import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.exceptions import CETClassificationError, FileSystemError, ValidationError
from src.models.cet_models import CETArea, CETClassification, ClassificationLevel


class CETAwareTfidfVectorizer(TfidfVectorizer):
    """
    TF-IDF vectorizer with CET keyword boosting.

    Enhances standard TF-IDF by increasing the weight of CET-specific keywords
    to improve classification accuracy for domain terminology.
    """

    def __init__(
        self, cet_keywords: dict[str, list[str]], keyword_boost_factor: float = 2.0, **kwargs
    ):
        """
        Initialize CET-aware TF-IDF vectorizer.

        Args:
            cet_keywords: Dictionary mapping CET IDs to keyword lists
            keyword_boost_factor: Multiplier for keyword TF-IDF scores (default: 2.0)
            **kwargs: Additional arguments passed to TfidfVectorizer
        """
        super().__init__(**kwargs)
        self.cet_keywords = cet_keywords
        self.keyword_boost_factor = keyword_boost_factor

        # Build flat keyword set for fast lookup
        self.keyword_set = set()
        for keywords in cet_keywords.values():
            self.keyword_set.update(k.lower() for k in keywords)

    def fit_transform(self, raw_documents, y=None):
        """Fit vectorizer and transform documents with keyword boosting."""
        # First, perform standard TF-IDF
        X = super().fit_transform(raw_documents, y)

        # Apply keyword boosting
        return self._apply_keyword_boost(X)

    def transform(self, raw_documents):
        """Transform documents with keyword boosting."""
        X = super().transform(raw_documents)
        return self._apply_keyword_boost(X)

    def _apply_keyword_boost(self, X):
        """
        Apply keyword boosting to TF-IDF matrix.

        Args:
            X: TF-IDF matrix (sparse)

        Returns:
            Boosted TF-IDF matrix
        """
        if not hasattr(self, "vocabulary_"):
            return X

        # Find indices of keyword features
        keyword_indices = []
        for word, idx in self.vocabulary_.items():
            if word.lower() in self.keyword_set:
                keyword_indices.append(idx)

        if not keyword_indices:
            logger.warning("No CET keywords found in vocabulary")
            return X

        # Boost keyword features
        X_boosted = X.copy()
        X_boosted[:, keyword_indices] *= self.keyword_boost_factor

        logger.debug(
            f"Applied keyword boost to {len(keyword_indices)} features "
            f"(factor: {self.keyword_boost_factor})"
        )

        return X_boosted


class ApplicabilityModel:
    """
    Multi-label CET classification model with probability calibration.

    This model classifies text documents into one or more CET technology areas
    using a TF-IDF pipeline with logistic regression and calibrated probabilities.

    Features:
    - Multi-label classification (document can match multiple CET areas)
    - Probability calibration for reliable confidence scores
    - Keyword-aware TF-IDF vectorization
    - Feature selection for dimensionality reduction
    - Batch processing for efficiency
    - Multi-threshold scoring (High/Medium/Low)
    """

    def __init__(
        self,
        cet_areas: list[CETArea],
        config: dict[str, Any],
        taxonomy_version: str,
    ):
        """
        Initialize CET classification model.

        Args:
            cet_areas: List of CET technology areas
            config: Configuration dictionary from classification.yaml
            taxonomy_version: Taxonomy version (e.g., 'NSTC-2025Q1')
        """
        self.cet_areas = cet_areas
        self.config = config
        self.taxonomy_version = taxonomy_version

        # Build CET keyword mapping
        self.cet_keywords = {area.cet_id: area.keywords for area in cet_areas}
        self.cet_id_to_name = {area.cet_id: area.name for area in cet_areas}

        # Initialize pipelines (one per CET area for binary classification)
        self.pipelines: dict[str, Pipeline] = {}
        self.is_trained = False

        # Model metadata
        self.training_date: str | None = None
        self.model_version = config.get("model_version", "v1.0.0")

        logger.info(
            f"Initialized ApplicabilityModel for {len(cet_areas)} CET areas "
            f"(taxonomy: {taxonomy_version})"
        )

    def _build_pipeline(self, cet_id: str) -> Pipeline:
        """
        Build classification pipeline for a single CET area.

        Pipeline stages:
        1. TF-IDF Vectorization with keyword boosting
        2. Feature selection (chi-squared)
        3. Logistic regression
        4. Probability calibration

        Args:
            cet_id: CET area identifier

        Returns:
            Scikit-learn Pipeline
        """
        tfidf_config = self.config.get("tfidf", {})
        lr_config = self.config.get("logistic_regression", {})
        feature_config = self.config.get("feature_selection", {})
        calibration_config = self.config.get("calibration", {})

        # TF-IDF Vectorizer with keyword boosting
        vectorizer = CETAwareTfidfVectorizer(
            cet_keywords=self.cet_keywords,
            keyword_boost_factor=tfidf_config.get("keyword_boost_factor", 2.0),
            max_features=tfidf_config.get("max_features", 5000),
            min_df=tfidf_config.get("min_df", 2),
            max_df=tfidf_config.get("max_df", 0.95),
            ngram_range=tuple(tfidf_config.get("ngram_range", [1, 2])),
            sublinear_tf=tfidf_config.get("sublinear_tf", True),
            use_idf=tfidf_config.get("use_idf", True),
            smooth_idf=tfidf_config.get("smooth_idf", True),
            norm=tfidf_config.get("norm", "l2"),
        )

        # Feature selection
        feature_selector = None
        if feature_config.get("enabled", True):
            k_best = feature_config.get("k_best", 3000)
            feature_selector = SelectKBest(chi2, k=k_best)

        # Logistic Regression
        classifier = LogisticRegression(
            penalty=lr_config.get("penalty", "l2"),
            C=lr_config.get("C", 1.0),
            solver=lr_config.get("solver", "lbfgs"),
            max_iter=lr_config.get("max_iter", 1000),
            class_weight=lr_config.get("class_weight", "balanced"),
            random_state=lr_config.get("random_state", 42),
            n_jobs=lr_config.get("n_jobs", -1),
        )

        # Calibration wrapper
        calibrated_classifier = CalibratedClassifierCV(
            estimator=classifier,
            method=calibration_config.get("method", "sigmoid"),
            cv=calibration_config.get("cv", 3),
        )

        # Build pipeline
        steps = [
            ("vectorizer", vectorizer),
        ]

        if feature_selector:
            steps.append(("feature_selection", feature_selector))

        steps.extend(
            [
                ("classifier", calibrated_classifier),
            ]
        )

        pipeline = Pipeline(steps)

        logger.debug(f"Built pipeline for {cet_id} with {len(steps)} steps")
        return pipeline

    def train(self, X_train: list[str], y_train: pd.DataFrame) -> dict[str, Any]:
        """
        Train classification models for all CET areas.

        Args:
            X_train: List of document texts
            y_train: DataFrame with binary columns for each CET area (1=applicable, 0=not)

        Returns:
            Training metrics dictionary
        """
        logger.info(f"Training CET classification models on {len(X_train)} documents")

        if len(X_train) != len(y_train):
            raise ValidationError(
                "X_train and y_train must have same length",
                component="ml.cet_classifier",
                operation="train",
                details={"X_train_length": len(X_train), "y_train_length": len(y_train)},
            )

        metrics = {}

        # Train one binary classifier per CET area
        for area in self.cet_areas:
            cet_id = area.cet_id

            if cet_id not in y_train.columns:
                logger.warning(f"CET area {cet_id} not found in training labels, skipping")
                continue

            logger.info(f"Training classifier for {cet_id} ({area.name})")

            # Build pipeline
            pipeline = self._build_pipeline(cet_id)

            # Get labels for this CET area
            y_binary = y_train[cet_id].values

            # Check class balance
            pos_count = y_binary.sum()
            neg_count = len(y_binary) - pos_count
            logger.debug(f"  Class balance: {pos_count} positive, {neg_count} negative")

            if pos_count == 0:
                logger.warning(f"  No positive examples for {cet_id}, skipping")
                continue

            # Train pipeline
            pipeline.fit(X_train, y_binary)

            # Store trained pipeline
            self.pipelines[cet_id] = pipeline

            # Calculate training metrics (on training set - for monitoring only)
            y_pred_proba = pipeline.predict_proba(X_train)[:, 1]
            y_pred = (y_pred_proba >= 0.5).astype(int)

            accuracy = (y_pred == y_binary).mean()
            precision = (y_pred * y_binary).sum() / (y_pred.sum() + 1e-10)
            recall = (y_pred * y_binary).sum() / (y_binary.sum() + 1e-10)
            f1 = 2 * precision * recall / (precision + recall + 1e-10)

            metrics[cet_id] = {
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "positive_examples": int(pos_count),
                "negative_examples": int(neg_count),
            }

            logger.info(
                f"  Trained {cet_id}: accuracy={accuracy:.3f}, "
                f"precision={precision:.3f}, recall={recall:.3f}, f1={f1:.3f}"
            )

        self.is_trained = True
        self.training_date = datetime.now().isoformat()

        logger.info(
            f"Training complete: {len(self.pipelines)}/{len(self.cet_areas)} "
            f"classifiers trained"
        )

        return metrics

    def classify(
        self,
        text: str,
        return_all_scores: bool = False,
    ) -> list[CETClassification]:
        """
        Classify a single document into CET areas.

        Args:
            text: Document text to classify
            return_all_scores: If True, return scores for all CET areas (default: False)

        Returns:
            List of CETClassification objects sorted by score (descending)
        """
        if not self.is_trained:
            raise CETClassificationError(
                "Model must be trained before classification",
                component="ml.cet_classifier",
                operation="classify",
                details={"is_trained": self.is_trained, "num_pipelines": len(self.pipelines)},
            )

        scores = self._get_scores([text])[0]

        # Get thresholds
        thresholds = self.config.get("confidence_thresholds", {})
        high_threshold = thresholds.get("high", 70.0)
        medium_threshold = thresholds.get("medium", 40.0)

        # Convert to CETClassification objects
        classifications = []
        for cet_id, score in scores.items():
            # Determine classification level
            if score >= high_threshold:
                level = ClassificationLevel.HIGH
            elif score >= medium_threshold:
                level = ClassificationLevel.MEDIUM
            else:
                level = ClassificationLevel.LOW

            # Only include if above threshold or return_all_scores
            min_threshold = medium_threshold if not return_all_scores else 0.0
            if score >= min_threshold:
                classifications.append(
                    CETClassification(
                        cet_id=cet_id,
                        cet_name=self.cet_id_to_name.get(cet_id, cet_id),
                        score=score,
                        classification=level,
                        primary=False,  # Will be set by caller
                        classified_at=datetime.now().isoformat(),
                        taxonomy_version=self.taxonomy_version,
                    )
                )

        # Sort by score (descending)
        classifications.sort(key=lambda x: x.score, reverse=True)

        # Mark primary (highest scoring)
        if classifications:
            classifications[0].primary = True

        return classifications

    def classify_batch(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[CETClassification]]:
        """
        Classify multiple documents efficiently.

        Args:
            texts: List of document texts
            batch_size: Batch size (default: from config or 1000)

        Returns:
            List of classification lists (one per document)
        """
        if not self.is_trained:
            raise CETClassificationError(
                "Model must be trained before classification",
                component="ml.cet_classifier",
                operation="classify",
                details={"is_trained": self.is_trained, "num_pipelines": len(self.pipelines)},
            )

        if batch_size is None:
            batch_size = self.config.get("batch", {}).get("size", 1000)

        logger.info(f"Classifying {len(texts)} documents in batches of {batch_size}")

        all_classifications = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.debug(f"Processing batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")

            # Get scores for batch
            batch_scores = self._get_scores(batch)

            # Convert to classifications
            for scores in batch_scores:
                classifications = self._scores_to_classifications(scores)
                all_classifications.append(classifications)

        logger.info(f"Batch classification complete: {len(all_classifications)} documents")
        return all_classifications

    def _get_scores(self, texts: list[str]) -> list[dict[str, float]]:
        """
        Get classification scores for documents.

        Args:
            texts: List of document texts

        Returns:
            List of score dictionaries (CET ID -> score)
        """
        # Initialize scores_list with empty dictionaries for each text
        scores_list = [{} for _ in texts]

        # Get prediction from each CET classifier for all texts at once
        for cet_id, pipeline in self.pipelines.items():
            try:
                # Predict probability of positive class (applicable) for the whole batch
                probas = pipeline.predict_proba(texts)[:, 1]
                # Convert to 0-100 scale
                scores = [float(p * 100) for p in probas]

                # Assign scores to the correct text in scores_list
                for i, score in enumerate(scores):
                    scores_list[i][cet_id] = score
            except Exception as e:
                logger.warning(f"Classification failed for {cet_id} for the batch: {e}")
                for i in range(len(texts)):
                    scores_list[i][cet_id] = 0.0

        return scores_list

    def _scores_to_classifications(self, scores: dict[str, float]) -> list[CETClassification]:
        """Convert score dictionary to CETClassification objects."""
        thresholds = self.config.get("confidence_thresholds", {})
        medium_threshold = thresholds.get("medium", 40.0)

        classifications = []

        for cet_id, score in scores.items():
            if score >= medium_threshold:
                level = self._score_to_level(score)
                classifications.append(
                    CETClassification(
                        cet_id=cet_id,
                        cet_name=self.cet_id_to_name.get(cet_id, cet_id),
                        score=score,
                        classification=level,
                        primary=False,
                        classified_at=datetime.now().isoformat(),
                        taxonomy_version=self.taxonomy_version,
                    )
                )

        # Sort and mark primary
        classifications.sort(key=lambda x: x.score, reverse=True)
        if classifications:
            classifications[0].primary = True

        return classifications

    def _score_to_level(self, score: float) -> ClassificationLevel:
        """Convert numeric score to classification level."""
        thresholds = self.config.get("confidence_thresholds", {})
        high_threshold = thresholds.get("high", 70.0)
        medium_threshold = thresholds.get("medium", 40.0)

        if score >= high_threshold:
            return ClassificationLevel.HIGH
        elif score >= medium_threshold:
            return ClassificationLevel.MEDIUM
        else:
            return ClassificationLevel.LOW

    def save(self, filepath: Path) -> None:
        """
        Save trained model to disk.

        Args:
            filepath: Path to save model file (.pkl)
        """
        if not self.is_trained:
            raise CETClassificationError(
                "Cannot save untrained model",
                component="ml.cet_classifier",
                operation="save",
                details={"is_trained": self.is_trained, "num_pipelines": len(self.pipelines)},
            )

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "pipelines": self.pipelines,
            "cet_areas": [area.model_dump() for area in self.cet_areas],
            "config": self.config,
            "taxonomy_version": self.taxonomy_version,
            "training_date": self.training_date,
            "model_version": self.model_version,
            "is_trained": self.is_trained,
        }

        with open(filepath, "wb") as f:
            pickle.dump(model_data, f)

        logger.info(f"Model saved to {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> "ApplicabilityModel":
        """
        Load trained model from disk.

        Args:
            filepath: Path to model file (.pkl)

        Returns:
            Loaded ApplicabilityModel instance
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileSystemError(
                f"Model file not found: {filepath}",
                file_path=str(filepath),
                operation="load_model",
                component="ml.cet_classifier",
            )

        with open(filepath, "rb") as f:
            model_data = pickle.load(f)

        # Reconstruct CETArea objects
        cet_areas = [CETArea(**area_dict) for area_dict in model_data["cet_areas"]]

        # Create model instance
        model = cls(
            cet_areas=cet_areas,
            config=model_data["config"],
            taxonomy_version=model_data["taxonomy_version"],
        )

        # Restore trained state
        model.pipelines = model_data["pipelines"]
        model.is_trained = model_data["is_trained"]
        model.training_date = model_data["training_date"]
        model.model_version = model_data.get("model_version", "v1.0.0")

        logger.info(
            f"Model loaded from {filepath} "
            f"(version: {model.model_version}, trained: {model.training_date})"
        )

        return model

    def get_metadata(self) -> dict[str, Any]:
        """Get model metadata."""
        return {
            "model_version": self.model_version,
            "taxonomy_version": self.taxonomy_version,
            "training_date": self.training_date,
            "is_trained": self.is_trained,
            "num_cet_areas": len(self.cet_areas),
            "num_trained_classifiers": len(self.pipelines),
            "cet_areas": [area.cet_id for area in self.cet_areas],
        }

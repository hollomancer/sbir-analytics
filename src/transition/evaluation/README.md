# Transition Evaluation Module

This directory provides reusable helpers for assessing the quality of Phase III transition detections. It is designed to be import-safe (no Dagster or Neo4j dependencies) so the same code can be invoked from unit tests, notebooks, ad-hoc scripts, or CI checks.

## Key Components

- **`TransitionEvaluator`** (`evaluator.py`): Core class that compares detected award→contract transitions against a ground-truth dataset and reports precision, recall, F1, and confidence-band summaries.
- **`EvaluationResult`**: Data container returned by `TransitionEvaluator.evaluate`, exposing metrics, confusion matrix, and serialized metadata.
- **`ConfusionMatrix`**: Lightweight struct encapsulating the basic TP/FP/FN/TN counts that underpin downstream analytics.

## Typical Workflow

1. **Load detections**  
   Materialize detections from `transition_detections.parquet` or another source into a pandas DataFrame. The evaluator expects, at minimum, `award_id`, `contract_id`, `likelihood_score`, and (optionally) `confidence`.

2. **Load ground truth**  
   Assemble a DataFrame of known Phase III linkages. Each row should reference the same identifier columns as the detections. A boolean label column can be provided when the input contains both positives and negatives.

3. **Run evaluation**

   ```python
   import pandas as pd
   from src.transition.evaluation.evaluator import TransitionEvaluator

   detections = pd.read_parquet("data/processed/transition_detections.parquet")
   ground_truth = pd.read_csv("data/reference/phase3_ground_truth.csv")

   evaluator = TransitionEvaluator(score_threshold=0.60)
   result = evaluator.evaluate(detections, ground_truth)
   ```

4. **Consume results**  
   The returned `EvaluationResult` exposes metrics as properties, and `result.to_dict()` yields a JSON-serializable payload suitable for dashboards, reports, or CI regression gates.

## Design Principles

- **Pure DataFrame Inputs**: All inputs are pandas DataFrames to avoid coupling with specific storage backends.
- **Score Threshold Awareness**: `TransitionEvaluator` applies a configurable likelihood score threshold before counting detections as positives.
- **Confidence Band Analytics**: Metrics are automatically bucketed by the detection confidence levels (`high`, `likely`, `possible`) for rapid diagnostics.
- **Safe Defaults**: Empty or missing inputs return zeroed results instead of raising, enabling resilient CI flows.

## Extensibility Ideas

- **ROC / PR Curves**: Add helpers that sweep the score threshold to generate ROC or precision-recall curves.
- **Bootstrap Confidence Intervals**: Provide uncertainty estimates around precision/recall using bootstrap resampling.
- **Explainability Artifacts**: Enrich `EvaluationResult.metadata` with representative false positives/negatives for analyst review.

## Related Tasks

Progress on evaluation work is tracked in `openspec/changes/add-transition-detection/tasks.md` under Section 18. As the evaluator matures, additional documentation (CLI wrappers, CI integration guidelines, dashboard hooks) should be placed alongside this README.
# sbir-ml

SBIR ML / data science — CET classification, transition detection, and analysis
tools.

Houses the machine-learning and scoring layers of the pipeline: the Critical &
Emerging Technology (CET) classifier, the multi-signal Phase II → Phase III
transition detector, and the analytics that aggregate their outputs. Methodology
is documented under [`docs/ml/`](../../docs/ml/) and
[`docs/transition/`](../../docs/transition/).

## Installation

The workspace packages are currently installed from a repository checkout; they
are not published to PyPI. From the repository root:

```bash
make install  # full workspace, including sbir-ml[nlp]
```

Core deps: `sbir-etl`, `scikit-learn`, `tqdm`. Optional extras:

| Extra | Adds |
|-------|------|
| `sbir-ml[nlp]` | spaCy + huggingface-hub (NLP feature extraction) |
| `sbir-ml[modernbert-local]` | sentence-transformers + torch + transformers (local ModernBERT embeddings) |

## Key Entry Points

| Import | Purpose |
|--------|---------|
| `sbir_ml.ml.models.cet_classifier` — `CETClassifier` | Per-CET TF-IDF → logistic-regression classifier (0–100 scores) |
| `sbir_ml.ml.models.rule_engine` — `RuleEngine` | Post-ML rule layer (negative keywords, context boosts, agency priors) driven by `config/cet/classification.yaml` |
| `sbir_ml.transition.detection.scoring` — `TransitionScorer` | Six-signal composite transition scoring |
| `sbir_ml.transition.detection.detector` / `evidence` | Detection orchestration + evidence bundles |
| `sbir_ml.transition.features.vendor_resolver` — `VendorResolver` | UEI/CAGE/DUNS + fuzzy (`token_sort_ratio`) vendor matching |
| `sbir_ml.transition.features.cet_analyzer` / `patent_analyzer` | CET and patent signal extraction |
| `sbir_ml.transition.analysis.analytics` — `TransitionAnalytics` | KPI aggregation over detections |

## Notes

- Transition scoring HIGH-threshold polarity is gated on every PR by
  `tests/unit/scripts/test_phase_iii_precision_backtest.py`. The ≥85%
  HIGH-precision number is a manual S3-corpus run of
  `scripts/phase_iii_precision_backtest.py`, not a CI gate.
- The six scored signals and their default weights are documented in
  [`docs/transition/scoring-guide.md`](../../docs/transition/scoring-guide.md).
